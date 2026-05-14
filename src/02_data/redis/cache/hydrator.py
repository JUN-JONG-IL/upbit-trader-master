#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
캐시 갱신기 (Hydrator)

TimescaleDB → Redis L1 캐시 동기화.
DB에서 최근 500개 캔들을 읽어 L1 캐시에 적재.
"""
import logging
from typing import Optional, List, Dict, Any

from .l1_cache import L1Cache

LOG = logging.getLogger("redis.cache.hydrator")


class CacheHydrator:
    """
    DB → L1 캐시 갱신기.
    
    파이프라인 연동:
        Finalizer → notify → Hydrator.hydrate()
    """

    def __init__(self, l1_cache: Optional[L1Cache] = None, pg_pool=None):
        self.l1_cache = l1_cache
        self.pg_pool = pg_pool

    async def hydrate(self, symbol: str, timeframe: str, limit: int = 500) -> int:
        """
        DB에서 최근 캔들을 읽어 L1 캐시에 적재.
        
        Returns:
            적재된 캔들 수
        """
        if not self.pg_pool or not self.l1_cache:
            return 0
        try:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT time, symbol, timeframe, open, high, low, close, volume, seq, trades
                    FROM candles
                    WHERE symbol = $1 AND timeframe = $2
                    ORDER BY time DESC
                    LIMIT $3
                """, symbol, timeframe, limit)
                if not rows:
                    return 0
                candles = [
                    {
                        "time": str(r["time"]),
                        "symbol": r["symbol"],
                        "timeframe": r["timeframe"],
                        "open": r["open"],
                        "high": r["high"],
                        "low": r["low"],
                        "close": r["close"],
                        "volume": r["volume"],
                        "seq": r["seq"],
                        "trades": r["trades"],
                    }
                    for r in rows
                ]
                count = await self.l1_cache.push_batch(symbol, timeframe, candles)
                LOG.info("✅ L1 캐시 갱신: %s %s (%d개)", symbol, timeframe, count)
                return count
        except Exception as e:
            LOG.error("❌ 캐시 갱신 실패: %s %s - %s", symbol, timeframe, e)
            return 0

    async def hydrate_all(self, symbols: List[str], timeframes: List[str], limit: int = 500) -> int:
        """여러 심볼/TF 일괄 갱신"""
        total = 0
        for symbol in symbols:
            for tf in timeframes:
                total += await self.hydrate(symbol, tf, limit)
        return total
