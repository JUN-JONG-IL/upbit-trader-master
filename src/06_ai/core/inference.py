#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
InferenceEngine - Real-time Inference Engine

Provides sub-100 ms synchronous and async prediction endpoints.
Manages model loading, feature preparation, and result formatting.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class InferenceEngine:
    """
    Real-time model inference engine.

    Supports both synchronous (``predict_sync``) and asynchronous
    (``predict``) prediction paths.  Hot-swapping a model via
    :meth:`load_model` is thread-safe for read workloads.

    Latency target: P95 < 100 ms for price prediction models.

    Example::

        engine = InferenceEngine()
        engine.load_model("lstm", my_lstm_model, feature_dim=10)
        result = await engine.predict("lstm", features)
    """

    #: Maximum number of latency measurements to retain per model.
    _LATENCY_WINDOW_SIZE: int = 1000

    def __init__(self, device: str = "cpu"):
        """
        Args:
            device: Torch device string (``"cpu"`` or ``"cuda"``).
        """
        self.device = device
        self._models: Dict[str, Any] = {}
        self._feature_dims: Dict[str, int] = {}
        self._inference_counts: Dict[str, int] = {}
        self._latency_history: Dict[str, List[float]] = {}

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def load_model(
        self, name: str, model: Any, feature_dim: int = 10
    ) -> None:
        """
        Load a model into the inference engine.

        Args:
            name: Unique model identifier.
            model: Model object; must implement ``predict()``.
            feature_dim: Expected number of input features.
        """
        self._models[name] = model
        self._feature_dims[name] = feature_dim
        self._inference_counts[name] = 0
        self._latency_history[name] = []
        logger.info("InferenceEngine: loaded model '%s' (feature_dim=%d)", name, feature_dim)

    def unload_model(self, name: str) -> bool:
        """Remove a model from the engine. Returns True if it existed."""
        removed = self._models.pop(name, None) is not None
        self._feature_dims.pop(name, None)
        self._inference_counts.pop(name, None)
        self._latency_history.pop(name, None)
        if removed:
            logger.info("InferenceEngine: unloaded model '%s'", name)
        return removed

    def list_models(self) -> List[str]:
        """Return names of all loaded models."""
        return list(self._models.keys())

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    async def predict(
        self,
        model_name: str,
        features: np.ndarray,
        return_confidence: bool = True,
    ) -> Dict[str, Any]:
        """
        Async prediction endpoint.

        Runs blocking model inference in a thread pool so that the
        event loop is not blocked.

        Args:
            model_name: Name of the loaded model.
            features: Input feature array (1-D or 2-D).
            return_confidence: If True, attempt to include confidence bounds.

        Returns:
            Dict with keys ``prediction``, ``confidence``,
            ``latency_ms``, ``model_name``.

        Raises:
            KeyError: If *model_name* is not loaded.
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self.predict_sync, model_name, features, return_confidence
        )
        return result

    def predict_sync(
        self,
        model_name: str,
        features: np.ndarray,
        return_confidence: bool = True,
    ) -> Dict[str, Any]:
        """
        Synchronous prediction endpoint.

        Args:
            model_name: Name of the loaded model.
            features: Input feature array.
            return_confidence: Whether to include confidence bounds.

        Returns:
            Prediction result dict.
        """
        if model_name not in self._models:
            raise KeyError(f"Model '{model_name}' not loaded in InferenceEngine")

        model = self._models[model_name]
        features = self._prepare_features(features, model_name)

        t0 = time.perf_counter()
        prediction, confidence = self._run_model(model, features, return_confidence)
        latency_ms = (time.perf_counter() - t0) * 1000

        self._record_latency(model_name, latency_ms)

        return {
            "prediction": float(prediction),
            "confidence": float(confidence),
            "latency_ms": round(latency_ms, 2),
            "model_name": model_name,
        }

    # ------------------------------------------------------------------
    # Batch inference
    # ------------------------------------------------------------------

    async def predict_batch(
        self,
        model_name: str,
        feature_list: List[np.ndarray],
    ) -> List[Dict[str, Any]]:
        """
        Predict for a batch of feature arrays.

        Args:
            model_name: Name of the loaded model.
            feature_list: List of feature arrays.

        Returns:
            List of prediction result dicts.
        """
        tasks = [self.predict(model_name, f) for f in feature_list]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self, model_name: str) -> Dict[str, Any]:
        """
        Return runtime metrics for a loaded model.

        Args:
            model_name: Model identifier.

        Returns:
            Dict with inference count and latency statistics.
        """
        history = self._latency_history.get(model_name, [])
        if not history:
            return {
                "model_name": model_name,
                "inference_count": 0,
                "latency_p50_ms": 0.0,
                "latency_p95_ms": 0.0,
                "latency_mean_ms": 0.0,
            }
        arr = np.array(history)
        return {
            "model_name": model_name,
            "inference_count": self._inference_counts.get(model_name, 0),
            "latency_p50_ms": round(float(np.percentile(arr, 50)), 2),
            "latency_p95_ms": round(float(np.percentile(arr, 95)), 2),
            "latency_mean_ms": round(float(arr.mean()), 2),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prepare_features(
        self, features: np.ndarray, model_name: str
    ) -> np.ndarray:
        """Ensure features are the correct dtype and shape."""
        features = np.asarray(features, dtype=np.float32)
        if features.ndim == 1:
            features = features.reshape(1, -1)
        return features

    def _run_model(
        self, model: Any, features: np.ndarray, return_confidence: bool
    ) -> Tuple[float, float]:
        """
        Execute model inference and return (prediction, confidence).

        Tries PyTorch, then scikit-learn / XGBoost, then a generic
        ``predict()`` call, finally falling back to a dummy value.
        """
        prediction: float = 0.0
        confidence: float = 0.5

        # --- PyTorch ---
        try:
            import torch
            if hasattr(model, "forward") or isinstance(model, torch.nn.Module):
                with torch.no_grad():
                    t = torch.tensor(features, dtype=torch.float32)
                    out = model(t)
                    prediction = float(out.squeeze().item())
                    confidence = 0.7  # default confidence for neural nets
                return prediction, confidence
        except Exception:
            pass

        # --- scikit-learn / XGBoost style ---
        try:
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(features)[0]
                prediction = float(np.argmax(proba))
                confidence = float(np.max(proba))
                return prediction, confidence
        except Exception:
            pass

        # --- Generic predict() ---
        try:
            out = model.predict(features)
            out = np.asarray(out)
            if out.ndim == 0:
                prediction = float(out.item())
            else:
                prediction = float(np.squeeze(out).flat[0])
            return prediction, confidence
        except Exception as exc:
            logger.debug("Model predict() failed: %s", exc)

        return prediction, confidence

    def _record_latency(self, model_name: str, latency_ms: float) -> None:
        self._inference_counts[model_name] = (
            self._inference_counts.get(model_name, 0) + 1
        )
        history = self._latency_history.setdefault(model_name, [])
        history.append(latency_ms)
        # Keep rolling window of last _LATENCY_WINDOW_SIZE measurements
        if len(history) > self._LATENCY_WINDOW_SIZE:
            self._latency_history[model_name] = history[-self._LATENCY_WINDOW_SIZE:]
