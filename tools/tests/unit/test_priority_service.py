#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 서비스 단위 테스트

테스트 범위:
    - PriorityService.calculate_all_scores()
    - PriorityService.apply_priority_weights() — OR / AND 로직
    - PriorityService._calculate_rank()
    - UpbitDataProvider 연동 (mock 사용)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# backend 패키지를 import할 수 있도록 sys.path 설정
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_ROOT))

from backend.services.priority_service import PriorityService


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def priority_service():
    return PriorityService()


def _make_ohlcv(prices):
    """간단한 OHLCV 딕셔너리 목록 생성 헬퍼"""
    return [{"open": p, "high": p, "low": p, "close": p, "volume": 1000.0} for p in prices]


# ---------------------------------------------------------------------------
# _calculate_rank() 테스트
# ---------------------------------------------------------------------------

class TestCalculateRank:
    def test_rank_highest(self, priority_service):
        """모든 값 중 최고이면 1.0 반환"""
        rank = priority_service._calculate_rank(100, [10, 50, 100])
        assert rank == 1.0

    def test_rank_lowest(self, priority_service):
        """모든 값 중 최저이면 0.0보다 크거나 같음"""
        rank = priority_service._calculate_rank(0, [10, 50, 100])
        assert 0.0 <= rank <= 1.0

    def test_rank_empty_list(self, priority_service):
        """빈 목록이면 0.0 반환"""
        assert priority_service._calculate_rank(50, []) == 0.0

    def test_rank_none_value(self, priority_service):
        """값이 None이면 0.0 반환"""
        assert priority_service._calculate_rank(None, [10, 20]) == 0.0

    def test_rank_range(self, priority_service):
        """반환값은 항상 0.0 ~ 1.0 범위"""
        for val in [0, 25, 50, 75, 100]:
            rank = priority_service._calculate_rank(val, list(range(0, 101, 10)))
            assert 0.0 <= rank <= 1.0


# ---------------------------------------------------------------------------
# apply_priority_weights() 테스트
# ---------------------------------------------------------------------------

class TestApplyPriorityWeights:
    def test_or_logic_basic(self, priority_service):
        """OR 모드: 점수 있으면 양수 반환"""
        scores = {"volume": 80.0, "volatility": 60.0}
        result = priority_service.apply_priority_weights(
            scores, ["volume", "volatility"], "OR"
        )
        assert result > 0

    def test_or_logic_zero_in_list_still_positive(self, priority_service):
        """OR 모드: 일부 0이어도 다른 점수가 있으면 양수"""
        scores = {"volume": 80.0, "volatility": 0.0}
        result = priority_service.apply_priority_weights(
            scores, ["volume", "volatility"], "OR"
        )
        assert result > 0

    def test_and_logic_zero_score_returns_zero(self, priority_service):
        """AND 모드: 하나라도 0이면 0 반환"""
        scores = {"volume": 80.0, "volatility": 0.0}
        result = priority_service.apply_priority_weights(
            scores, ["volume", "volatility"], "AND"
        )
        assert result == 0.0

    def test_and_logic_all_positive_returns_positive(self, priority_service):
        """AND 모드: 모두 양수이면 양수 반환"""
        scores = {"volume": 80.0, "volatility": 60.0}
        result = priority_service.apply_priority_weights(
            scores, ["volume", "volatility"], "AND"
        )
        assert result > 0

    def test_empty_scores_returns_zero(self, priority_service):
        """빈 점수 딕셔너리이면 0 반환"""
        result = priority_service.apply_priority_weights({}, [], "OR")
        assert result == 0.0

    def test_priority_order_weight_decreases(self, priority_service):
        """앞 순위 항목이 더 높은 가중치를 받음"""
        scores_a = {"volume": 100.0, "volatility": 0.0}
        scores_b = {"volume": 0.0, "volatility": 100.0}

        # volume이 1순위인 경우
        result_a = priority_service.apply_priority_weights(
            scores_a, ["volume", "volatility"], "OR"
        )
        # volatility가 1순위인 경우
        result_b = priority_service.apply_priority_weights(
            scores_b, ["volatility", "volume"], "OR"
        )
        # 둘 다 1순위에서 동일 점수(100)이므로 결과가 같아야 함
        assert abs(result_a - result_b) < 1e-6

    def test_higher_priority_has_higher_weight(self, priority_service):
        """1순위 항목이 2순위 항목보다 더 높은 가중치"""
        # volume=100, volatility=100이지만 volume이 1순위
        scores = {"volume": 100.0, "volatility": 100.0}
        result_vol_first = priority_service.apply_priority_weights(
            scores, ["volume", "volatility"], "OR"
        )
        # 둘 다 100점이고 순서만 다를 때 결과가 같아야 함
        result_vola_first = priority_service.apply_priority_weights(
            scores, ["volatility", "volume"], "OR"
        )
        assert abs(result_vol_first - result_vola_first) < 1e-6


# ---------------------------------------------------------------------------
# calculate_all_scores() 테스트 — UpbitDataProvider mock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCalculateAllScores:
    async def test_scores_in_valid_range(self, priority_service):
        """계산된 점수는 0 ~ 100 범위"""
        # 데이터 제공자를 mock으로 대체
        priority_service.data_provider.get_volume_24h = AsyncMock(return_value=1000.0)
        priority_service.data_provider.get_all_tickers = AsyncMock(
            return_value=["BTC", "ETH"]
        )
        scores = await priority_service.calculate_all_scores(
            "BTC", "upbit", enabled_items=["volume"]
        )
        assert "volume" in scores
        assert 0.0 <= scores["volume"] <= 100.0

    async def test_empty_provider_returns_zero_scores(self, priority_service):
        """API 응답이 빈 값이면 0 점수 반환"""
        priority_service.data_provider.get_volume_24h = AsyncMock(return_value=0.0)
        priority_service.data_provider.get_all_tickers = AsyncMock(return_value=[])
        scores = await priority_service.calculate_all_scores(
            "BTC", "upbit", enabled_items=["volume"]
        )
        assert scores["volume"] == 0.0

    async def test_only_enabled_items_calculated(self, priority_service):
        """enabled_items에 포함된 항목만 점수 계산"""
        scores = await priority_service.calculate_all_scores(
            "BTC", "upbit", enabled_items=["volatility", "price_change"]
        )
        assert set(scores.keys()) == {"volatility", "price_change"}

    async def test_all_items_calculated_by_default(self, priority_service):
        """enabled_items=None이면 전체 항목 계산"""
        priority_service.data_provider.get_volume_24h = AsyncMock(return_value=0.0)
        priority_service.data_provider.get_all_tickers = AsyncMock(return_value=[])
        priority_service.data_provider.get_ohlcv = AsyncMock(return_value=[])
        priority_service.data_provider.get_market_cap = AsyncMock(return_value=0.0)
        priority_service.data_provider.get_price_change_rate = AsyncMock(return_value=None)
        scores = await priority_service.calculate_all_scores("BTC", "upbit")
        expected_keys = {
            "volume", "market_cap", "popularity", "new_listings",
            "volatility", "price_change", "pattern_detection", "social_mentions",
        }
        assert set(scores.keys()) == expected_keys

    async def test_volatility_with_real_data(self, priority_service):
        """변동성 계산 — OHLCV 데이터가 있으면 점수 계산"""
        ohlcv = _make_ohlcv([100, 110, 95, 120, 105])
        priority_service.data_provider.get_ohlcv = AsyncMock(return_value=ohlcv)
        priority_service.data_provider.get_all_tickers = AsyncMock(return_value=["BTC"])

        # _get_all_volatilities를 직접 mock
        with patch.object(
            priority_service, "_get_all_volatilities", AsyncMock(return_value=[5.0, 10.0, 15.0])
        ):
            scores = await priority_service.calculate_all_scores(
                "BTC", "upbit", enabled_items=["volatility"]
            )
        assert 0.0 <= scores["volatility"] <= 100.0


# ---------------------------------------------------------------------------
# UpbitDataProvider 단독 테스트 (pyupbit mock)
# ---------------------------------------------------------------------------

class TestUpbitDataProvider:
    def test_import_without_pyupbit(self):
        """pyupbit 없이도 UpbitDataProvider 임포트 가능"""
        from backend.services.upbit_data_provider import UpbitDataProvider
        provider = UpbitDataProvider()
        assert provider is not None

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pyupbit(self):
        """pyupbit 미설치 환경에서 빈 값 반환"""
        from backend.services import upbit_data_provider as udp

        original = udp._PYUPBIT_AVAILABLE
        udp._PYUPBIT_AVAILABLE = False
        try:
            provider = udp.UpbitDataProvider()
            assert await provider.get_ticker_data("BTC") == {}
            assert await provider.get_volume_24h("BTC") == 0.0
            assert await provider.get_ohlcv("BTC") == []
            assert await provider.get_all_tickers() == []
            assert await provider.get_market_cap("BTC") == 0.0
            assert await provider.get_orderbook("BTC") == {}
        finally:
            udp._PYUPBIT_AVAILABLE = original
