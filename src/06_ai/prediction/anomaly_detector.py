#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AnomalyDetector - Autoencoder-based Anomaly Detection

Detects abnormal market behaviour (pump & dump, wash trading, unusual
volatility) using a lightweight autoencoder.  Falls back to a
statistical Z-score detector when PyTorch is unavailable.

Latency target: P95 < 100 ms for real-time inference.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


if TORCH_AVAILABLE:
    class _AutoencoderNet(nn.Module):
        """Fully-connected autoencoder for anomaly detection."""

        def __init__(self, input_dim: int, encoding_dim: int = 16):
            super().__init__()
            hidden = max(encoding_dim * 2, 32)
            self.encoder = nn.Sequential(
                nn.Linear(input_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, encoding_dim),
                nn.ReLU(),
            )
            self.decoder = nn.Sequential(
                nn.Linear(encoding_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, input_dim),
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":  # type: ignore[name-defined]
            return self.decoder(self.encoder(x))

        def reconstruction_error(self, x: "torch.Tensor") -> "torch.Tensor":  # type: ignore[name-defined]
            recon = self.forward(x)
            return ((x - recon) ** 2).mean(dim=1)


class AnomalyDetector:
    """
    Autoencoder-based market anomaly detector.

    Normal market behaviour is learnt during :meth:`train`.
    A sample is flagged as anomalous when its reconstruction error
    exceeds a threshold derived from training-time statistics.

    Falls back to Z-score detection when PyTorch is unavailable.

    Example::

        detector = AnomalyDetector(input_dim=10)
        detector.train(X_normal)
        result = detector.detect(X_new)
        print(result["anomalies"])
    """

    def __init__(
        self,
        input_dim: int = 10,
        encoding_dim: int = 16,
        threshold_sigma: float = 3.0,
        device: str = "cpu",
    ):
        """
        Args:
            input_dim: Number of input features.
            encoding_dim: Autoencoder bottleneck dimension.
            threshold_sigma: Number of standard deviations above the
                mean training error to use as the anomaly threshold.
            device: Torch device string.
        """
        self.input_dim = input_dim
        self.encoding_dim = encoding_dim
        self.threshold_sigma = threshold_sigma
        self.device = device

        self._model: Optional[Any] = None
        self._threshold: float = 0.0
        self._train_mean: float = 0.0
        self._train_std: float = 1.0
        self._is_trained = False

        # Fallback Z-score statistics
        self._feature_mean: Optional[np.ndarray] = None
        self._feature_std: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 1e-3,
    ) -> Dict[str, Any]:
        """
        Train the autoencoder on normal market data.

        Args:
            X: Normal training samples (N × features).
            epochs: Training epochs.
            batch_size: Mini-batch size.
            learning_rate: Adam learning rate.

        Returns:
            Training metrics dict.
        """
        X = np.asarray(X, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        input_dim = X.shape[1]
        self.input_dim = input_dim

        if TORCH_AVAILABLE:
            return self._train_pytorch(X, epochs, batch_size, learning_rate)
        return self._train_zscore(X)

    def _train_pytorch(
        self,
        X: np.ndarray,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> Dict[str, Any]:
        import torch
        from torch.utils.data import DataLoader, TensorDataset

        self._model = _AutoencoderNet(self.input_dim, self.encoding_dim).to(self.device)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()

        dataset = TensorDataset(torch.tensor(X))
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(epochs):
            self._model.train()
            total_loss = 0.0
            for (batch,) in loader:
                batch = batch.to(self.device)
                optimizer.zero_grad()
                recon = self._model(batch)
                loss = criterion(recon, batch)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        # Compute threshold from reconstruction errors on training data
        self._model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X).to(self.device)
            errors = self._model.reconstruction_error(X_t).cpu().numpy()

        self._train_mean = float(errors.mean())
        self._train_std = float(errors.std() + 1e-8)
        self._threshold = self._train_mean + self.threshold_sigma * self._train_std
        self._is_trained = True

        return {
            "method": "autoencoder",
            "input_dim": self.input_dim,
            "threshold": round(self._threshold, 6),
        }

    def _train_zscore(self, X: np.ndarray) -> Dict[str, Any]:
        self._feature_mean = X.mean(axis=0)
        self._feature_std = X.std(axis=0) + 1e-8
        self._is_trained = True
        return {"method": "zscore", "input_dim": self.input_dim}

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, X: np.ndarray) -> Dict[str, Any]:
        """
        Detect anomalies in new samples.

        Args:
            X: Input samples (N × features).

        Returns:
            ::

                {
                    "anomalies": [
                        {
                            "index": int,
                            "score": float,   # reconstruction error
                            "is_anomaly": bool,
                            "severity": str   # low | medium | high
                        }, ...
                    ],
                    "anomaly_count": int,
                    "timestamp": str,
                }
        """
        X = np.asarray(X, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        if not self._is_trained:
            logger.warning("AnomalyDetector not trained; all samples marked normal")
            return self._empty_result(len(X))

        if TORCH_AVAILABLE and self._model is not None:
            scores = self._score_pytorch(X)
        else:
            scores = self._score_zscore(X)

        anomalies = []
        for idx, score in enumerate(scores):
            is_anomaly = float(score) > self._threshold
            severity = self._severity(score)
            anomalies.append({
                "index": idx,
                "score": round(float(score), 6),
                "is_anomaly": is_anomaly,
                "severity": severity,
            })

        anomaly_count = sum(1 for a in anomalies if a["is_anomaly"])
        return {
            "anomalies": anomalies,
            "anomaly_count": anomaly_count,
            "threshold": round(self._threshold, 6),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def detect_single(self, x: np.ndarray) -> Tuple[bool, float]:
        """
        Convenience method for a single sample.

        Returns:
            Tuple of (is_anomaly, score).
        """
        result = self.detect(x.reshape(1, -1))
        entry = result["anomalies"][0]
        return entry["is_anomaly"], entry["score"]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _score_pytorch(self, X: np.ndarray) -> np.ndarray:
        import torch
        self._model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X).to(self.device)
            return self._model.reconstruction_error(X_t).cpu().numpy()

    def _score_zscore(self, X: np.ndarray) -> np.ndarray:
        if self._feature_mean is None:
            return np.zeros(len(X))
        z = np.abs((X - self._feature_mean) / self._feature_std)
        # Max Z-score across features as the anomaly score
        self._threshold = self.threshold_sigma
        return z.max(axis=1)

    def _severity(self, score: float) -> str:
        if score < self._threshold * 1.5:
            return "low"
        elif score < self._threshold * 2.5:
            return "medium"
        return "high"

    @staticmethod
    def _empty_result(n: int) -> Dict[str, Any]:
        return {
            "anomalies": [
                {"index": i, "score": 0.0, "is_anomaly": False, "severity": "low"}
                for i in range(n)
            ],
            "anomaly_count": 0,
            "threshold": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
