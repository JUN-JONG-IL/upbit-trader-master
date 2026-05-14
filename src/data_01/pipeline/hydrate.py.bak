"""
src/02_data/pipeline/hydrate.py
Stage 9: Redis L1 캐시 갱신

TimescaleDB의 최신 캔들 N개를 Redis List에 적재합니다.
키 패턴: candles:{symbol}:{timeframe}
TTL:     604800초 (7일)
최대:    10,000개 (LTRIM)
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
    """TimescaleDB → Redis L1 캐시 워밍 클래스."""

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
        TimescaleDB에서 최신 캔들을 조회하여 Redis에 적재합니다.
        적재된 캔들 수를 반환합니다.
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
        # 오래된 것부터 LPUSH 하면 최신이 인덱스 0에 위치
        for row in reversed(rows):
            pipe.lpush(key, _json_dumps(dict(row)))
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()

        logger.info("L1 캐시 워밍 완료: %s/%s (%d건)", symbol, timeframe, len(rows))
        return len(rows)

    async def hydrate_candle(self, candle: dict) -> None:
        """단건 캔들을 Redis L1 캐시에 추가합니다."""
        symbol    = candle.get("symbol",    "")
        timeframe = candle.get("timeframe", "1m")
        key       = f"candles:{symbol}:{timeframe}"
        data      = _json_dumps(candle)
        pipe = self._redis.pipeline()
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, CANDLE_LIMIT - 1)
        pipe.expire(key, CANDLE_TTL)
        await pipe.execute()
