"""
src/ai/models/lightgbm_shap.py

LightGBM 모델 + SHAP 해석 모듈
용도: 시장 예측 모델의 특성 중요도 분석 및 설명 가능한 AI 제공

의존성:
  pip install lightgbm>=4.6.0 shap>=0.43.0 numpy pandas
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LGB_AVAILABLE = False

try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SHAP_AVAILABLE = False


class LightGBMSHAP:
    """LightGBM 모델 + SHAP 해석"""

    def __init__(self, params: dict | None = None) -> None:
        if not _LGB_AVAILABLE:
            raise ImportError(
                "lightgbm 패키지가 필요합니다. pip install lightgbm>=4.6.0"
            )
        self.params: dict = params or {
            "objective": "regression",
            "metric": "rmse",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "verbose": -1,
        }
        self.model: lgb.Booster | None = None
        self.explainer: shap.TreeExplainer | None = None

    # ------------------------------------------------------------------
    # 학습
    # ------------------------------------------------------------------

    def train(
        self,
        X_train: pd.DataFrame | np.ndarray,
        y_train: pd.Series | np.ndarray,
        X_val: pd.DataFrame | np.ndarray | None = None,
        y_val: pd.Series | np.ndarray | None = None,
    ) -> lgb.Booster:
        """
        모델 학습

        Args:
            X_train: 학습 특성
            y_train: 학습 레이블
            X_val  : 검증 특성 (선택)
            y_val  : 검증 레이블 (선택)

        Returns:
            학습된 LightGBM Booster
        """
        train_data = lgb.Dataset(X_train, label=y_train)

        if X_val is not None and y_val is not None:
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
            self.model = lgb.train(
                self.params,
                train_data,
                num_boost_round=1000,
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )
        else:
            self.model = lgb.train(
                self.params,
                train_data,
                num_boost_round=1000,
            )

        # SHAP Explainer 초기화
        if _SHAP_AVAILABLE:
            self.explainer = shap.TreeExplainer(self.model)

        return self.model

    # ------------------------------------------------------------------
    # 추론
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """
        예측값 반환

        Args:
            X: 입력 특성

        Returns:
            예측값 배열
        """
        if self.model is None:
            raise RuntimeError("모델을 먼저 학습시켜 주세요 (train 호출).")
        return self.model.predict(X)

    # ------------------------------------------------------------------
    # SHAP 해석
    # ------------------------------------------------------------------

    def explain(
        self, X_sample: pd.DataFrame | np.ndarray
    ) -> np.ndarray:
        """
        SHAP 값 계산

        Args:
            X_sample: 설명할 샘플 데이터

        Returns:
            SHAP 값 행렬 (n_samples × n_features)
        """
        if not _SHAP_AVAILABLE:
            raise ImportError(
                "shap 패키지가 필요합니다. pip install shap>=0.43.0"
            )
        if self.model is None:
            raise RuntimeError("모델을 먼저 학습시켜 주세요 (train 호출).")
        if self.explainer is None:
            self.explainer = shap.TreeExplainer(self.model)

        return self.explainer.shap_values(X_sample)

    def plot_importance(
        self,
        X_sample: pd.DataFrame | np.ndarray,
        max_display: int = 20,
    ) -> None:
        """
        SHAP Feature Importance 플롯 (beeswarm / summary plot)

        Args:
            X_sample   : 설명할 샘플 (보통 100~500개 권장)
            max_display: 표시할 최대 특성 수
        """
        shap_values = self.explain(X_sample)
        shap.summary_plot(shap_values, X_sample, max_display=max_display)

    def plot_waterfall(
        self, X_single: pd.DataFrame | np.ndarray
    ) -> None:
        """
        단일 예측 SHAP Waterfall 플롯

        Args:
            X_single: 단일 샘플 (1행 DataFrame 또는 2-D array[1, n_features])
        """
        if not _SHAP_AVAILABLE:
            raise ImportError(
                "shap 패키지가 필요합니다. pip install shap>=0.43.0"
            )
        shap_values = self.explain(X_single)
        base = (
            self.explainer.expected_value
            if self.explainer is not None
            else 0.0
        )
        data = (
            X_single.iloc[0]
            if isinstance(X_single, pd.DataFrame)
            else X_single[0]
        )
        shap.waterfall_plot(
            shap.Explanation(
                values=shap_values[0],
                base_values=base,
                data=data,
            )
        )

    def feature_importance_df(
        self, X_sample: pd.DataFrame | np.ndarray
    ) -> pd.DataFrame:
        """
        특성별 평균 |SHAP| 값을 DataFrame으로 반환

        Args:
            X_sample: 설명할 샘플

        Returns:
            columns=['feature', 'importance'] (내림차순 정렬)
        """
        shap_values = self.explain(X_sample)
        importance = np.abs(shap_values).mean(axis=0)

        if isinstance(X_sample, pd.DataFrame):
            features = list(X_sample.columns)
        else:
            features = [f"f{i}" for i in range(shap_values.shape[1])]

        df = pd.DataFrame({"feature": features, "importance": importance})
        return df.sort_values("importance", ascending=False).reset_index(
            drop=True
        )
