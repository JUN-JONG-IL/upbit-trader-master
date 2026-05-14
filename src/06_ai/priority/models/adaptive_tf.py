#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive TimeFrame 모듈

심볼별 최적 타임프레임을 자동 선택하거나 변동성 기반으로 동적 조정합니다.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 지원 타임프레임 목록 (분 단위)
SUPPORTED_TIMEFRAMES = [1, 3, 5, 10, 15, 30, 60, 240, 1440]


class AdaptiveTimeFrame:
    """Adaptive TimeFrame 선택기"""

    def __init__(self, method: str = "symbol_based") -> None:
        """
        Args:
            method: 'symbol_based' | 'volatility_based' | 'hybrid'
        """
        if method not in ("symbol_based", "volatility_based", "hybrid"):
            raise ValueError(f"지원하지 않는 method: {method}")
        self.method = method
        self._symbol_tf_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_optimal_timeframe(
        self,
        symbol: str,
        price_history: Optional[List[float]] = None,
        volatility: Optional[float] = None,
    ) -> int:
        """심볼에 맞는 최적 타임프레임(분)을 반환합니다."""
        if self.method == "symbol_based":
            return self._select_by_symbol(symbol)
        elif self.method == "volatility_based":
            return self._select_by_volatility(volatility or 0.0)
        else:  # hybrid
            tf_symbol = self._select_by_symbol(symbol)
            if price_history and len(price_history) >= 2:
                vol = self._calc_volatility(price_history)
                tf_vol = self._select_by_volatility(vol)
                # 두 타임프레임의 평균을 가장 가까운 지원 값으로 반올림
                avg = (tf_symbol + tf_vol) / 2
                return self._nearest_timeframe(avg)
            return tf_symbol

    def update_symbol_timeframe(self, symbol: str, timeframe: int) -> None:
        """특정 심볼의 타임프레임을 수동으로 설정합니다."""
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"지원하지 않는 타임프레임: {timeframe}분. "
                f"사용 가능: {SUPPORTED_TIMEFRAMES}"
            )
        self._symbol_tf_cache[symbol] = timeframe
        logger.info("심볼 %s 타임프레임 설정: %d분", symbol, timeframe)

    # ------------------------------------------------------------------
    # 내부 로직
    # ------------------------------------------------------------------

    def _select_by_symbol(self, symbol: str) -> int:
        """캐시에서 심볼의 타임프레임을 반환합니다. 없으면 기본값(60분)."""
        return self._symbol_tf_cache.get(symbol, 60)

    def _select_by_volatility(self, volatility: float) -> int:
        """변동성 크기에 따라 적절한 타임프레임을 선택합니다.

        낮은 변동성 → 긴 타임프레임, 높은 변동성 → 짧은 타임프레임.
        """
        if volatility >= 10.0:
            return 1
        elif volatility >= 5.0:
            return 5
        elif volatility >= 2.0:
            return 15
        elif volatility >= 1.0:
            return 60
        elif volatility >= 0.5:
            return 240
        return 1440

    @staticmethod
    def _calc_volatility(prices: List[float]) -> float:
        """가격 시계열의 변동성(표준편차/평균 * 100)을 계산합니다."""
        if len(prices) < 2:
            return 0.0
        mean = sum(prices) / len(prices)
        if mean == 0:
            return 0.0
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        return (variance ** 0.5) / mean * 100

    @staticmethod
    def _nearest_timeframe(value: float) -> int:
        """value에 가장 가까운 지원 타임프레임을 반환합니다."""
        return min(SUPPORTED_TIMEFRAMES, key=lambda tf: abs(tf - value))
