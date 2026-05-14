#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 시스템 통합 테스트

전체 워크플로우를 테스트합니다:
  1. 설정 저장 → 로드
  2. 점수 계산 (UpbitDataProvider mock)
  3. 가중치 적용
  4. 점수 DB 저장 → 조회
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# backend 패키지를 import할 수 있도록 sys.path 설정
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_ROOT))

from backend.models.db_models import Base
from backend.services.priority_service import PriorityService
from backend.services.priority_db_service import PriorityDBService


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def priority_service(db_session):
    return PriorityService(db=db_session)


@pytest.fixture
def db_service(db_session):
    return PriorityDBService(db_session)


def _mock_provider(service: PriorityService, *, volume: float = 500_000.0):
    """UpbitDataProvider를 mock으로 교체 (네트워크 없이 테스트)"""
    service.data_provider.get_volume_24h = AsyncMock(return_value=volume)
    service.data_provider.get_market_cap = AsyncMock(return_value=volume * 1_000_000)
    service.data_provider.get_ticker_data = AsyncMock(
        return_value={"price": 50_000_000.0}
    )
    service.data_provider.get_all_tickers = AsyncMock(return_value=["BTC", "ETH", "XRP"])
    service.data_provider.get_ohlcv = AsyncMock(
        return_value=[
            {"open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000},
            {"open": 105, "high": 115, "low": 100, "close": 110, "volume": 1200},
        ]
    )
    service.data_provider.get_price_change_rate = AsyncMock(return_value=5.0)


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFullWorkflow:
    async def test_save_config_then_calculate_scores(
        self, priority_service, db_service
    ):
        """설정 저장 → 점수 계산 → DB 저장 → 조회"""
        # 1. 설정 저장
        config = {
            "setting_name": "고변동성 전략",
            "volume_enabled": True,
            "volatility_enabled": True,
            "price_change_enabled": True,
            "priority_order": ["volatility", "volume", "price_change"],
            "logic_type": "OR",
        }
        settings = db_service.save_settings(user_id=1, config=config)
        assert settings.id is not None

        # 2. 데이터 제공자 mock
        _mock_provider(priority_service)

        # 3. 점수 계산
        symbol = "BTC"
        scores = await priority_service.calculate_all_scores(
            symbol=symbol,
            exchange="upbit",
            enabled_items=["volume", "volatility", "price_change"],
        )
        assert set(scores.keys()) == {"volume", "volatility", "price_change"}

        # 4. 가중치 적용
        weighted_score = priority_service.apply_priority_weights(
            scores, config["priority_order"], config["logic_type"]
        )

        scores["weighted_score"] = weighted_score
        scores["total_score"] = sum(v for k, v in scores.items()
                                    if k not in ("weighted_score",))

        # 5. DB에 저장
        db_service.save_scores(symbol, "upbit", scores)

        # 6. 조회 확인
        top_symbols = db_service.get_top_symbols("upbit", limit=10)
        assert len(top_symbols) > 0
        assert top_symbols[0].symbol == symbol

    async def test_multiple_symbols_ranked(self, priority_service, db_service):
        """여러 심볼 점수 계산 및 순위 검증"""
        symbols = ["BTC", "ETH", "XRP"]
        volumes = {"BTC": 1_000_000.0, "ETH": 500_000.0, "XRP": 200_000.0}
        all_volumes = list(volumes.values())

        for symbol in symbols:
            priority_service.data_provider.get_volume_24h = AsyncMock(
                return_value=volumes[symbol]
            )
            priority_service.data_provider.get_all_tickers = AsyncMock(
                return_value=symbols
            )
            # mock _get_all_volumes to return fixed list
            from unittest.mock import patch
            with patch.object(
                priority_service,
                "_get_all_volumes",
                AsyncMock(return_value=all_volumes),
            ):
                scores = await priority_service.calculate_all_scores(
                    symbol, "upbit", enabled_items=["volume"]
                )
            scores["total_score"] = scores.get("volume", 0)
            scores["weighted_score"] = scores.get("volume", 0)
            db_service.save_scores(symbol, "upbit", scores)

        top = db_service.get_top_symbols("upbit", limit=3)
        assert len(top) == 3
        # BTC은 거래량이 가장 높으므로 1위여야 함
        assert top[0].symbol == "BTC"

    async def test_settings_load_and_apply(self, priority_service, db_service):
        """설정 저장 후 로드해서 점수 계산에 적용"""
        config = {
            "setting_name": "테스트 전략",
            "volume_enabled": True,
            "volatility_enabled": False,
            "price_change_enabled": True,
            "priority_order": ["volume", "price_change"],
            "logic_type": "AND",
        }
        db_service.save_settings(user_id=1, config=config)

        # 설정 로드
        loaded = db_service.load_settings(user_id=1)
        assert loaded is not None

        # 활성화된 항목 추출
        enabled_items = []
        if loaded.volume_enabled:
            enabled_items.append("volume")
        if loaded.volatility_enabled:
            enabled_items.append("volatility")
        if loaded.price_change_enabled:
            enabled_items.append("price_change")

        assert "volume" in enabled_items
        assert "volatility" not in enabled_items
        assert "price_change" in enabled_items

        # AND 모드에서 score=0인 항목이 있으면 weighted=0
        scores_with_zero = {"volume": 80.0, "price_change": 0.0}
        weighted = priority_service.apply_priority_weights(
            scores_with_zero, loaded.priority_order, loaded.logic_type
        )
        assert weighted == 0.0

    async def test_or_logic_passes_with_some_zeros(
        self, priority_service, db_service
    ):
        """OR 모드: 일부 0 점수가 있어도 총합이 양수"""
        config = {
            "setting_name": "OR 전략",
            "priority_order": ["volume", "market_cap"],
            "logic_type": "OR",
        }
        db_service.save_settings(user_id=1, config=config)
        loaded = db_service.load_settings(user_id=1)

        scores = {"volume": 75.0, "market_cap": 0.0}
        weighted = priority_service.apply_priority_weights(
            scores, loaded.priority_order, loaded.logic_type
        )
        assert weighted > 0.0
