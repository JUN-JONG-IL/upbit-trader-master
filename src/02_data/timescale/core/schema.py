#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimescaleDB DDL 관리 (idempotent)

스키마 생성/검증:
- candles (Hypertable)
- staging_candles
- isolated_candles
- latest_snapshot
"""
import logging
from typing import Optional

LOG = logging.getLogger("timescale.schema")

# DDL 쿼리
DDL_CANDLES = """
CREATE TABLE IF NOT EXISTS candles (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    seq         BIGINT,
    trades      INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""

DDL_STAGING_CANDLES = """
CREATE TABLE IF NOT EXISTS staging_candles (
    id          BIGSERIAL,
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    seq         BIGINT,
    trades      INTEGER,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    processed   BOOLEAN     DEFAULT FALSE
);
"""

DDL_ISOLATED_CANDLES = """
CREATE TABLE IF NOT EXISTS isolated_candles (
    id               BIGSERIAL,
    time             TIMESTAMPTZ NOT NULL,
    symbol           TEXT        NOT NULL,
    timeframe        TEXT        NOT NULL,
    open             DOUBLE PRECISION,
    high             DOUBLE PRECISION,
    low              DOUBLE PRECISION,
    close            DOUBLE PRECISION,
    volume           DOUBLE PRECISION,
    seq              BIGINT,
    payload          JSONB,
    reason           TEXT,
    isolation_reason TEXT,
    isolated_at      TIMESTAMPTZ DEFAULT NOW()
);
"""

DDL_LATEST_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS latest_snapshot (
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,
    last_time       TIMESTAMPTZ,
    last_candle_time TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, timeframe)
);
"""


async def ensure_schema(pool) -> bool:
    """스키마 검증/생성 (idempotent)"""
    if not pool:
        LOG.error("❌ 연결 풀 없음 - 스키마 생성 불가")
        return False
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(DDL_CANDLES)
                await conn.execute(DDL_STAGING_CANDLES)
                await conn.execute(DDL_ISOLATED_CANDLES)
                await conn.execute(DDL_LATEST_SNAPSHOT)
                # hypertable 생성 시도 (이미 있으면 무시)
                try:
                    await conn.execute("""
                        SELECT create_hypertable('candles', 'time',
                            if_not_exists => TRUE,
                            migrate_data => TRUE)
                    """)
                except Exception as e:
                    LOG.debug("hypertable 생성 무시: %s", e)
        LOG.info("✅ TimescaleDB 스키마 검증 완료")
        return True
    except Exception as e:
        LOG.error("❌ 스키마 생성 실패: %s", e)
        return False
