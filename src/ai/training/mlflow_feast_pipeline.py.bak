"""
src/06_ai/training/mlflow_feast_pipeline.py

MLflow + Feast 통합 ML 파이프라인
용도: 실험 추적, 모델 버전 관리, 온라인 피처 서빙 통합

의존성:
  pip install mlflow>=3.5.0 feast>=0.60.0
"""
from __future__ import annotations

from typing import Any

import pandas as pd

try:
    import mlflow
    import mlflow.sklearn
    _MLFLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MLFLOW_AVAILABLE = False

try:
    from feast import FeatureStore  # type: ignore
    _FEAST_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FEAST_AVAILABLE = False


class MLflowFeastPipeline:
    """
    MLflow + Feast 통합 ML 파이프라인

    - MLflow: 파라미터·메트릭·모델 아티팩트 추적
    - Feast : 온라인 피처 저장소 연동

    사용 예시::

        pipeline = MLflowFeastPipeline(
            experiment_name="trading_models",
            feast_repo_path="./feast_repo"
        )
        entity_df = pd.DataFrame([{"symbol": "KRW-BTC"}])
        features = pipeline.get_features(entity_df)
        model = pipeline.train_and_log(model, X_train, y_train,
                                       X_val, y_val, params)
    """

    # Feast에서 조회할 기본 피처 목록
    DEFAULT_FEATURES: list[str] = [
        "market_stats:price_mean_24h",
        "market_stats:volume_sum_24h",
        "technical_indicators:rsi_14",
        "technical_indicators:macd",
    ]

    def __init__(
        self,
        experiment_name: str = "trading_models",
        feast_repo_path: str = "./feast_repo",
        mlflow_uri: str = "http://localhost:5000",
    ) -> None:
        if not _MLFLOW_AVAILABLE:
            raise ImportError(
                "mlflow 패키지가 필요합니다. pip install mlflow>=3.5.0"
            )

        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment(experiment_name)

        self.store: Any = None
        if _FEAST_AVAILABLE:
            try:
                self.store = FeatureStore(repo_path=feast_repo_path)
            except Exception:
                # feature_repo 미구성 시 선택적 사용
                self.store = None

    # ------------------------------------------------------------------
    # Feast 피처 조회
    # ------------------------------------------------------------------

    def get_features(
        self,
        entity_df: pd.DataFrame,
        features: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Feast 온라인 피처 저장소에서 피처 조회

        Args:
            entity_df: 엔티티 DataFrame (예: columns=['symbol'])
            features : 조회할 피처 목록 (없으면 DEFAULT_FEATURES 사용)

        Returns:
            피처 DataFrame

        Raises:
            RuntimeError: Feast가 설치되지 않았거나 저장소 미설정 시
        """
        if self.store is None:
            raise RuntimeError(
                "Feast FeatureStore를 사용할 수 없습니다. "
                "feast 패키지를 설치하고 feast_repo_path를 설정하세요."
            )

        return (
            self.store.get_online_features(
                features=features or self.DEFAULT_FEATURES,
                entity_rows=entity_df.to_dict("records"),
            ).to_df()
        )

    # ------------------------------------------------------------------
    # 학습 및 MLflow 로깅
    # ------------------------------------------------------------------

    def train_and_log(
        self,
        model: Any,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        params: dict,
        model_name: str = "model",
    ) -> Any:
        """
        모델 학습 후 MLflow에 파라미터·메트릭·모델 기록

        Args:
            model     : sklearn 호환 모델
            X_train   : 학습 특성
            y_train   : 학습 레이블
            X_val     : 검증 특성
            y_val     : 검증 레이블
            params    : 로깅할 하이퍼파라미터 딕셔너리
            model_name: MLflow artifact 저장 이름

        Returns:
            학습된 모델
        """
        with mlflow.start_run():
            # 파라미터 로깅
            mlflow.log_params(params)

            # 학습
            model.fit(X_train, y_train)

            # 평가
            train_score = float(model.score(X_train, y_train))
            val_score = float(model.score(X_val, y_val))

            mlflow.log_metric("train_score", train_score)
            mlflow.log_metric("val_score", val_score)

            # 모델 저장
            mlflow.sklearn.log_model(model, model_name)

            print(
                f"Train Score: {train_score:.4f}, "
                f"Val Score: {val_score:.4f}"
            )

        return model

    # ------------------------------------------------------------------
    # 모델 로드
    # ------------------------------------------------------------------

    def load_model(self, run_id: str, model_name: str = "model") -> Any:
        """
        MLflow Run에서 모델 로드

        Args:
            run_id    : MLflow Run ID
            model_name: artifact 이름 (기본 'model')

        Returns:
            로드된 sklearn 호환 모델
        """
        model_uri = f"runs:/{run_id}/{model_name}"
        return mlflow.sklearn.load_model(model_uri)

    # ------------------------------------------------------------------
    # Feast 피처 + MLflow 모델 예측
    # ------------------------------------------------------------------

    def predict_with_features(
        self,
        entity_df: pd.DataFrame,
        run_id: str,
        features: list[str] | None = None,
        model_name: str = "model",
    ) -> Any:
        """
        Feast 피처 조회 → MLflow 모델 로드 → 예측

        Args:
            entity_df : 엔티티 DataFrame
            run_id    : MLflow Run ID
            features  : 조회할 피처 목록 (없으면 DEFAULT_FEATURES 사용)
            model_name: artifact 이름

        Returns:
            예측 결과 배열
        """
        feature_df = self.get_features(entity_df, features)
        model = self.load_model(run_id, model_name)
        return model.predict(feature_df)
