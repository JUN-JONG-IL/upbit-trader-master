#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 DB 서비스

SQLAlchemy Session을 통해 우선순위 설정 및 심볼 점수를 DB에 저장/조회합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.db_models import PrioritySettings, SymbolPriorityScores

logger = logging.getLogger(__name__)


class PriorityDBService:
    """우선순위 설정 및 점수 DB 서비스"""

    def __init__(self, db: Session) -> None:
        """
        Args:
            db: SQLAlchemy Session 인스턴스
        """
        self.db = db

    # ------------------------------------------------------------------
    # 설정 저장/로드
    # ------------------------------------------------------------------

    def save_settings(self, user_id: int, config: dict) -> PrioritySettings:
        """우선순위 설정을 DB에 저장합니다.

        이미 동일한 user_id의 활성 설정이 있으면 비활성화 후 새 레코드를 삽입합니다.

        Args:
            user_id: 사용자 ID
            config: 설정 딕셔너리 (PriorityConfig.to_dict() 형식)

        Returns:
            저장된 PrioritySettings 인스턴스
        """
        # 기존 활성 설정 비활성화
        self.db.query(PrioritySettings).filter(
            PrioritySettings.user_id == user_id,
            PrioritySettings.is_active.is_(True),
        ).update({"is_active": False})

        settings = PrioritySettings(
            user_id=user_id,
            setting_name=config.get("setting_name", "기본 설정"),
            volume_enabled=config.get("volume_enabled", False),
            market_cap_enabled=config.get("market_cap_enabled", False),
            popularity_enabled=config.get("popularity_enabled", False),
            new_listings_enabled=config.get("new_listings_enabled", False),
            volatility_enabled=config.get("volatility_enabled", False),
            price_change_enabled=config.get("price_change_enabled", False),
            pattern_detection_enabled=config.get("pattern_detection_enabled", False),
            social_mentions_enabled=config.get("social_mentions_enabled", False),
            priority_order=config.get("priority_order", []),
            logic_type=config.get("logic_type", "OR"),
            is_active=True,
        )

        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        logger.info(
            "우선순위 설정 저장 완료: user_id=%s, id=%s, name=%s",
            user_id,
            settings.id,
            settings.setting_name,
        )
        return settings

    def load_settings(
        self, user_id: int, setting_name: Optional[str] = None
    ) -> Optional[PrioritySettings]:
        """DB에서 활성 우선순위 설정을 로드합니다.

        Args:
            user_id: 사용자 ID
            setting_name: 설정 이름 (None이면 가장 최근 활성 설정 반환)

        Returns:
            PrioritySettings 인스턴스 또는 None
        """
        query = self.db.query(PrioritySettings).filter(
            PrioritySettings.user_id == user_id,
            PrioritySettings.is_active.is_(True),
        )
        if setting_name:
            query = query.filter(PrioritySettings.setting_name == setting_name)
        return query.order_by(PrioritySettings.id.desc()).first()

    def list_settings(self, user_id: int) -> List[PrioritySettings]:
        """사용자의 모든 설정 목록을 반환합니다."""
        return (
            self.db.query(PrioritySettings)
            .filter(PrioritySettings.user_id == user_id)
            .order_by(PrioritySettings.id.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # 점수 저장/조회
    # ------------------------------------------------------------------

    def save_scores(
        self,
        symbol: str,
        exchange: str,
        scores: dict,
        expires_hours: int = 1,
    ) -> SymbolPriorityScores:
        """심볼 우선순위 점수를 DB에 저장합니다.

        Args:
            symbol: 심볼 (예: "BTC")
            exchange: 거래소 (예: "upbit")
            scores: 점수 딕셔너리
            expires_hours: 만료 시간 (시간 단위, 기본 1시간)

        Returns:
            저장된 SymbolPriorityScores 인스턴스
        """
        now = datetime.now()
        score_record = SymbolPriorityScores(
            exchange=exchange,
            symbol=symbol,
            volume_score=scores.get("volume", 0),
            market_cap_score=scores.get("market_cap", 0),
            popularity_score=scores.get("popularity", 0),
            new_listing_score=scores.get("new_listings", 0),
            volatility_score=scores.get("volatility", 0),
            price_change_score=scores.get("price_change", 0),
            pattern_score=scores.get("pattern_detection", 0),
            social_score=scores.get("social_mentions", 0),
            total_score=scores.get("total_score", 0),
            weighted_score=scores.get("weighted_score", 0),
            calculated_at=now,
            expires_at=now + timedelta(hours=expires_hours),
        )

        self.db.add(score_record)
        self.db.commit()
        self.db.refresh(score_record)
        logger.debug(
            "점수 저장: exchange=%s, symbol=%s, total=%.2f",
            exchange,
            symbol,
            float(score_record.total_score or 0),
        )
        return score_record

    def get_top_symbols(
        self, exchange: str = "upbit", limit: int = 50
    ) -> List[SymbolPriorityScores]:
        """우선순위 상위 심볼 목록을 조회합니다.

        만료되지 않은 점수 중 total_score 기준 내림차순으로 반환합니다.

        Args:
            exchange: 거래소 (예: "upbit")
            limit: 최대 반환 수

        Returns:
            SymbolPriorityScores 목록
        """
        return (
            self.db.query(SymbolPriorityScores)
            .filter(
                SymbolPriorityScores.exchange == exchange,
                SymbolPriorityScores.expires_at > datetime.now(),
            )
            .order_by(SymbolPriorityScores.total_score.desc())
            .limit(limit)
            .all()
        )

    def get_symbol_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> Optional[SymbolPriorityScores]:
        """특정 심볼의 최신 점수를 조회합니다."""
        return (
            self.db.query(SymbolPriorityScores)
            .filter(
                SymbolPriorityScores.exchange == exchange,
                SymbolPriorityScores.symbol == symbol,
                SymbolPriorityScores.expires_at > datetime.now(),
            )
            .order_by(SymbolPriorityScores.calculated_at.desc())
            .first()
        )
