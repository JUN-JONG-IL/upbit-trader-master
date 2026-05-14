"""
LightGBM + SHAP 기반 Gap 발생 예측 모델

목적: 캔들 Gap(결측) 발생 확률 예측 + SHAP 설명 가능성 제공
Gap: 예상 시각에 캔들이 생성되지 않은 경우 (데이터 공백)

사용 흐름:
  1. train(df) 으로 과거 데이터 학습
  2. predict_with_explanation(X) 으로 확률 + 주요 원인 반환
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    logger.warning("lightgbm 패키지가 없습니다. pip install lightgbm 을 실행하세요.")

try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False
    logger.warning("shap 패키지가 없습니다. pip install shap 을 실행하세요.")

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False

# 학습에 사용할 기본 피처 목록
DEFAULT_FEATURES = ["hour", "day_of_week", "volatility", "volume_ma"]


class GapPredictor:
    """
    Gap 발생 예측 + SHAP 설명 모델

    Example:
        predictor = GapPredictor()
        predictor.train(train_df)
        prob, reasons = predictor.predict_with_explanation([[10, 1, 0.05, 1000]])
        print(f"Gap 확률: {prob:.2%}")
        print(f"주요 원인: {reasons}")
    """

    def __init__(self, features: list[str] | None = None):
        """
        초기화

        Args:
            features: 학습 피처 컬럼명 목록 (None 이면 DEFAULT_FEATURES 사용)
        """
        self.features = features or DEFAULT_FEATURES
        self.model: Any = None
        self.explainer: Any = None

    def train(self, df: Any, label_col: str = "gap_occurred") -> None:
        """
        모델 학습

        Args:
            df:        학습 데이터 (polars.DataFrame 또는 pandas.DataFrame)
            label_col: 타겟 컬럼명 (0/1 이진 분류)
        """
        if not _LGB_AVAILABLE:
            raise ImportError("lightgbm 패키지를 설치하세요: pip install lightgbm")

        # polars → numpy 변환
        if _POLARS_AVAILABLE and isinstance(df, pl.DataFrame):
            X = df.select(self.features).to_numpy()
            y = df[label_col].to_numpy()
        else:
            # pandas.DataFrame 또는 numpy 배열 지원
            X = df[self.features].to_numpy() if hasattr(df, "__getitem__") else np.array(df)
            y = df[label_col].to_numpy() if hasattr(df, "__getitem__") else np.array(label_col)

        train_data = lgb.Dataset(X, label=y, feature_name=self.features)

        params = {
            "objective": "binary",
            "metric": "auc",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "verbose": -1,
        }

        self.model = lgb.train(params, train_data, num_boost_round=100)
        logger.info("LightGBM 학습 완료 (특성 %d개, 샘플 %d개)", len(self.features), len(y))

        # SHAP Explainer 초기화
        if _SHAP_AVAILABLE:
            self.explainer = shap.TreeExplainer(self.model)
        else:
            logger.warning("shap 미설치 → SHAP 설명 비활성화")

    def predict(self, X: Any) -> np.ndarray:
        """
        Gap 발생 확률 예측

        Args:
            X: 피처 배열 (shape: [n_samples, n_features])

        Returns:
            확률 배열 (0.0 ~ 1.0)
        """
        if self.model is None:
            raise RuntimeError("먼저 train() 을 호출하세요.")
        return self.model.predict(X)

    def predict_with_explanation(self, X: Any) -> tuple[float, list[tuple[str, float]]]:
        """
        단일 샘플 예측 + SHAP 설명

        Args:
            X: 피처 배열 (shape: [1, n_features])

        Returns:
            (Gap 발생 확률, 상위 3개 피처 영향도 목록)
            영향도 목록: [(피처명, SHAP값), ...]

        Example:
            prob, reasons = predictor.predict_with_explanation([[10, 1, 0.05, 1000]])
            # Gap 확률: 15.3%
            # 주요 원인: [('volatility', 0.12), ('hour', 0.08), ...]
        """
        if self.model is None:
            raise RuntimeError("먼저 train() 을 호출하세요.")

        X_arr = np.array(X) if not isinstance(X, np.ndarray) else X
        prob = float(self.model.predict(X_arr)[0])

        if self.explainer is None:
            return prob, []

        shap_values = self.explainer.shap_values(X_arr)
        # binary 분류: shap_values 는 shape [n_samples, n_features]
        sample_shap = shap_values[0] if shap_values.ndim == 2 else shap_values

        top_features = sorted(
            zip(self.features, sample_shap),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:3]

        return prob, list(top_features)

    def save(self, path: str) -> None:
        """모델 저장 (LightGBM 기본 형식)"""
        if self.model is None:
            raise RuntimeError("저장할 모델이 없습니다.")
        self.model.save_model(path)
        logger.info("모델 저장: %s", path)

    def load(self, path: str) -> None:
        """모델 로드"""
        if not _LGB_AVAILABLE:
            raise ImportError("lightgbm 패키지를 설치하세요.")
        self.model = lgb.Booster(model_file=path)
        if _SHAP_AVAILABLE:
            self.explainer = shap.TreeExplainer(self.model)
        logger.info("모델 로드: %s", path)


if __name__ == "__main__":
    # 간단한 동작 확인 (더미 데이터)
    import numpy as np

    np.random.seed(42)
    n = 500
    # 더미 피처: [hour, day_of_week, volatility, volume_ma]
    X_train = np.column_stack(
        [
            np.random.randint(0, 24, n),         # hour
            np.random.randint(0, 7, n),           # day_of_week
            np.random.uniform(0, 0.1, n),         # volatility
            np.random.uniform(100, 5000, n),      # volume_ma
        ]
    )
    y_train = (np.random.rand(n) > 0.85).astype(int)  # ~15% Gap 발생

    try:
        import pandas as pd

        df = pd.DataFrame(X_train, columns=DEFAULT_FEATURES)
        df["gap_occurred"] = y_train

        predictor = GapPredictor()
        predictor.train(df)

        prob, reasons = predictor.predict_with_explanation([[10, 1, 0.05, 1000]])
        print(f"Gap 확률: {prob:.2%}")
        print(f"주요 원인: {reasons}")
    except ImportError as e:
        print(f"필수 패키지 없음: {e}")
