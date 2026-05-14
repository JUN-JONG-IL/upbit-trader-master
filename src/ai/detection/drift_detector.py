"""
Drift 감지 및 재학습 트리거 모듈

목적: 모델 입력 데이터 분포 변화(Drift) 감지 후
      자동 재학습 트리거 + Evidently HTML 리포트 생성

사용 라이브러리:
  - alibi-detect: 통계적 Drift 감지 (Kolmogorov-Smirnov)
  - evidently:    데이터 드리프트 시각화 리포트

감지 주기: 1주일마다 (또는 이벤트 기반)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    from alibi_detect.cd import TabularDrift
    _ALIBI_AVAILABLE = True
except ImportError:
    _ALIBI_AVAILABLE = False
    logger.warning(
        "alibi-detect 패키지가 없습니다. "
        "pip install alibi-detect 를 실행하세요."
    )

try:
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset
    _EVIDENTLY_AVAILABLE = True
except ImportError:
    _EVIDENTLY_AVAILABLE = False
    logger.warning(
        "evidently 패키지가 없습니다. "
        "pip install evidently 를 실행하세요."
    )

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False


def _to_pandas(df: Any) -> Any:
    """polars/numpy → pandas 변환 (Evidently 필요)"""
    if _POLARS_AVAILABLE and isinstance(df, pl.DataFrame):
        return df.to_pandas()
    if isinstance(df, np.ndarray):
        return pd.DataFrame(df) if _PANDAS_AVAILABLE else df
    return df  # 이미 pandas.DataFrame


class DriftMonitor:
    """
    데이터 드리프트 감지 및 리포트 생성

    Example:
        monitor = DriftMonitor(feature_names=['open','high','low','close','volume'])
        monitor.fit(train_df)

        # 주기적으로 실행 (예: 매주)
        is_drift = monitor.detect(recent_df, report_path='drift_report.html')
        if is_drift:
            print("⚠️ Drift 발견 → 재학습 필요")
    """

    def __init__(
        self,
        feature_names: list[str] | None = None,
        p_val: float = 0.05,
    ):
        """
        초기화

        Args:
            feature_names: 피처 이름 목록 (없으면 자동 생성)
            p_val:         Drift 판단 유의수준 (기본: 0.05)
        """
        self.feature_names = feature_names
        self.p_val = p_val
        self._detector: Any = None
        self._reference_df: Any = None

    def fit(self, reference_df: Any) -> None:
        """
        기준 데이터 학습 (Drift 감지 기준 수립)

        Args:
            reference_df: 기준 데이터 (pandas.DataFrame, polars.DataFrame, 또는 numpy 배열)
        """
        if not _ALIBI_AVAILABLE:
            raise ImportError("alibi-detect 패키지를 설치하세요: pip install alibi-detect")

        self._reference_df = reference_df
        ref_np = self._to_numpy(reference_df)

        # 피처 이름이 없으면 자동 생성
        n_features = ref_np.shape[1] if ref_np.ndim == 2 else 1
        if self.feature_names is None:
            self.feature_names = [f"feature_{i}" for i in range(n_features)]

        self._detector = TabularDrift(
            x_ref=ref_np,
            p_val=self.p_val,
        )
        logger.info("DriftMonitor 기준 데이터 학습 완료 (샘플 %d개)", len(ref_np))

    def detect(
        self,
        current_df: Any,
        report_path: str | None = "drift_report.html",
    ) -> bool:
        """
        현재 데이터의 Drift 감지

        Args:
            current_df:  현재 데이터
            report_path: Evidently HTML 리포트 저장 경로 (None 이면 저장 안 함)

        Returns:
            True = Drift 발견 (재학습 필요), False = 정상
        """
        if self._detector is None:
            raise RuntimeError("먼저 fit() 을 호출하세요.")

        current_np = self._to_numpy(current_df)
        preds = self._detector.predict(current_np)
        is_drift: bool = bool(preds["data"]["is_drift"])

        if is_drift:
            logger.warning("⚠️ Drift 발견! 재학습이 필요합니다.")

            # Evidently HTML 리포트 생성
            if report_path and _EVIDENTLY_AVAILABLE and _PANDAS_AVAILABLE:
                self._generate_report(current_df, report_path)
        else:
            logger.info("✅ Drift 없음 (정상 분포)")

        return is_drift

    def detect_features(self, current_df: Any) -> dict[str, bool]:
        """
        피처별 Drift 감지 결과 반환

        Args:
            current_df: 현재 데이터

        Returns:
            {피처명: Drift여부} 딕셔너리
        """
        if self._detector is None:
            raise RuntimeError("먼저 fit() 을 호출하세요.")

        current_np = self._to_numpy(current_df)
        preds = self._detector.predict(current_np)

        feature_drift = preds["data"].get("is_drift_features", [])
        names = self.feature_names or [f"feature_{i}" for i in range(len(feature_drift))]
        return dict(zip(names, feature_drift))

    def _generate_report(self, current_df: Any, report_path: str) -> None:
        """Evidently 드리프트 리포트 생성"""
        try:
            ref_pd = _to_pandas(self._reference_df)
            cur_pd = _to_pandas(current_df)

            # 컬럼명 정규화
            if self.feature_names and hasattr(ref_pd, "columns"):
                n = min(len(self.feature_names), ref_pd.shape[1])
                col_map = {ref_pd.columns[i]: self.feature_names[i] for i in range(n)}
                ref_pd = ref_pd.rename(columns=col_map)
                cur_pd = cur_pd.rename(columns=col_map)

            report = Report(metrics=[DataDriftPreset()])
            report.run(reference_data=ref_pd, current_data=cur_pd)
            report.save_html(report_path)
            logger.info("Evidently 리포트 저장: %s", report_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("리포트 생성 실패: %s", exc)

    @staticmethod
    def _to_numpy(df: Any) -> np.ndarray:
        """다양한 데이터 타입 → numpy 변환"""
        if isinstance(df, np.ndarray):
            return df
        if _POLARS_AVAILABLE and isinstance(df, pl.DataFrame):
            return df.to_numpy()
        if _PANDAS_AVAILABLE and isinstance(df, pd.DataFrame):
            return df.to_numpy()
        return np.array(df)


if __name__ == "__main__":
    try:
        from alibi_detect.cd import TabularDrift  # noqa: F401

        np.random.seed(42)
        # 기준 데이터 (정상 분포)
        ref = np.random.normal(0, 1, (200, 5)).astype(np.float32)
        # 현재 데이터 (분포 이동 있음)
        current = np.random.normal(0.5, 1.2, (100, 5)).astype(np.float32)

        monitor = DriftMonitor(feature_names=["open", "high", "low", "close", "volume"])
        monitor.fit(ref)

        is_drift = monitor.detect(current, report_path=None)
        print(f"Drift 여부: {is_drift}")
    except ImportError as e:
        print(f"필수 패키지 없음: {e}")
