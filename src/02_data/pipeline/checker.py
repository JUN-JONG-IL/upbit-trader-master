"""
src/02_data/pipeline/checker.py
Stage 1: 데이터 존재 확인

캐시 계층 순서:
    L0 – 인메모리 dict (프로세스 내)
    L1 – Redis List (candles:{symbol}:{tf})
    L2 – TimescaleDB (candles 테이블)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 인메모리 L0 캐시 (symbol+tf → last_seen_time)
_l0_cache: dict[str, datetime] = {}


class CandleChecker:
    """캔들 데이터 존재 여부 및 누락 구간을 확인합니다."""

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
    # L0 – 인메모리
    # ------------------------------------------------------------------
    def check_l0(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """L0 인메모리 캐시에서 마지막 확인 시각을 반환합니다."""
        return _l0_cache.get(f"{symbol}:{timeframe}")

    def update_l0(self, symbol: str, timeframe: str, t: datetime) -> None:
        """L0 캐시를 갱신합니다."""
        _l0_cache[f"{symbol}:{timeframe}"] = t

    # ------------------------------------------------------------------
    # L1 – Redis
    # ------------------------------------------------------------------
    async def check_l1(self, symbol: str, timeframe: str) -> Optional[str]:
        """Redis L1 캐시에서 가장 최근 캔들 직렬화 문자열을 반환합니다."""
        if self._redis is None:
            return None
        try:
            items = await self._redis.lrange(f"candles:{symbol}:{timeframe}", 0, 0)
            return items[0] if items else None
        except Exception as exc:
            logger.warning("Redis L1 조회 실패 (%s:%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # L2 – TimescaleDB
    # ------------------------------------------------------------------
    async def check_l2(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """TimescaleDB에서 가장 최근 캔들 시각을 반환합니다."""
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
            logger.warning("TimescaleDB L2 조회 실패 (%s:%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # 누락 구간 계산
    # ------------------------------------------------------------------
    def get_missing_ranges(
        self,
        last_time: datetime,
        now: Optional[datetime] = None,
        timeframe: str = "1m",
    ) -> list[tuple[datetime, datetime]]:
        """
        last_time 이후 누락된 캔들 구간 목록을 반환합니다.
        단순 구현: (last_time, now) 구간 하나를 반환합니다.
        """
        if now is None:
            now = datetime.now(tz=timezone.utc)
        interval = self.TIMEFRAME_SECONDS.get(timeframe, 60)
        gap = (now - last_time).total_seconds()
        if gap < interval:
            return []
        return [(last_time, now)]
