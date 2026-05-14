#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터 드리프트 감지 및 자동 재학습 트리거

config.yaml의 ai_ml_features.drift_monitoring.enabled=true 시 활성화.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

LOG = logging.getLogger("timescale.ml.drift_monitor")

try:
    import numpy as np  # type: ignore
    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False


class DriftMonitor:
    """
    통계적 드리프트 감지기.

    PSI(Population Stability Index) 또는 Z-Score 기반으로
    데이터 분포 변화 감지 후 자동 재학습 트리거.

    config.yaml:
        ai_ml_features:
            drift_monitoring:
                enabled: true
                check_interval: "1 day"
    """

    def __init__(self, threshold: float = 0.2, check_interval: str = "1 day"):
        self.threshold = threshold
        self.check_interval = check_interval
        self._reference: Optional[List[float]] = None
        self._last_check: Optional[datetime] = None
        self.drift_count = 0

    def set_reference(self, data: List[float]):
        """기준 분포 설정"""
        self._reference = list(data)
        LOG.info("✅ 드리프트 기준 분포 설정 (%d 샘플)", len(data))

    def check(self, current_data: List[float]) -> Dict[str, Any]:
        """
        현재 데이터와 기준 분포 비교.

        Returns:
            {"drift_detected": bool, "score": float, "action": str}
        """
        if not self._reference or not current_data:
            return {"drift_detected": False, "score": 0.0, "action": "no_reference"}

        score = self._compute_psi(self._reference, current_data)
        drift_detected = score > self.threshold

        if drift_detected:
            self.drift_count += 1
            LOG.warning("⚠️  드리프트 감지! PSI=%.3f (threshold=%.3f)", score, self.threshold)

        self._last_check = datetime.now(timezone.utc)
        return {
            "drift_detected": drift_detected,
            "score": score,
            "threshold": self.threshold,
            "action": "retrain" if drift_detected else "ok",
            "drift_count": self.drift_count,
        }

    def _compute_psi(self, reference: List[float], current: List[float], bins: int = 10) -> float:
        """PSI (Population Stability Index) 계산"""
        if not NUMPY_AVAILABLE:
            # 간단한 평균 차이 기반 대체
            ref_mean = sum(reference) / len(reference) if reference else 0
            cur_mean = sum(current) / len(current) if current else 0
            return abs(ref_mean - cur_mean) / (abs(ref_mean) + 1e-9)
        try:
            ref_arr = np.array(reference)
            cur_arr = np.array(current)
            min_v = min(ref_arr.min(), cur_arr.min())
            max_v = max(ref_arr.max(), cur_arr.max()) + 1e-9
            ref_counts, edges = np.histogram(ref_arr, bins=bins, range=(min_v, max_v))
            cur_counts, _ = np.histogram(cur_arr, bins=edges)
            ref_pct = (ref_counts / len(ref_arr)) + 1e-9
            cur_pct = (cur_counts / len(cur_arr)) + 1e-9
            psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
            return psi
        except Exception as e:
            LOG.debug("PSI 계산 오류: %s", e)
            return 0.0
