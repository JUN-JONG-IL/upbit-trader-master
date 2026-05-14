#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drift 모니터링 모듈

Alibi Detect 또는 Evidently AI를 사용하여 데이터 드리프트를 감지합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class DriftMonitorBase:
    """Drift 모니터 기본 클래스"""

    def __init__(self, check_interval: int = 3600) -> None:
        """
        Args:
            check_interval: Drift 체크 주기 (초).
        """
        if check_interval <= 0:
            raise ValueError("check_interval은 양수여야 합니다.")
        self.check_interval = check_interval
        self._last_check: Optional[datetime] = None
        self._reference_data: Optional[np.ndarray] = None

    def set_reference(self, data: np.ndarray) -> None:
        """기준(레퍼런스) 데이터를 설정합니다."""
        self._reference_data = np.asarray(data, dtype=float)
        logger.info("Drift 기준 데이터 설정 완료 (샘플 수: %d)", len(data))

    def should_check(self) -> bool:
        """다음 체크 시간이 됐는지 반환합니다."""
        if self._last_check is None:
            return True
        return datetime.now() >= self._last_check + timedelta(seconds=self.check_interval)

    def check(self, current_data: np.ndarray) -> Dict[str, Any]:
        raise NotImplementedError

    def _mark_checked(self) -> None:
        self._last_check = datetime.now()


class AlibiDriftMonitor(DriftMonitorBase):
    """Alibi Detect 기반 Drift 모니터"""

    def __init__(self, check_interval: int = 3600) -> None:
        super().__init__(check_interval)
        self._detector: Any = None

    def set_reference(self, data: np.ndarray) -> None:
        super().set_reference(data)
        try:
            from alibi_detect.cd import MMDDrift  # type: ignore
            self._detector = MMDDrift(self._reference_data, backend="numpy", p_val=0.05)
            logger.info("Alibi Detect MMDDrift 초기화 완료")
        except ImportError:
            logger.warning("alibi-detect 패키지가 없습니다. 기본 통계 방법을 사용합니다.")
            self._detector = None

    def check(self, current_data: np.ndarray) -> Dict[str, Any]:
        current_data = np.asarray(current_data, dtype=float)
        self._mark_checked()
        try:
            if self._detector is not None:
                result = self._detector.predict(current_data)
                is_drift = bool(result["data"]["is_drift"])
                p_val = float(result["data"].get("p_val", 0.0))
            else:
                is_drift, p_val = self._statistical_drift(current_data)

            logger.info(
                "Alibi Drift 체크 완료 – is_drift=%s, p_val=%.4f", is_drift, p_val
            )
            return {
                "is_drift": is_drift,
                "p_val": p_val,
                "method": "alibi_detect",
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error("Alibi Drift 체크 오류: %s", exc)
            return {"error": str(exc), "checked_at": datetime.now().isoformat()}

    def _statistical_drift(self, current: np.ndarray):
        """KS 검정으로 드리프트를 감지합니다 (alibi-detect 미설치 대체)."""
        from scipy import stats  # type: ignore
        ref = self._reference_data
        if ref is None or len(ref) == 0:
            return False, 1.0
        _, p_val = stats.ks_2samp(ref.ravel(), current.ravel())
        return p_val < 0.05, p_val


class EvidentlyDriftMonitor(DriftMonitorBase):
    """Evidently AI 기반 Drift 모니터 (오픈소스, 실시간 대시보드, 추천)"""

    def __init__(self, check_interval: int = 3600) -> None:
        super().__init__(check_interval)

    def check(self, current_data: np.ndarray) -> Dict[str, Any]:
        current_data = np.asarray(current_data, dtype=float)
        self._mark_checked()
        try:
            import pandas as pd  # type: ignore

            ref = self._reference_data
            if ref is None:
                raise ValueError("기준 데이터가 설정되지 않았습니다.")

            ref_df = pd.DataFrame(ref, columns=[f"f{i}" for i in range(ref.shape[1] if ref.ndim > 1 else 1)])
            cur_df = pd.DataFrame(
                current_data,
                columns=[f"f{i}" for i in range(current_data.shape[1] if current_data.ndim > 1 else 1)],
            )

            try:
                from evidently.report import Report  # type: ignore
                from evidently.metric_preset import DataDriftPreset  # type: ignore
                report = Report(metrics=[DataDriftPreset()])
                report.run(reference_data=ref_df, current_data=cur_df)
                result = report.as_dict()
                drift_info = result.get("metrics", [{}])[0].get("result", {})
                is_drift = bool(drift_info.get("dataset_drift", False))
                drift_share = float(drift_info.get("share_of_drifted_columns", 0.0))
            except ImportError:
                # evidently 없으면 KS 통계 대체
                from scipy import stats  # type: ignore
                _, p_val = stats.ks_2samp(ref_df.values.ravel(), cur_df.values.ravel())
                is_drift = p_val < 0.05
                drift_share = 1.0 - p_val

            logger.info(
                "Evidently Drift 체크 완료 – is_drift=%s, drift_share=%.4f",
                is_drift,
                drift_share,
            )
            return {
                "is_drift": is_drift,
                "drift_share": drift_share,
                "method": "evidently",
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error("Evidently Drift 체크 오류: %s", exc)
            return {"error": str(exc), "checked_at": datetime.now().isoformat()}


def create_drift_monitor(
    monitor_type: str, check_interval: int = 3600
) -> DriftMonitorBase:
    """팩토리 함수: 모니터 타입에 맞는 Drift 모니터를 생성합니다."""
    monitors = {
        "alibi_detect": AlibiDriftMonitor,
        "evidently": EvidentlyDriftMonitor,
    }
    cls = monitors.get(monitor_type)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 모니터 타입: {monitor_type}. 사용 가능: {list(monitors)}"
        )
    return cls(check_interval=check_interval)
