"""
src/data_01/clients/redis_client.py
Redis 鍮꾨룞湲??대씪?댁뼵??(aioredis / redis.asyncio 湲곕컲)

罹먯떆 ??援ъ“:
    candles:{symbol}:{timeframe}  ??List, TTL 7?? 理쒕? 10,000媛?
    gap_fill_queue                ??Sorted Set (score = ?곗꽑?쒖쐞)
    timescale:events              ??Pub/Sub ?꾩뿭 梨꾨꼸
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None

CANDLE_TTL    = 604_800  # 7??(珥?
CANDLE_LIMIT  = 10_000   # 理쒕? 罹먯떆 媛쒖닔 (?ъ슜???ㅼ젙 10000 吏??
GAP_FILL_QUEUE = "gap_fill_queue"
GLOBAL_CHANNEL = "timescale:events"


def _get_redis_module():
    """redis.asyncio ?먮뒗 aioredis 瑜??숈쟻?쇰줈 濡쒕뱶?⑸땲??"""
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
        raise ImportError("redis[asyncio] ?먮뒗 aioredis ?⑦궎吏媛 ?꾩슂?⑸땲??") from exc


async def get_redis_client():
    """?깃???Redis ?대씪?댁뼵?몃? 諛섑솚?⑸땲??"""
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
        logger.info("Redis ?대씪?댁뼵???앹꽦 ?꾨즺 (%s:%d)", host, port)
    return _client


async def close_redis_client() -> None:
    """Redis ?곌껐???レ뒿?덈떎."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis ?대씪?댁뼵??醫낅즺")


class RedisClient:
    """Redis L1 罹먯떆 / Pub/Sub / Gap Queue ?ы띁 ?대옒??"""

    def __init__(self, client) -> None:
        self._r = client

    # ------------------------------------------------------------------
    # L1 罹먯떆 (List)
    # ------------------------------------------------------------------
    @staticmethod
    def candle_key(symbol: str, timeframe: str) -> str:
        return f"candles:{symbol}:{timeframe}"

    async def push_candle(self, symbol: str, timeframe: str, data: str) -> None:
        """罹붾뱾 吏곷젹??臾몄옄?댁쓣 L1 罹먯떆??異붽??⑸땲??(理쒖떊 10,000媛??좎?)."""
        key = self.candle_key(symbol, timeframe)
        pipe = self._r.pipeline()
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 10_000) -> list[str]:
        """L1 罹먯떆?먯꽌 罹붾뱾 紐⑸줉??議고쉶?⑸땲??"""
        key = self.candle_key(symbol, timeframe)
        return await self._r.lrange(key, 0, limit - 1)

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------
    async def publish(self, channel: str, message: str) -> None:
        """梨꾨꼸??硫붿떆吏瑜?諛쒗뻾?⑸땲??"""
        await self._r.publish(channel, message)

    async def publish_candle(self, symbol: str, timeframe: str, message: str) -> None:
        """?щ낵蹂?罹붾뱾 梨꾨꼸??硫붿떆吏瑜?諛쒗뻾?⑸땲??"""
        channel = f"candles:{symbol}:{timeframe}"
        await self._r.publish(channel, message)

    # ------------------------------------------------------------------
    # Gap Fill Queue (Sorted Set)
    # ------------------------------------------------------------------
    async def enqueue_gap(self, job_json: str, priority: float) -> None:
        """Gap 諛깊븘 ?묒뾽???곗꽑?쒖쐞 ?먯뿉 ?깅줉?⑸땲??"""
        await self._r.zadd(GAP_FILL_QUEUE, {job_json: priority})

    async def dequeue_gap(self) -> Optional[str]:
        """?곗꽑?쒖쐞媛 媛???믪? Gap ?묒뾽??爰쇰깄?덈떎."""
        items = await self._r.zpopmax(GAP_FILL_QUEUE, count=1)
        if items:
            return items[0][0] if isinstance(items[0], (list, tuple)) else items[0]
        return None

    async def gap_queue_size(self) -> int:
        """Gap 諛깊븘 ?먯쓽 ?湲??묒뾽 ?섎? 諛섑솚?⑸땲??"""
        return await self._r.zcard(GAP_FILL_QUEUE)

