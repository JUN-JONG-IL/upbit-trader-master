#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 API 엔드포인트

FastAPI 라우터로 우선순위 설정 및 점수 계산 API를 제공합니다.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/priority", tags=["priority"])


# ── 요청/응답 스키마 ─────────────────────────────────────────────────────────

class PrioritySettingsRequest(BaseModel):
    """우선순위 설정 저장 요청"""

    setting_name: str = Field(default="기본 설정", max_length=100)

    volume_enabled: bool = False
    market_cap_enabled: bool = False
    popularity_enabled: bool = False
    new_listings_enabled: bool = False
    volatility_enabled: bool = False
    price_change_enabled: bool = False
    pattern_detection_enabled: bool = False
    social_mentions_enabled: bool = False

    priority_order: List[str] = Field(default_factory=list)
    logic_type: str = Field(default="OR", pattern="^(OR|AND)$")

    @field_validator("priority_order")
    @classmethod
    def validate_order(cls, v: List[str]) -> List[str]:
        allowed = {
            "volume", "market_cap", "popularity", "new_listings",
            "volatility", "price_change", "pattern_detection", "social_mentions",
        }
        invalid = [k for k in v if k not in allowed]
        if invalid:
            raise ValueError(f"허용되지 않은 priority_order 항목: {invalid}")
        return v


class PriorityScoreResponse(BaseModel):
    """우선순위 점수 응답"""

    symbol: str
    exchange: str
    scores: Dict[str, float]
    total_score: float
    weighted_score: float


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.get("/settings", summary="우선순위 설정 조회")
async def get_priority_settings():
    """현재 저장된 우선순위 설정을 반환합니다."""
    try:
        from ..config.priority_config import PriorityConfigManager
        mgr = PriorityConfigManager()
        config = mgr.load()
        return config.to_dict()
    except Exception as exc:
        logger.error("우선순위 설정 조회 실패: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/settings", summary="우선순위 설정 저장")
async def save_priority_settings(body: PrioritySettingsRequest):
    """우선순위 설정을 저장합니다."""
    try:
        from ..config.priority_config import PriorityConfig, PriorityConfigManager
        config = PriorityConfig.from_dict(body.model_dump())
        mgr = PriorityConfigManager()
        mgr.save(config)
        return {"message": "설정이 저장되었습니다.", "setting_name": config.setting_name}
    except Exception as exc:
        logger.error("우선순위 설정 저장 실패: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/scores/{symbol}",
    response_model=PriorityScoreResponse,
    summary="심볼 우선순위 점수 계산",
)
async def get_priority_scores(
    symbol: str,
    exchange: str = Query(default="upbit", description="거래소"),
):
    """특정 심볼의 우선순위 점수를 계산하여 반환합니다."""
    try:
        from ..config.priority_config import PriorityConfigManager
        from ..services.priority_service import PriorityService

        mgr = PriorityConfigManager()
        config = mgr.load()
        service = PriorityService()

        enabled = config.enabled_items()
        scores = await service.calculate_all_scores(symbol, exchange, enabled)
        weighted = service.apply_priority_weights(
            scores, config.priority_order or enabled, config.logic_type
        )
        total = sum(scores.values())

        return PriorityScoreResponse(
            symbol=symbol,
            exchange=exchange,
            scores=scores,
            total_score=total,
            weighted_score=weighted,
        )
    except Exception as exc:
        logger.error("우선순위 점수 계산 실패 (%s): %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/scores", summary="전체 심볼 우선순위 점수 목록")
async def list_priority_scores(
    exchange: str = Query(default="upbit"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """전체 심볼 목록에 대한 우선순위 점수를 반환합니다 (stub)."""
    return {
        "exchange": exchange,
        "limit": limit,
        "scores": [],
        "message": "실제 구현 시 DB에서 캐시된 점수를 반환합니다.",
    }
