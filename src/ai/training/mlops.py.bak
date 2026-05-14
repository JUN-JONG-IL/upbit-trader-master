"""
src/06_ai/training/mlops.py

MLflow + Feast MLOps 파이프라인

- MLflow: 모델 버전 관리, 하이퍼파라미터 및 메트릭 추적
- Feast: 온라인 특성 저장소에서 실시간 특성 조회
"""

from __future__ import annotations

from typing import Any

import mlflow
import mlflow.sklearn
from feast import FeatureStore


class MLOpsManager:
    """
    ML 모델 버전 관리 + 특성 저장소

    Args:
        tracking_uri: MLflow 추적 서버 URI (기본값: http://localhost:5000)
        feature_repo_path: Feast feature_repo 경로 (기본값: feature_repo)
    """

    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        feature_repo_path: str = "feature_repo",
    ):
        mlflow.set_tracking_uri(tracking_uri)
        self.fs = FeatureStore(repo_path=feature_repo_path)

    def log_model(
        self,
        model: Any,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifact_name: str = "model",
    ) -> str:
        """
        모델 + 하이퍼파라미터 + 메트릭 기록

        Args:
            model: sklearn 호환 모델 객체
            params: 하이퍼파라미터 딕셔너리
            metrics: 성능 메트릭 딕셔너리
            artifact_name: MLflow 아티팩트 이름

        Returns:
            run_id: MLflow 실행 ID
        """
        with mlflow.start_run() as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(model, artifact_name)
            return run.info.run_id

    def get_features(self, entity_rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
        """
        Feast 온라인 특성 저장소에서 특성 조회

        Args:
            entity_rows: 엔티티 딕셔너리 리스트 (예: [{"symbol": "KRW-BTC"}])

        Returns:
            특성 딕셔너리 (특성명 → 값 리스트)
        """
        return self.fs.get_online_features(
            features=[
                "candle_stats:open_1h_avg",
                "candle_stats:volume_24h_sum",
                "candle_stats:volatility_7d",
            ],
            entity_rows=entity_rows,
        ).to_dict()

    def load_model(self, run_id: str, artifact_name: str = "model") -> Any:
        """MLflow에서 모델 로드"""
        model_uri = f"runs:/{run_id}/{artifact_name}"
        return mlflow.sklearn.load_model(model_uri)
