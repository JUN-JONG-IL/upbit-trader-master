"""
src/data_01/clients/redis_client.py
Redis ë¹„ë™ê¸??´ë¼?´ì–¸??(aioredis / redis.asyncio ê¸°ë°˜)

ìºì‹œ ??êµ¬ì¡°:
    candles:{symbol}:{timeframe}  ??List, TTL 7?? ìµœë? 10,000ê°?
    gap_fill_queue                ??Sorted Set (score = ?°ì„ ?œìœ„)
    timescale:events              ??Pub/Sub ?„ì—­ ì±„ë„
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None

CANDLE_TTL    = 604_800  # 7??(ì´?
CANDLE_LIMIT  = 10_000   # ìµœë? ìºì‹œ ê°œìˆ˜ (?¬ìš©???¤ì • 10000 ì§€??
GAP_FILL_QUEUE = "gap_fill_queue"
GLOBAL_CHANNEL = "timescale:events"


def _get_redis_module():
    """redis.asyncio ?ëŠ” aioredis ë¥??™ì ?¼ë¡œ ë¡œë“œ?©ë‹ˆ??"""
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
        raise ImportError("redis[asyncio] ?ëŠ” aioredis ?¨í‚¤ì§€ê°€ ?„ìš”?©ë‹ˆ??") from exc


async def get_redis_client():
    """?±ê???Redis ?´ë¼?´ì–¸?¸ë? ë°˜í™˜?©ë‹ˆ??"""
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
        logger.info("Redis ?´ë¼?´ì–¸???ì„± ?„ë£Œ (%s:%d)", host, port)
    return _client


async def close_redis_client() -> None:
    """Redis ?°ê²°???«ìŠµ?ˆë‹¤."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis ?´ë¼?´ì–¸??ì¢…ë£Œ")


class RedisClient:
    """Redis L1 ìºì‹œ / Pub/Sub / Gap Queue ?¬í¼ ?´ë˜??"""

    def __init__(self, client) -> None:
        self._r = client

    # ------------------------------------------------------------------
    # L1 ìºì‹œ (List)
    # ------------------------------------------------------------------
    @staticmethod
    def candle_key(symbol: str, timeframe: str) -> str:
        return f"candles:{symbol}:{timeframe}"

    async def push_candle(self, symbol: str, timeframe: str, data: str) -> None:
        """ìº”ë“¤ ì§ë ¬??ë¬¸ì?´ì„ L1 ìºì‹œ??ì¶”ê??©ë‹ˆ??(ìµœì‹  10,000ê°?? ì?)."""
        key = self.candle_key(symbol, timeframe)
        pipe = self._r.pipeline()
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 10_000) -> list[str]:
        """L1 ìºì‹œ?ì„œ ìº”ë“¤ ëª©ë¡??ì¡°íšŒ?©ë‹ˆ??"""
        key = self.candle_key(symbol, timeframe)
        return await self._r.lrange(key, 0, limit - 1)

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------
    async def publish(self, channel: str, message: str) -> None:
        """ì±„ë„??ë©”ì‹œì§€ë¥?ë°œí–‰?©ë‹ˆ??"""
        await self._r.publish(channel, message)

    async def publish_candle(self, symbol: str, timeframe: str, message: str) -> None:
        """?¬ë³¼ë³?ìº”ë“¤ ì±„ë„??ë©”ì‹œì§€ë¥?ë°œí–‰?©ë‹ˆ??"""
        channel = f"candles:{symbol}:{timeframe}"
        await self._r.publish(channel, message)

    # ------------------------------------------------------------------
    # Gap Fill Queue (Sorted Set)
    # ------------------------------------------------------------------
    async def enqueue_gap(self, job_json: str, priority: float) -> None:
        """Gap ë°±í•„ ?‘ì—…???°ì„ ?œìœ„ ?ì— ?±ë¡?©ë‹ˆ??"""
        await self._r.zadd(GAP_FILL_QUEUE, {job_json: priority})

    async def dequeue_gap(self) -> Optional[str]:
        """?°ì„ ?œìœ„ê°€ ê°€???’ì? Gap ?‘ì—…??êº¼ëƒ…?ˆë‹¤."""
        items = await self._r.zpopmax(GAP_FILL_QUEUE, count=1)
        if items:
            return items[0][0] if isinstance(items[0], (list, tuple)) else items[0]
        return None

    async def gap_queue_size(self) -> int:
        """Gap ë°±í•„ ?ì˜ ?€ê¸??‘ì—… ?˜ë? ë°˜í™˜?©ë‹ˆ??"""
        return await self._r.zcard(GAP_FILL_QUEUE)

