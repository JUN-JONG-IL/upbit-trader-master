#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive Base TF (심볼별 최적 타임프레임 자동 선택)

config.yaml의 ai_ml_features.adaptive_tf.enabled=true 시 활성화.
"""
import logging
from typing import Dict, Optional, List

LOG = logging.getLogger("timescale.ml.adaptive_tf")

# 타임프레임 우선순위 (유동성 → 낮은 TF)
_TF_PRIORITY = ["1m", "3m", "5m", "15m", "1h", "4h", "1d"]


class AdaptiveTF:
    """
    심볼별 최적 Base TF 선택기.

    유동성(거래량)이 높은 심볼은 1m,
    저유동성 심볼은 5m~15m 추천.

    config.yaml:
        ai_ml_features:
            adaptive_tf:
                enabled: false
    """

    def __init__(self):
        # symbol → recommended TF 캐시
        self._cache: Dict[str, str] = {}

    def recommend(self, symbol: str, avg_volume_24h: float) -> str:
        """
        평균 24h 거래량 기반 TF 추천.

        Args:
            symbol: 심볼 (예: KRW-BTC)
            avg_volume_24h: 24시간 평균 거래량 (KRW)

        Returns:
            추천 TF 문자열 (예: '1m', '5m')
        """
        if avg_volume_24h >= 1_000_000_000_000:  # 1조 이상
            tf = "1m"
        elif avg_volume_24h >= 100_000_000_000:   # 1천억 이상
            tf = "1m"
        elif avg_volume_24h >= 10_000_000_000:    # 100억 이상
            tf = "3m"
        elif avg_volume_24h >= 1_000_000_000:     # 10억 이상
            tf = "5m"
        else:
            tf = "15m"
        self._cache[symbol] = tf
        LOG.debug("AdaptiveTF: %s → %s (volume=%.0f)", symbol, tf, avg_volume_24h)
        return tf

    def get(self, symbol: str) -> Optional[str]:
        """캐시된 추천 TF 반환"""
        return self._cache.get(symbol)

    def get_all(self) -> Dict[str, str]:
        return dict(self._cache)
