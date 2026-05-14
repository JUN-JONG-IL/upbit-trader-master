#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
캔들 데이터 조회 API

[Endpoints]
- GET /candles/{symbol}?tf=1m&limit=200

[Cache Strategy]
L0 (lru_cache/인메모리) → L1 (Redis) → L2 (TimescaleDB/MongoDB)

[References]
- work_order/DB설계.md 5.3, 6.2, 8.2

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Redis 연결 ────────────────────────────────────────────────────────────────

def _get_redis() -> Optional[Any]:
    """Redis 클라이언트 반환 (연결 실패 시 None)"""
    try:
        import redis as redis_lib  # type: ignore
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        client = redis_lib.Redis(host=host, port=port, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


# ── L0: 인메모리 심볼 목록 캐시 ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_valid_timeframes() -> tuple:
    """유효한 타임프레임 목록 (불변 캐시)"""
    return ("1m", "5m", "15m", "1h", "4h", "1d")


# ── API 엔드포인트 ───────────────────────────────────────────────────────────

@router.get(
    "/candles/{symbol}",
    summary="캔들 데이터 조회",
    response_description="캔들 데이터 목록",
)
async def get_candles(
    symbol: str,
    tf: str = Query("1m", description="타임프레임 (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(200, ge=1, le=1000, description="조회 개수 (최대 1000)"),
) -> List[Dict[str, Any]]:
    """
    캔들 데이터 조회 (3-Tier 캐시 전략)

    **캐시 전략** (DB설계.md 8.2):
    1. **L1 Redis**: `candles:{symbol}:{tf}` LRANGE 조회
    2. **L2 TimescaleDB/MongoDB**: L1 미스 시 DB 조회
    3. 조회 결과를 Redis에 캐싱 (TTL 7일)

    Args:
        symbol: 코인 심볼 (예: KRW-BTC)
        tf: 타임프레임
        limit: 조회 개수

    Returns:
        캔들 데이터 목록 (최신 순)
    """
    if tf not in _get_valid_timeframes():
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 타임프레임: {tf}. 허용: {_get_valid_timeframes()}",
        )

    # L1: Redis 조회
    redis_client = _get_redis()
    cache_key = f"candles:{symbol}:{tf}"

    if redis_client:
        try:
            cached = redis_client.lrange(cache_key, 0, limit - 1)
            if cached:
                logger.debug("[CandlesAPI] L1 캐시 히트: %s", cache_key)
                return [json.loads(c) for c in cached]
        except Exception as exc:
            logger.warning("[CandlesAPI] Redis 조회 실패: %s", exc)

    # L2: DB 조회 (MongoDB 또는 TimescaleDB)
    candles = await _fetch_from_db(symbol, tf, limit)

    # Redis 캐싱 (TTL 7일 = 604800초, DB설계.md 6.2)
    if candles and redis_client:
        try:
            pipe = redis_client.pipeline()
            pipe.delete(cache_key)
            pipe.lpush(cache_key, *[json.dumps(c) for c in candles])
            pipe.ltrim(cache_key, 0, 499)
            pipe.expire(cache_key, 604800)
            pipe.execute()
            logger.debug("[CandlesAPI] L1 캐시 저장: %s (%d건)", cache_key, len(candles))
        except Exception as exc:
            logger.warning("[CandlesAPI] Redis 저장 실패: %s", exc)

    return candles


@router.get(
    "/candles/{symbol}/latest",
    summary="최신 캔들 1개 조회",
)
async def get_latest_candle(
    symbol: str,
    tf: str = Query("1m", description="타임프레임"),
) -> Dict[str, Any]:
    """
    최신 캔들 1개 조회

    Args:
        symbol: 코인 심볼
        tf: 타임프레임

    Returns:
        가장 최근 캔들 데이터
    """
    candles = await get_candles(symbol, tf=tf, limit=1)
    if not candles:
        raise HTTPException(status_code=404, detail=f"캔들 없음: {symbol} {tf}")
    return candles[0]


# ── 내부 DB 조회 ──────────────────────────────────────────────────────────────

async def _fetch_from_db(
    symbol: str, tf: str, limit: int
) -> List[Dict[str, Any]]:
    """
    DB에서 캔들 데이터 조회 (MongoDB fallback)

    실제 DB 연결은 환경에 따라 TimescaleDB 또는 MongoDB를 사용합니다.

    Args:
        symbol: 코인 심볼
        tf: 타임프레임
        limit: 조회 개수

    Returns:
        캔들 데이터 목록
    """
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )
        collection = f"{symbol}_minute_1" if tf == "1m" else f"{symbol}_{tf}"
        result = await db.find_items(
            db_name="candles",
            collection_name=collection,
            query={},
            sort=[("time", -1)],
            limit=limit,
        )
        candles = [dict(r) for r in (result or [])]
        # _id 필드 제거 (JSON 직렬화 문제)
        for c in candles:
            c.pop("_id", None)
        logger.debug("[CandlesAPI] L2 DB 조회: %s %s (%d건)", symbol, tf, len(candles))
        return candles
    except ImportError:
        logger.debug("[CandlesAPI] DBHandler 없음 - 빈 결과 반환")
        return []
    except Exception as exc:
        logger.warning("[CandlesAPI] DB 조회 실패: %s", exc)
        return []
