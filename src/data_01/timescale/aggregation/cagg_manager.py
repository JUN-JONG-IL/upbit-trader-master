#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAGG (Continuous Aggregate) 관리자

- 5m / 15m / 1h / 1d CAGG 생성 및 자동 리프레시 정책 등록
- 점진적(incremental) 리프레시 지원
"""
import logging
from typing import Optional, List

LOG = logging.getLogger("timescale.aggregation.cagg")

CAGG_DEFINITIONS = {
    "cagg_candles_5m":  ("5 minutes",  "5 minutes"),
    "cagg_candles_15m": ("15 minutes", "15 minutes"),
    "cagg_candles_1h":  ("1 hour",     "1 hour"),
    "cagg_candles_1d":  ("1 day",      "1 day"),
}

_CAGG_DDL_TEMPLATE = """
CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name}
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('{bucket}', time) AS bucket,
    symbol,
    timeframe,
    first(open, time)   AS open,
    max(high)           AS high,
    min(low)            AS low,
    last(close, time)   AS close,
    sum(volume)         AS volume,
    count(*)            AS trade_count
FROM candles
GROUP BY bucket, symbol, timeframe
WITH NO DATA;
"""


class CaggManager:
    """CAGG 생성 및 리프레시 정책 관리"""

    def __init__(self, pool=None):
        self.pool = pool

    async def create_all(self, views: Optional[List[str]] = None) -> bool:
        """모든(또는 지정) CAGG 생성"""
        if not self.pool:
            LOG.error("❌ 연결 풀 없음")
            return False
        targets = views or list(CAGG_DEFINITIONS.keys())
        success = True
        for view_name in targets:
            if view_name not in CAGG_DEFINITIONS:
                LOG.warning("Unknown CAGG: %s", view_name)
                continue
            bucket, schedule = CAGG_DEFINITIONS[view_name]
            ddl = _CAGG_DDL_TEMPLATE.format(view_name=view_name, bucket=bucket)
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(ddl)
                    LOG.info("✅ CAGG 생성: %s (bucket=%s)", view_name, bucket)
                    # 리프레시 정책 추가 (이미 있으면 무시)
                    try:
                        await conn.execute(f"""
                            SELECT add_continuous_aggregate_policy('{view_name}',
                                start_offset => INTERVAL '1 month',
                                end_offset   => INTERVAL '1 minute',
                                schedule_interval => INTERVAL '{schedule}',
                                if_not_exists => TRUE)
                        """)
                        LOG.info("✅ 리프레시 정책 등록: %s", view_name)
                    except Exception as e:
                        LOG.debug("리프레시 정책 무시: %s - %s", view_name, e)
            except Exception as e:
                LOG.error("❌ CAGG 생성 실패: %s - %s", view_name, e)
                success = False
        return success

    async def refresh(self, view_name: str, start=None, end=None):
        """CAGG 점진적 리프레시"""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                if start and end:
                    await conn.execute(
                        f"CALL refresh_continuous_aggregate('{view_name}', $1, $2)",
                        start, end,
                    )
                else:
                    await conn.execute(
                        f"CALL refresh_continuous_aggregate('{view_name}', NULL, NULL)"
                    )
                LOG.info("✅ CAGG 리프레시: %s", view_name)
        except Exception as e:
            LOG.error("❌ CAGG 리프레시 실패: %s - %s", view_name, e)

    async def setup_retention(self, table: str = "candles", retention: str = "1 year"):
        """Retention 정책 자동화"""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(f"""
                    SELECT add_retention_policy('{table}',
                        INTERVAL '{retention}',
                        if_not_exists => TRUE)
                """)
                LOG.info("✅ Retention 정책 등록: %s (%s)", table, retention)
        except Exception as e:
            LOG.debug("Retention 정책 무시: %s - %s", table, e)
