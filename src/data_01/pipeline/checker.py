"""
src/data_01/pipeline/checker.py
Stage 1: ?곗씠??議댁옱 ?뺤씤

罹먯떆 怨꾩링 ?쒖꽌:
    L0 ???몃찓紐⑤━ dict (?꾨줈?몄뒪 ??
    L1 ??Redis List (candles:{symbol}:{tf})
    L2 ??TimescaleDB (candles ?뚯씠釉?
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ?몃찓紐⑤━ L0 罹먯떆 (symbol+tf ??last_seen_time)
_l0_cache: dict[str, datetime] = {}


class CandleChecker:
    """罹붾뱾 ?곗씠??議댁옱 ?щ? 諛??꾨씫 援ш컙???뺤씤?⑸땲??"""

    TIMEFRAME_SECONDS: dict[str, int] = {
        "1s":  1,
        "1m":  60,
        "3m":  180,
        "5m":  300,
        "15m": 900,
        "30m": 1800,
        "1h":  3600,
        "4h":  14400,
        "1d":  86400,
    }

    def __init__(self, timescale_pool=None, redis_client=None) -> None:
        self._pool  = timescale_pool
        self._redis = redis_client

    # ------------------------------------------------------------------
    # L0 ???몃찓紐⑤━
    # ------------------------------------------------------------------
    def check_l0(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """L0 ?몃찓紐⑤━ 罹먯떆?먯꽌 留덉?留??뺤씤 ?쒓컖??諛섑솚?⑸땲??"""
        return _l0_cache.get(f"{symbol}:{timeframe}")

    def update_l0(self, symbol: str, timeframe: str, t: datetime) -> None:
        """L0 罹먯떆瑜?媛깆떊?⑸땲??"""
        _l0_cache[f"{symbol}:{timeframe}"] = t

    # ------------------------------------------------------------------
    # L1 ??Redis
    # ------------------------------------------------------------------
    async def check_l1(self, symbol: str, timeframe: str) -> Optional[str]:
        """Redis L1 罹먯떆?먯꽌 媛??理쒓렐 罹붾뱾 吏곷젹??臾몄옄?댁쓣 諛섑솚?⑸땲??"""
        if self._redis is None:
            return None
        try:
            items = await self._redis.lrange(f"candles:{symbol}:{timeframe}", 0, 0)
            return items[0] if items else None
        except Exception as exc:
            logger.warning("Redis L1 議고쉶 ?ㅽ뙣 (%s:%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # L2 ??TimescaleDB
    # ------------------------------------------------------------------
    async def check_l2(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """TimescaleDB?먯꽌 媛??理쒓렐 罹붾뱾 ?쒓컖??諛섑솚?⑸땲??"""
        if self._pool is None:
            return None
        try:
            row = await self._pool.fetchrow(
                """
                SELECT MAX(time) AS last_time
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                """,
                symbol, timeframe,
            )
            return row["last_time"] if row else None
        except Exception as exc:
            logger.warning("TimescaleDB L2 議고쉶 ?ㅽ뙣 (%s:%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # ?꾨씫 援ш컙 怨꾩궛
    # ------------------------------------------------------------------
    def get_missing_ranges(
        self,
        last_time: datetime,
        now: Optional[datetime] = None,
        timeframe: str = "1m",
    ) -> list[tuple[datetime, datetime]]:
        """
        last_time ?댄썑 ?꾨씫??罹붾뱾 援ш컙 紐⑸줉??諛섑솚?⑸땲??
        ?⑥닚 援ы쁽: (last_time, now) 援ш컙 ?섎굹瑜?諛섑솚?⑸땲??
        """
        if now is None:
            now = datetime.now(tz=timezone.utc)
        interval = self.TIMEFRAME_SECONDS.get(timeframe, 60)
        gap = (now - last_time).total_seconds()
        if gap < interval:
            return []
        return [(last_time, now)]

