#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
TimescaleDB/MongoDB → Redis 자동 동기화 워커

[Responsibilities]
- 활성 심볼의 최신 캔들 데이터를 Redis L1 캐시에 동기화 (Hydrate)
- 1분 주기 실행 또는 외부 트리거에 의한 갱신
- candles:{symbol}:{tf} 키에 LPUSH + LTRIM + EXPIRE 적용

[Cache Keys]
- candles:{symbol}:{tf}  → LRANGE 기반 캔들 목록 (TTL 7일)

[References]
- work_order/DB설계.md 6.2 (L1 캐싱)
- work_order/DB설계.md 8.2 (캐시 계층 흐름)

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
_CACHE_LIMIT = 10_000      # Redis에 보관할 최대 캔들 수 (사용자 설정 10,000 지원)
_CACHE_TTL = 604800        # 7일 (초)
_DEFAULT_SYNC_INTERVAL = 60  # 기본 동기화 주기 (초)


class DataSyncWorker:
    """
    TimescaleDB/MongoDB → Redis L1 캐시 동기화 워커

    Attributes:
        sync_interval: 동기화 주기 (초)
        timeframes: 동기화할 타임프레임 목록
    """

    def __init__(
        self,
        sync_interval: int = _DEFAULT_SYNC_INTERVAL,
        timeframes: tuple = _TIMEFRAMES,
    ) -> None:
        self.sync_interval = sync_interval
        self.timeframes = timeframes
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._redis: Optional[Any] = None

    def _get_redis(self) -> Optional[Any]:
        """Redis 클라이언트 반환"""
        if self._redis:
            try:
                self._redis.ping()
                return self._redis
            except Exception:
                self._redis = None

        try:
            import redis as redis_lib  # type: ignore
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            client = redis_lib.Redis(host=host, port=port, decode_responses=True)
            client.ping()
            self._redis = client
            return client
        except Exception as exc:
            logger.debug("[DataSyncWorker] Redis 연결 실패: %s", exc)
            return None

    async def start(self) -> None:
        """워커 시작 (백그라운드 태스크로 동기화 루프 실행)"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("[DataSyncWorker] 시작 (interval=%ds)", self.sync_interval)

    async def stop(self) -> None:
        """워커 중지"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("[DataSyncWorker] 중지됨")

    async def run_once(self) -> int:
        """
        단일 동기화 실행 (스케줄러나 외부 트리거에서 호출)

        Returns:
            동기화된 심볼 수
        """
        return await hydrate_redis(
            timeframes=self.timeframes,
            cache_limit=_CACHE_LIMIT,
            cache_ttl=_CACHE_TTL,
        )

    async def _sync_loop(self) -> None:
        """주기적 동기화 루프"""
        while self._running:
            try:
                start = time.time()
                count = await self.run_once()
                elapsed = time.time() - start
                logger.info(
                    "[DataSyncWorker] 동기화 완료: %d 심볼, %.2fs 소요",
                    count, elapsed,
                )
            except Exception as exc:
                logger.warning("[DataSyncWorker] 동기화 오류: %s", exc)

            await asyncio.sleep(self.sync_interval)


async def hydrate_redis(
    symbols: Optional[List[str]] = None,
    timeframes: tuple = _TIMEFRAMES,
    cache_limit: int = _CACHE_LIMIT,
    cache_ttl: int = _CACHE_TTL,
) -> int:
    """
    Redis L1 캐시에 최신 캔들 데이터 동기화 (Hydrate)

    DB설계.md 6.2: candles:{symbol}:{tf} 키에 LPUSH + LTRIM + EXPIRE

    Args:
        symbols: 동기화할 심볼 목록 (None이면 활성 심볼 전체)
        timeframes: 동기화할 타임프레임 목록
        cache_limit: Redis에 보관할 최대 캔들 수
        cache_ttl: Redis TTL (초)

    Returns:
        동기화된 심볼 수
    """
    redis_client = _get_redis_client()
    if not redis_client:
        logger.warning("[hydrate_redis] Redis 연결 없음 - 동기화 건너뜀")
        return 0

    if symbols is None:
        symbols = await _get_active_symbols()

    if not symbols:
        logger.debug("[hydrate_redis] 활성 심볼 없음")
        return 0

    synced = 0
    for symbol in symbols:
        for tf in timeframes:
            try:
                candles = await _fetch_candles_from_db(symbol, tf, cache_limit)
                if not candles:
                    continue
                cache_key = f"candles:{symbol}:{tf}"
                pipe = redis_client.pipeline()
                pipe.delete(cache_key)
                pipe.lpush(cache_key, *[json.dumps(c) for c in candles])
                pipe.ltrim(cache_key, 0, cache_limit - 1)
                pipe.expire(cache_key, cache_ttl)
                pipe.execute()
                logger.debug("[hydrate_redis] 동기화: %s %s (%d건)", symbol, tf, len(candles))
            except Exception as exc:
                logger.warning("[hydrate_redis] %s %s 실패: %s", symbol, tf, exc)
        synced += 1

    logger.info("[hydrate_redis] %d 심볼 동기화 완료", synced)
    return synced


def _get_redis_client() -> Optional[Any]:
    """Redis 클라이언트 반환 (패키지 레벨)"""
    try:
        import redis as redis_lib  # type: ignore
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        client = redis_lib.Redis(host=host, port=port, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


async def _get_active_symbols() -> List[str]:
    """MongoDB에서 활성 심볼 조회"""
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )
        result = await db.find_items(
            db_name="config",
            collection_name="active_symbols",
            query={"active": True},
        )
        return [r.get("symbol", "") for r in (result or []) if r.get("symbol")]
    except Exception:
        return []


async def _fetch_candles_from_db(
    symbol: str, tf: str, limit: int
) -> List[Dict[str, Any]]:
    """DB에서 캔들 데이터 조회"""
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
        for c in candles:
            c.pop("_id", None)
        return candles
    except Exception as exc:
        logger.debug("[DataSyncWorker] DB 조회 실패 %s %s: %s", symbol, tf, exc)
        return []
