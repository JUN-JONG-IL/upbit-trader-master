#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 서비스 모듈

Gap 예측, 이상치 감지 모델을 초기화하고 예측을 실행합니다.

CHANGELOG:
- 2026-03-19 | Copilot | src/ai/priority/services/ → src/ai/ai_engine/ 으로 이동
              ML 서비스는 AI 엔진 레이어에 속하므로 ai_engine/ 하위로 재배치
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MLService:
    """ML 모델 선택/실행 서비스"""

    def __init__(self, db=None, settings=None) -> None:
        """
        Args:
            db: 데이터베이스 세션.
            settings: MLConfig 인스턴스.
        """
        self.db = db
        self.settings = settings
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 모델 초기화
    # ------------------------------------------------------------------

    async def setup_gap_predictor(self) -> None:
        """Gap 예측 모델을 설정합니다."""
        if self.settings is None:
            logger.warning("MLConfig 없음 – Gap 예측 모델 초기화 건너뜀")
            return

        model_type = self.settings.gap_model_type
        params: dict = self.settings.gap_model_params or {}

        try:
            if model_type == "lightgbm":
                import lightgbm as lgb  # type: ignore
                self.models["gap"] = lgb.LGBMRegressor(
                    n_estimators=params.get("n_estimators", 100),
                    learning_rate=params.get("learning_rate", 0.05),
                    max_depth=params.get("max_depth", 7),
                    num_leaves=params.get("num_leaves", 31),
                    random_state=42,
                    verbose=-1,
                )
            elif model_type == "xgboost":
                import xgboost as xgb  # type: ignore
                self.models["gap"] = xgb.XGBRegressor(
                    n_estimators=params.get("n_estimators", 100),
                    learning_rate=params.get("learning_rate", 0.05),
                    max_depth=params.get("max_depth", 7),
                    random_state=42,
                    verbosity=0,
                )
            elif model_type == "catboost":
                from catboost import CatBoostRegressor  # type: ignore
                self.models["gap"] = CatBoostRegressor(
                    iterations=params.get("iterations", 100),
                    learning_rate=params.get("learning_rate", 0.05),
                    depth=params.get("depth", 7),
                    random_state=42,
                    verbose=False,
                )
            elif model_type == "prophet":
                from prophet import Prophet  # type: ignore
                self.models["gap"] = Prophet(
                    daily_seasonality=True,
                    weekly_seasonality=True,
                    yearly_seasonality=False,
                )
            else:
                logger.warning("알 수 없는 Gap 모델 타입: %s", model_type)
                return

            logger.info("Gap 예측 모델 초기화 완료 (%s)", model_type)
        except ImportError as exc:
            logger.error("Gap 예측 모델 라이브러리 없음 (%s): %s", model_type, exc)

    async def setup_anomaly_detector(self) -> None:
        """이상치 감지 모델을 설정합니다."""
        if self.settings is None:
            logger.warning("MLConfig 없음 – 이상치 감지 모델 초기화 건너뜀")
            return

        model_type = self.settings.anomaly_model_type
        contamination = 1.0 - self.settings.anomaly_threshold

        try:
            from sklearn.preprocessing import StandardScaler  # type: ignore

            if model_type == "isolation_forest":
                from sklearn.ensemble import IsolationForest  # type: ignore
                self.models["anomaly"] = IsolationForest(
                    contamination=contamination,
                    random_state=42,
                    n_estimators=100,
                )
            elif model_type == "one_class_svm":
                from sklearn.svm import OneClassSVM  # type: ignore
                self.models["anomaly"] = OneClassSVM(
                    nu=contamination,
                    kernel="rbf",
                )
            elif model_type == "autoencoder":
                # Autoencoder는 PyTorch 기반 별도 구현 사용
                # importlib.util 로 직접 로드 (파일 이동 후에도 경로 안정적으로 유지)
                import importlib.util as _ilu
                import os as _os
                _ad_path = _os.path.normpath(_os.path.join(
                    _os.path.dirname(_os.path.abspath(__file__)),
                    "..", "priority", "models", "anomaly_detector.py"
                ))
                _ad_spec = _ilu.spec_from_file_location("_priority_anomaly_detector", _ad_path)
                _ad_mod = _ilu.module_from_spec(_ad_spec)
                _ad_spec.loader.exec_module(_ad_mod)  # type: ignore
                AutoencoderDetector = _ad_mod.AutoencoderDetector
                self.models["anomaly"] = AutoencoderDetector(
                    threshold=self.settings.anomaly_threshold
                )
            else:
                logger.warning("알 수 없는 이상치 감지 모델: %s", model_type)
                return

            self.scalers["anomaly"] = StandardScaler()
            logger.info("이상치 감지 모델 초기화 완료 (%s)", model_type)
        except ImportError as exc:
            logger.error("이상치 감지 모델 라이브러리 없음 (%s): %s", model_type, exc)

    # ------------------------------------------------------------------
    # 예측 실행
    # ------------------------------------------------------------------

    async def predict_gap(
        self, symbol: str, exchange: str = "upbit"
    ) -> Dict[str, Any]:
        """Gap 예측을 실행합니다."""
        try:
            features = await self._prepare_gap_features(symbol, exchange)
            model = self.models.get("gap")
            if model is None:
                raise ValueError("Gap 예측 모델이 초기화되지 않았습니다.")

            if (
                self.settings is not None
                and self.settings.gap_model_type == "prophet"
            ):
                prediction = await self._predict_with_prophet(model, features)
            else:
                if not features:
                    raise ValueError("Gap 예측을 위한 피처 데이터가 없습니다.")
                prediction = float(model.predict([features])[0])

            return {
                "symbol": symbol,
                "exchange": exchange,
                "prediction": prediction,
                "model_type": getattr(self.settings, "gap_model_type", "unknown"),
                "predicted_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error("Gap 예측 오류: %s", exc)
            return {"symbol": symbol, "error": str(exc)}

    async def detect_anomaly(
        self, symbol: str, exchange: str = "upbit"
    ) -> Dict[str, Any]:
        """이상치 감지를 실행합니다."""
        try:
            features = await self._prepare_anomaly_features(symbol, exchange)
            if not features:
                raise ValueError("이상치 감지를 위한 피처 데이터가 없습니다.")

            scaler = self.scalers.get("anomaly")
            model = self.models.get("anomaly")
            if model is None:
                raise ValueError("이상치 감지 모델이 초기화되지 않았습니다.")

            import numpy as np  # type: ignore
            feature_arr = np.array(features).reshape(1, -1)
            if scaler is not None:
                feature_arr = scaler.fit_transform(feature_arr)

            prediction = model.predict(feature_arr)
            is_anomaly = int(prediction[0]) == -1

            return {
                "symbol": symbol,
                "exchange": exchange,
                "is_anomaly": is_anomaly,
                "detected_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error("이상치 감지 오류: %s", exc)
            return {"symbol": symbol, "error": str(exc)}

    # ------------------------------------------------------------------
    # 피처 준비 (실제 구현 시 DB/API 연동)
    # ------------------------------------------------------------------

    async def _prepare_gap_features(
        self, symbol: str, exchange: str
    ) -> List[float]:
        """Gap 예측 피처를 준비합니다 (stub)."""
        return []

    async def _predict_with_prophet(self, model: Any, features: Any) -> float:
        """Prophet 모델로 예측합니다 (stub)."""
        return 0.0

    async def _prepare_anomaly_features(
        self, symbol: str, exchange: str
    ) -> List[float]:
        """이상치 감지 피처를 준비합니다 (stub)."""
        return []
