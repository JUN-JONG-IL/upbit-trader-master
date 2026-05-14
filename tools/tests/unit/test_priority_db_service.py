#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 DB 서비스 단위 테스트

테스트 범위:
    - PriorityDBService.save_settings()
    - PriorityDBService.load_settings()
    - PriorityDBService.list_settings()
    - PriorityDBService.save_scores()
    - PriorityDBService.get_top_symbols()
    - PriorityDBService.get_symbol_score()
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# backend 패키지를 import할 수 있도록 sys.path 설정
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_ROOT))

from backend.models.db_models import Base
from backend.services.priority_db_service import PriorityDBService


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """테스트용 인메모리 SQLite 세션"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def db_service(db_session):
    return PriorityDBService(db_session)


@pytest.fixture
def sample_config():
    return {
        "setting_name": "테스트 설정",
        "volume_enabled": True,
        "market_cap_enabled": False,
        "popularity_enabled": True,
        "new_listings_enabled": False,
        "volatility_enabled": True,
        "price_change_enabled": False,
        "pattern_detection_enabled": False,
        "social_mentions_enabled": False,
        "priority_order": ["volume", "volatility", "popularity"],
        "logic_type": "OR",
    }


# ---------------------------------------------------------------------------
# save_settings / load_settings 테스트
# ---------------------------------------------------------------------------

class TestSaveLoadSettings:
    def test_save_returns_settings_with_id(self, db_service, sample_config):
        """저장 후 id가 할당된 PrioritySettings 반환"""
        saved = db_service.save_settings(user_id=1, config=sample_config)
        assert saved.id is not None
        assert saved.id > 0

    def test_saved_values_match_config(self, db_service, sample_config):
        """저장된 값이 config 딕셔너리와 일치"""
        saved = db_service.save_settings(user_id=1, config=sample_config)
        assert saved.setting_name == sample_config["setting_name"]
        assert saved.volume_enabled == sample_config["volume_enabled"]
        assert saved.volatility_enabled == sample_config["volatility_enabled"]
        assert saved.logic_type == sample_config["logic_type"]
        assert saved.priority_order == sample_config["priority_order"]

    def test_load_returns_saved_settings(self, db_service, sample_config):
        """저장 후 load_settings로 동일 값 로드"""
        db_service.save_settings(user_id=1, config=sample_config)
        loaded = db_service.load_settings(user_id=1)

        assert loaded is not None
        assert loaded.setting_name == sample_config["setting_name"]
        assert loaded.volume_enabled == True
        assert loaded.logic_type == "OR"

    def test_load_returns_none_when_no_settings(self, db_service):
        """저장된 설정이 없으면 None 반환"""
        result = db_service.load_settings(user_id=999)
        assert result is None

    def test_new_save_deactivates_old_settings(self, db_service, sample_config):
        """두 번 저장 시 이전 설정은 비활성화"""
        first = db_service.save_settings(user_id=1, config=sample_config)

        updated_config = dict(sample_config)
        updated_config["setting_name"] = "수정된 설정"
        second = db_service.save_settings(user_id=1, config=updated_config)

        # 최신 설정이 로드되어야 함
        loaded = db_service.load_settings(user_id=1)
        assert loaded.setting_name == "수정된 설정"
        assert loaded.id == second.id

    def test_load_by_setting_name(self, db_service, sample_config):
        """setting_name으로 특정 설정 로드"""
        db_service.save_settings(user_id=1, config=sample_config)
        loaded = db_service.load_settings(user_id=1, setting_name="테스트 설정")
        assert loaded is not None

    def test_load_wrong_setting_name_returns_none(self, db_service, sample_config):
        """존재하지 않는 setting_name으로 로드 시 None 반환"""
        db_service.save_settings(user_id=1, config=sample_config)
        loaded = db_service.load_settings(user_id=1, setting_name="존재하지_않음")
        assert loaded is None

    def test_multiple_users_isolated(self, db_service, sample_config):
        """다른 user_id의 설정은 서로 영향을 주지 않음"""
        db_service.save_settings(user_id=1, config=sample_config)

        config2 = dict(sample_config)
        config2["setting_name"] = "유저2 설정"
        db_service.save_settings(user_id=2, config=config2)

        loaded1 = db_service.load_settings(user_id=1)
        loaded2 = db_service.load_settings(user_id=2)

        assert loaded1.setting_name == "테스트 설정"
        assert loaded2.setting_name == "유저2 설정"

    def test_default_values_used_for_missing_keys(self, db_service):
        """config에 키가 없으면 기본값 사용"""
        minimal_config = {"setting_name": "최소 설정"}
        saved = db_service.save_settings(user_id=1, config=minimal_config)
        assert saved.volume_enabled == False
        assert saved.logic_type == "OR"
        assert saved.priority_order == []

    def test_and_logic_type_saved(self, db_service):
        """AND 로직 타입 저장/로드"""
        config = {"setting_name": "AND 설정", "logic_type": "AND"}
        db_service.save_settings(user_id=1, config=config)
        loaded = db_service.load_settings(user_id=1)
        assert loaded.logic_type == "AND"


# ---------------------------------------------------------------------------
# list_settings 테스트
# ---------------------------------------------------------------------------

class TestListSettings:
    def test_list_empty_when_no_settings(self, db_service):
        """설정이 없으면 빈 목록"""
        assert db_service.list_settings(user_id=1) == []

    def test_list_returns_all_settings(self, db_service, sample_config):
        """모든 저장된 설정 반환"""
        db_service.save_settings(user_id=1, config=sample_config)
        db_service.save_settings(user_id=1, config=dict(sample_config, setting_name="두번째"))
        result = db_service.list_settings(user_id=1)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# save_scores / get_top_symbols 테스트
# ---------------------------------------------------------------------------

class TestSaveScores:
    def test_save_scores_returns_record(self, db_service):
        """점수 저장 후 레코드 반환"""
        scores = {
            "volume": 80.5,
            "volatility": 65.3,
            "total_score": 145.8,
            "weighted_score": 75.2,
        }
        record = db_service.save_scores("BTC", "upbit", scores)
        assert record.id is not None
        assert record.symbol == "BTC"
        assert record.exchange == "upbit"

    def test_saved_scores_match_input(self, db_service):
        """저장된 점수가 입력값과 일치"""
        scores = {
            "volume": 80.0,
            "market_cap": 70.0,
            "volatility": 60.0,
            "total_score": 210.0,
            "weighted_score": 75.0,
        }
        record = db_service.save_scores("ETH", "upbit", scores)
        assert float(record.volume_score) == 80.0
        assert float(record.market_cap_score) == 70.0
        assert float(record.volatility_score) == 60.0
        assert float(record.total_score) == 210.0

    def test_get_top_symbols_returns_symbols(self, db_service):
        """점수 저장 후 get_top_symbols로 조회"""
        db_service.save_scores("BTC", "upbit", {"total_score": 90.0, "weighted_score": 85.0})
        db_service.save_scores("ETH", "upbit", {"total_score": 70.0, "weighted_score": 65.0})

        top = db_service.get_top_symbols("upbit", limit=10)
        assert len(top) == 2

    def test_top_symbols_ordered_by_total_score(self, db_service):
        """total_score 내림차순 정렬 확인"""
        db_service.save_scores("BTC", "upbit", {"total_score": 90.0, "weighted_score": 85.0})
        db_service.save_scores("ETH", "upbit", {"total_score": 70.0, "weighted_score": 65.0})
        db_service.save_scores("XRP", "upbit", {"total_score": 80.0, "weighted_score": 75.0})

        top = db_service.get_top_symbols("upbit", limit=3)
        scores = [float(r.total_score) for r in top]
        assert scores == sorted(scores, reverse=True)

    def test_get_top_symbols_respects_limit(self, db_service):
        """limit 파라미터 적용 확인"""
        for sym in ["BTC", "ETH", "XRP", "SOL", "ADA"]:
            db_service.save_scores(sym, "upbit", {"total_score": 50.0, "weighted_score": 50.0})

        top = db_service.get_top_symbols("upbit", limit=3)
        assert len(top) == 3

    def test_get_top_symbols_exchange_filter(self, db_service):
        """거래소 필터 적용 확인"""
        db_service.save_scores("BTC", "upbit", {"total_score": 80.0, "weighted_score": 75.0})
        db_service.save_scores("BTC", "bithumb", {"total_score": 70.0, "weighted_score": 65.0})

        top_upbit = db_service.get_top_symbols("upbit")
        top_bithumb = db_service.get_top_symbols("bithumb")

        assert all(r.exchange == "upbit" for r in top_upbit)
        assert all(r.exchange == "bithumb" for r in top_bithumb)


# ---------------------------------------------------------------------------
# get_symbol_score 테스트
# ---------------------------------------------------------------------------

class TestGetSymbolScore:
    def test_returns_score_for_symbol(self, db_service):
        """저장된 심볼 점수 조회"""
        db_service.save_scores("BTC", "upbit", {"total_score": 85.0, "weighted_score": 80.0})
        score = db_service.get_symbol_score("BTC", "upbit")
        assert score is not None
        assert score.symbol == "BTC"

    def test_returns_none_for_unknown_symbol(self, db_service):
        """저장되지 않은 심볼은 None 반환"""
        score = db_service.get_symbol_score("UNKNOWN", "upbit")
        assert score is None

    def test_all_score_fields_present(self, db_service):
        """전체 점수 필드가 저장되는지 확인"""
        scores = {
            "volume": 80.0,
            "market_cap": 70.0,
            "popularity": 60.0,
            "new_listings": 50.0,
            "volatility": 40.0,
            "price_change": 30.0,
            "pattern_detection": 20.0,
            "social_mentions": 10.0,
            "total_score": 360.0,
            "weighted_score": 55.0,
        }
        db_service.save_scores("BTC", "upbit", scores)
        score = db_service.get_symbol_score("BTC", "upbit")

        assert float(score.volume_score) == 80.0
        assert float(score.market_cap_score) == 70.0
        assert float(score.popularity_score) == 60.0
        assert float(score.new_listing_score) == 50.0
        assert float(score.volatility_score) == 40.0
        assert float(score.price_change_score) == 30.0
        assert float(score.pattern_score) == 20.0
        assert float(score.social_score) == 10.0
