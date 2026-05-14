"""
src/data_01/clients/redis_client.py
Redis 비동기 클라이언트 (aioredis / redis.asyncio 기반)

캐시 키 구조:
    candles:{symbol}:{timeframe}  → List, TTL 7일, 최대 10,000개
    gap_fill_queue                → Sorted Set (score = 우선순위)
    timescale:events              → Pub/Sub 전역 채널
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None

CANDLE_TTL    = 604_800  # 7일 (초)
CANDLE_LIMIT  = 10_000   # 최대 캐시 개수 (사용자 설정 10000 지원)
GAP_FILL_QUEUE = "gap_fill_queue"
GLOBAL_CHANNEL = "timescale:events"


def _get_redis_module():
    """redis.asyncio 또는 aioredis 를 동적으로 로드합니다."""
    try:
        import importlib
        redis_mod = importlib.import_module("redis.asyncio")
        return redis_mod
    except Exception:
        pass
    try:
        import aioredis  # type: ignore
        return aioredis
    except ImportError as exc:
        raise ImportError("redis[asyncio] 또는 aioredis 패키지가 필요합니다.") from exc


async def get_redis_client():
    """싱글턴 Redis 클라이언트를 반환합니다."""
    global _client
    if _client is None:
        redis_mod = _get_redis_module()
        host     = os.getenv("REDIS_HOST",     "localhost")
        port     = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD", None) or None
        _client = redis_mod.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            max_connections=50,
        )
        logger.info("Redis 클라이언트 생성 완료 (%s:%d)", host, port)
    return _client


async def close_redis_client() -> None:
    """Redis 연결을 닫습니다."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis 클라이언트 종료")


class RedisClient:
    """Redis L1 캐시 / Pub/Sub / Gap Queue 헬퍼 클래스."""

    def __init__(self, client) -> None:
        self._r = client

    # ------------------------------------------------------------------
    # L1 캐시 (List)
    # ------------------------------------------------------------------
    @staticmethod
    def candle_key(symbol: str, timeframe: str) -> str:
        return f"candles:{symbol}:{timeframe}"

    async def push_candle(self, symbol: str, timeframe: str, data: str) -> None:
        """캔들 직렬화 문자열을 L1 캐시에 추가합니다 (최신 10,000개 유지)."""
        key = self.candle_key(symbol, timeframe)
        pipe = self._r.pipeline()
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 10_000) -> list[str]:
        """L1 캐시에서 캔들 목록을 조회합니다."""
        key = self.candle_key(symbol, timeframe)
        return await self._r.lrange(key, 0, limit - 1)

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------
    async def publish(self, channel: str, message: str) -> None:
        """채널에 메시지를 발행합니다."""
        await self._r.publish(channel, message)

    async def publish_candle(self, symbol: str, timeframe: str, message: str) -> None:
        """심볼별 캔들 채널에 메시지를 발행합니다."""
        channel = f"candles:{symbol}:{timeframe}"
        await self._r.publish(channel, message)

    # ------------------------------------------------------------------
    # Gap Fill Queue (Sorted Set)
    # ------------------------------------------------------------------
    async def enqueue_gap(self, job_json: str, priority: float) -> None:
        """Gap 백필 작업을 우선순위 큐에 등록합니다."""
        await self._r.zadd(GAP_FILL_QUEUE, {job_json: priority})

    async def dequeue_gap(self) -> Optional[str]:
        """우선순위가 가장 높은 Gap 작업을 꺼냅니다."""
        items = await self._r.zpopmax(GAP_FILL_QUEUE, count=1)
        if items:
            return items[0][0] if isinstance(items[0], (list, tuple)) else items[0]
        return None

    async def gap_queue_size(self) -> int:
        """Gap 백필 큐의 대기 작업 수를 반환합니다."""
        return await self._r.zcard(GAP_FILL_QUEUE)
