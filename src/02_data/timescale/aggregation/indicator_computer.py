#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
지표 계산기 (TimescaleDB 기반)

- CAGG 데이터를 활용한 기술적 지표 계산
- 이동평균(SMA/EMA), RSI, MACD 등
"""
import logging
from typing import Optional, List, Dict, Any

LOG = logging.getLogger("timescale.aggregation.indicator")


class IndicatorComputer:
    """TimescaleDB 기반 기술적 지표 계산기"""

    def __init__(self, pool=None):
        self.pool = pool

    async def compute_sma(
        self, symbol: str, timeframe: str, period: int = 20,
        cagg_view: str = "cagg_candles_5m", limit: int = 10_000
    ) -> List[Dict[str, Any]]:
        """단순이동평균(SMA) 계산"""
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT bucket,
                           AVG(close) OVER (
                               PARTITION BY symbol
                               ORDER BY bucket
                               ROWS BETWEEN {period - 1} PRECEDING AND CURRENT ROW
                           ) AS sma_{period}
                    FROM {cagg_view}
                    WHERE symbol = $1
                    ORDER BY bucket DESC
                    LIMIT $2
                """, symbol, limit)
                return [dict(r) for r in rows]
        except Exception as e:
            LOG.error("SMA 계산 실패: %s", e)
            return []

    async def compute_ema(
        self, symbol: str, timeframe: str, period: int = 20,
        limit: int = 10_000
    ) -> List[Dict[str, Any]]:
        """지수이동평균(EMA) - 원본 캔들 기반"""
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT time, close
                    FROM candles
                    WHERE symbol = $1 AND timeframe = $2
                    ORDER BY time DESC
                    LIMIT $3
                """, symbol, timeframe, limit)
                if not rows:
                    return []
                closes = [float(r["close"]) for r in reversed(rows)]
                k = 2.0 / (period + 1)
                ema = closes[0]
                result = []
                for i, (row, close) in enumerate(zip(reversed(rows), closes)):
                    ema = close * k + ema * (1 - k)
                    result.append({"time": row["time"], "ema": ema})
                return result
        except Exception as e:
            LOG.error("EMA 계산 실패: %s", e)
            return []
