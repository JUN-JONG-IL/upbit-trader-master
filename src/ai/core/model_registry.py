#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ModelRegistry - MLflow-based Model Version Management

Provides model registration, versioning, stage promotion, and retrieval.
Falls back gracefully to an in-memory registry when MLflow is unavailable.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import mlflow
    import mlflow.pytorch
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logger.warning("MLflow not installed; using in-memory model registry.")


@dataclass
class ModelVersion:
    """Metadata for a single registered model version."""

    name: str
    version: str
    stage: str = "Staging"          # Staging | Production | Archived
    model_type: str = "unknown"
    accuracy: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    artifact_uri: str = ""
    trained_at: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def run_name(self) -> str:
        return f"{self.name}-{self.version}"


class ModelRegistry:
    """
    MLflow-based model registry with in-memory fallback.

    When MLflow is available, models are tracked in an MLflow experiment.
    The in-memory index is always maintained for fast synchronous lookups.

    Example::

        registry = ModelRegistry("sqlite:///data/mlruns.db")
        info = registry.register(model, name="lstm-v2", version="2.0.0",
                                  model_type="pytorch",
                                  metrics={"mae": 0.05, "rmse": 0.08})
        prod_model = registry.get_production_model("lstm-v2")
    """

    def __init__(self, tracking_uri: str = "sqlite:///data/mlruns.db"):
        """
        Args:
            tracking_uri: MLflow tracking server URI or local SQLite path.
        """
        self.tracking_uri = tracking_uri
        self._registry: Dict[str, List[ModelVersion]] = {}

        if MLFLOW_AVAILABLE:
            try:
                mlflow.set_tracking_uri(tracking_uri)
                logger.info("MLflow registry initialised: %s", tracking_uri)
            except Exception as exc:
                logger.error("MLflow init failed (%s); using in-memory registry", exc)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        model: Any,
        name: str,
        version: str,
        model_type: str = "generic",
        metrics: Optional[Dict[str, float]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        stage: str = "Staging",
    ) -> ModelVersion:
        """
        Register a model and log it to MLflow (if available).

        Args:
            model: The model object to persist.
            name: Logical model name (e.g. ``"lstm-price-predictor"``).
            version: Semantic version string (e.g. ``"1.0.0"``).
            model_type: Framework tag (``"pytorch"`` | ``"sklearn"`` | etc.).
            metrics: Evaluation metrics to log.
            parameters: Hyperparameters to log.
            stage: Initial lifecycle stage.

        Returns:
            :class:`ModelVersion` with populated metadata.
        """
        metrics = metrics or {}
        parameters = parameters or {}

        info = ModelVersion(
            name=name,
            version=version,
            stage=stage,
            model_type=model_type,
            accuracy=metrics.get("accuracy", 0.0),
            parameters=parameters,
            metrics=metrics,
        )

        if MLFLOW_AVAILABLE:
            info.artifact_uri = self._log_to_mlflow(
                model, name, version, model_type, metrics, parameters
            )

        self._registry.setdefault(name, []).append(info)
        logger.info("Model registered: %s v%s (%s)", name, version, stage)
        return info

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_production_model(self, name: str) -> Optional[ModelVersion]:
        """Return the latest Production-stage version for *name*."""
        return self._latest_by_stage(name, "Production")

    def get_staging_model(self, name: str) -> Optional[ModelVersion]:
        """Return the latest Staging-stage version for *name*."""
        return self._latest_by_stage(name, "Staging")

    def get_model(self, name: str, version: str) -> Optional[ModelVersion]:
        """Return a specific version by name and version string."""
        for mv in self._registry.get(name, []):
            if mv.version == version:
                return mv
        return None

    def list_models(self) -> List[ModelVersion]:
        """Return all registered model versions."""
        return [mv for versions in self._registry.values() for mv in versions]

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def promote(self, name: str, version: str, target_stage: str) -> bool:
        """
        Promote a model version to a new lifecycle stage.

        Args:
            name: Model name.
            version: Version string.
            target_stage: ``"Staging"`` | ``"Production"`` | ``"Archived"``.

        Returns:
            ``True`` on success, ``False`` if the version was not found.
        """
        for mv in self._registry.get(name, []):
            if mv.version == version:
                mv.stage = target_stage
                logger.info(
                    "Model %s v%s promoted to %s", name, version, target_stage
                )
                return True
        logger.warning("Model %s v%s not found for promotion", name, version)
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _latest_by_stage(self, name: str, stage: str) -> Optional[ModelVersion]:
        candidates = [
            mv for mv in self._registry.get(name, []) if mv.stage == stage
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda mv: mv.trained_at)

    def _log_to_mlflow(
        self,
        model: Any,
        name: str,
        version: str,
        model_type: str,
        metrics: Dict[str, float],
        parameters: Dict[str, Any],
    ) -> str:
        """Log model run to MLflow and return the artifact URI."""
        artifact_uri = ""
        try:
            with mlflow.start_run(run_name=f"{name}-{version}"):
                if parameters:
                    mlflow.log_params(parameters)
                if metrics:
                    mlflow.log_metrics(metrics)
                mlflow.set_tag("model_type", model_type)
                mlflow.set_tag("version", version)

                if model_type == "pytorch":
                    try:
                        mlflow.pytorch.log_model(model, "model")
                    except Exception:
                        mlflow.log_text(str(type(model)), "model_type.txt")
                elif model_type == "sklearn":
                    try:
                        import mlflow.sklearn
                        mlflow.sklearn.log_model(model, "model")
                    except Exception:
                        pass
                else:
                    mlflow.log_text(str(type(model)), "model_type.txt")

                artifact_uri = mlflow.get_artifact_uri()
        except Exception as exc:
            logger.warning("MLflow logging failed: %s", exc)
        return artifact_uri
