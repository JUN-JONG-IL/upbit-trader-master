#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap 예측 모델 (XGBoost 기반)

config.yaml의 ai_ml_features.gap_prediction.enabled=true 시 활성화.
XGBoost를 사용하여 다음 Gap 발생 시간 예측.
"""
import logging
import os
from typing import Optional, List, Dict, Any

LOG = logging.getLogger("timescale.ml.gap_predictor")

try:
    import xgboost as xgb  # type: ignore
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import numpy as np  # type: ignore
    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False


class GapPredictor:
    """
    XGBoost 기반 Gap 발생 예측 모델.
    
    config.yaml:
        ai_ml_features:
            gap_prediction:
                enabled: true
                model_version: "v1"
                threshold: 0.8
    """

    def __init__(self, threshold: float = 0.8, model_version: str = "v1"):
        self.threshold = threshold
        self.model_version = model_version
        self.model: Optional[Any] = None
        self._fitted = False

    def is_available(self) -> bool:
        return XGB_AVAILABLE and NUMPY_AVAILABLE

    def fit(self, features: List[Dict[str, Any]], labels: List[int]):
        """모델 학습"""
        if not self.is_available():
            LOG.warning("⚠️  XGBoost/NumPy 미설치 - Gap 예측 비활성")
            return
        try:
            X = np.array([[f.get("gap_seconds", 0), f.get("volume", 0),
                           f.get("hour", 0), f.get("weekday", 0)] for f in features])
            y = np.array(labels)
            self.model = xgb.XGBClassifier(n_estimators=100, max_depth=4,
                                            use_label_encoder=False, eval_metric="logloss")
            self.model.fit(X, y)
            self._fitted = True
            LOG.info("✅ Gap 예측 모델 학습 완료 (v%s)", self.model_version)
        except Exception as e:
            LOG.error("❌ Gap 예측 모델 학습 실패: %s", e)

    def predict(self, feature: Dict[str, Any]) -> float:
        """Gap 발생 확률 예측 (0.0~1.0)"""
        if not self._fitted or not self.is_available():
            return 0.0
        try:
            X = np.array([[feature.get("gap_seconds", 0), feature.get("volume", 0),
                           feature.get("hour", 0), feature.get("weekday", 0)]])
            prob = self.model.predict_proba(X)[0][1]
            return float(prob)
        except Exception as e:
            LOG.error("Gap 예측 실패: %s", e)
            return 0.0

    def should_fill(self, feature: Dict[str, Any]) -> bool:
        """임계값 기반 Gap Fill 필요 여부"""
        return self.predict(feature) >= self.threshold
