#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap 예측 모델 모듈

LightGBM, XGBoost, CatBoost, Prophet 기반 Gap 예측 모델을 제공합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class GapPredictorBase:
    """Gap 예측 기본 클래스"""

    def __init__(self, params: Optional[Dict] = None) -> None:
        self.params = params or {}
        self.model: Any = None
        self.is_trained: bool = False

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_trained:
            raise RuntimeError("모델이 학습되지 않았습니다.")
        raise NotImplementedError

    def _validate_input(self, X: np.ndarray) -> np.ndarray:
        if X is None or len(X) == 0:
            raise ValueError("입력 데이터가 비어 있습니다.")
        return np.asarray(X, dtype=float)


class LightGBMGapPredictor(GapPredictorBase):
    """LightGBM 기반 Gap 예측 모델 (추천)"""

    def __init__(self, params: Optional[Dict] = None) -> None:
        super().__init__(params)
        try:
            import lightgbm as lgb  # type: ignore
            self.model = lgb.LGBMRegressor(
                n_estimators=self.params.get("n_estimators", 100),
                learning_rate=self.params.get("learning_rate", 0.05),
                max_depth=self.params.get("max_depth", 7),
                num_leaves=self.params.get("num_leaves", 31),
                random_state=42,
                verbose=-1,
            )
        except ImportError:
            logger.error("lightgbm 패키지가 설치되지 않았습니다.")
            raise

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        X = self._validate_input(X)
        self.model.fit(X, y)
        self.is_trained = True
        logger.info("LightGBM Gap 예측 모델 학습 완료")

    def predict(self, X: np.ndarray) -> np.ndarray:
        super().predict(X)
        X = self._validate_input(X)
        return self.model.predict(X)


class XGBoostGapPredictor(GapPredictorBase):
    """XGBoost 기반 Gap 예측 모델"""

    def __init__(self, params: Optional[Dict] = None) -> None:
        super().__init__(params)
        try:
            import xgboost as xgb  # type: ignore
            self.model = xgb.XGBRegressor(
                n_estimators=self.params.get("n_estimators", 100),
                learning_rate=self.params.get("learning_rate", 0.05),
                max_depth=self.params.get("max_depth", 7),
                random_state=42,
                verbosity=0,
            )
        except ImportError:
            logger.error("xgboost 패키지가 설치되지 않았습니다.")
            raise

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        X = self._validate_input(X)
        self.model.fit(X, y)
        self.is_trained = True
        logger.info("XGBoost Gap 예측 모델 학습 완료")

    def predict(self, X: np.ndarray) -> np.ndarray:
        super().predict(X)
        X = self._validate_input(X)
        return self.model.predict(X)


class CatBoostGapPredictor(GapPredictorBase):
    """CatBoost 기반 Gap 예측 모델 (범주형 데이터 강점)"""

    def __init__(self, params: Optional[Dict] = None) -> None:
        super().__init__(params)
        try:
            from catboost import CatBoostRegressor  # type: ignore
            self.model = CatBoostRegressor(
                iterations=self.params.get("iterations", 100),
                learning_rate=self.params.get("learning_rate", 0.05),
                depth=self.params.get("depth", 7),
                random_state=42,
                verbose=False,
            )
        except ImportError:
            logger.error("catboost 패키지가 설치되지 않았습니다.")
            raise

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        X = self._validate_input(X)
        self.model.fit(X, y)
        self.is_trained = True
        logger.info("CatBoost Gap 예측 모델 학습 완료")

    def predict(self, X: np.ndarray) -> np.ndarray:
        super().predict(X)
        X = self._validate_input(X)
        return self.model.predict(X)


class ProphetGapPredictor(GapPredictorBase):
    """Prophet 기반 Gap 예측 모델 (시계열 특화)"""

    def __init__(self, params: Optional[Dict] = None) -> None:
        super().__init__(params)
        try:
            from prophet import Prophet  # type: ignore
            self.model = Prophet(
                daily_seasonality=self.params.get("daily_seasonality", True),
                weekly_seasonality=self.params.get("weekly_seasonality", True),
                yearly_seasonality=self.params.get("yearly_seasonality", False),
            )
        except ImportError:
            logger.error("prophet 패키지가 설치되지 않았습니다.")
            raise

    def train(self, df: pd.DataFrame) -> None:  # type: ignore[override]
        """df는 'ds' (datetime), 'y' (target) 컬럼을 가져야 합니다."""
        if not {"ds", "y"}.issubset(df.columns):
            raise ValueError("Prophet 학습 데이터는 'ds', 'y' 컬럼이 필요합니다.")
        self.model.fit(df)
        self.is_trained = True
        logger.info("Prophet Gap 예측 모델 학습 완료")

    def predict(self, future_df: pd.DataFrame) -> np.ndarray:  # type: ignore[override]
        if not self.is_trained:
            raise RuntimeError("모델이 학습되지 않았습니다.")
        forecast = self.model.predict(future_df)
        return forecast["yhat"].values


def create_gap_predictor(model_type: str, params: Optional[Dict] = None) -> GapPredictorBase:
    """팩토리 함수: 모델 타입에 맞는 Gap 예측기를 생성합니다."""
    predictors = {
        "lightgbm": LightGBMGapPredictor,
        "xgboost": XGBoostGapPredictor,
        "catboost": CatBoostGapPredictor,
        "prophet": ProphetGapPredictor,
    }
    cls = predictors.get(model_type)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 모델 타입: {model_type}. 사용 가능: {list(predictors)}"
        )
    return cls(params)
