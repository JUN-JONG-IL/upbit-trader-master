"""
src/data_01/pipeline/hydrate.py
Stage 9: Redis L1 罹먯떆 媛깆떊

TimescaleDB??理쒖떊 罹붾뱾 N媛쒕? Redis List???곸옱?⑸땲??
???⑦꽩: candles:{symbol}:{timeframe}
TTL:     604800珥?(7??
理쒕?:    10,000媛?(LTRIM)
"""

from __future__ import annotations

import logging

try:
    import orjson  # type: ignore
    def _json_dumps(obj) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    orjson = None  # type: ignore
    import json as _json
    def _json_dumps(obj) -> str:  # type: ignore[misc]
        return _json.dumps(obj, default=str)

logger = logging.getLogger(__name__)

CANDLE_TTL   = 604_800
CANDLE_LIMIT = 10_000


class CacheHydrator:
    """TimescaleDB ??Redis L1 罹먯떆 ?뚮컢 ?대옒??"""

    def __init__(self, pool, redis_client) -> None:
        self._pool  = pool
        self._redis = redis_client

    async def hydrate(
        self,
        symbol: str,
        timeframe: str,
        limit: int = CANDLE_LIMIT,
        exchange: str = "upbit",
    ) -> int:
        """
        TimescaleDB?먯꽌 理쒖떊 罹붾뱾??議고쉶?섏뿬 Redis???곸옱?⑸땲??
        ?곸옱??罹붾뱾 ?섎? 諛섑솚?⑸땲??
        """
        rows = await self._pool.fetch(
            """
            SELECT time, symbol, timeframe, exchange,
                   open, high, low, close, volume, quote_volume,
                   trade_count, is_complete, seq
            FROM candles
            WHERE symbol = $1 AND timeframe = $2 AND exchange = $3
            ORDER BY time DESC
            LIMIT $4
            """,
            symbol, timeframe, exchange, limit,
        )
        if not rows:
            return 0

        key  = f"candles:{symbol}:{timeframe}"
        pipe = self._redis.pipeline()
        # ?ㅻ옒??寃껊???LPUSH ?섎㈃ 理쒖떊???몃뜳??0???꾩튂
        for row in reversed(rows):
            pipe.lpush(key, _json_dumps(dict(row)))
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

        logger.info("L1 罹먯떆 ?뚮컢 ?꾨즺: %s/%s (%d嫄?", symbol, timeframe, len(rows))
        return len(rows)

    async def hydrate_candle(self, candle: dict) -> None:
        """?④굔 罹붾뱾??Redis L1 罹먯떆??異붽??⑸땲??"""
        symbol    = candle.get("symbol",    "")
        timeframe = candle.get("timeframe", "1m")
        key       = f"candles:{symbol}:{timeframe}"
        data      = _json_dumps(candle)
        pipe = self._redis.pipeline()
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

