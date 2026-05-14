-- init-db.sql
-- PostgreSQL (TimescaleDB) 초기화 스크립트 (v9.0)
-- 실행 방법: psql -U admin -d upbit -f init-db.sql

-- ============================================================
-- 확장 활성화
-- ============================================================
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================
-- Snowflake ID 시퀀스
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS snowflake_seq START 1;

-- ============================================================
-- Event Store 테이블 (CQRS + Event Sourcing)
-- ============================================================
CREATE TABLE IF NOT EXISTS event_store (
    id          BIGSERIAL PRIMARY KEY,
    aggregate_id TEXT      NOT NULL,
    event_type  TEXT      NOT NULL,
    data        JSONB     NOT NULL,
    version     INT       NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (aggregate_id, version)
);

CREATE INDEX IF NOT EXISTS idx_event_store_aggregate
    ON event_store (aggregate_id, version);

-- ============================================================
-- candles 테이블 (Hash Partition by symbol)
-- ============================================================
CREATE TABLE IF NOT EXISTS candles (
    id           BIGINT      NOT NULL DEFAULT nextval('snowflake_seq'),
    symbol       TEXT        NOT NULL,
    timeframe    TEXT        NOT NULL,
    exchange     TEXT        NOT NULL DEFAULT 'upbit',
    time         TIMESTAMPTZ NOT NULL,
    open         NUMERIC     NOT NULL,
    high         NUMERIC     NOT NULL,
    low          NUMERIC     NOT NULL,
    close        NUMERIC     NOT NULL,
    volume       NUMERIC     NOT NULL DEFAULT 0,
    quote_volume NUMERIC     DEFAULT 0,
    trade_count  INTEGER     DEFAULT 0,
    is_complete  BOOLEAN     DEFAULT FALSE,
    PRIMARY KEY (symbol, time, timeframe)
) PARTITION BY HASH (symbol);

-- 16개 파티션 생성 + Hypertable 변환
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS candles_p%s
             PARTITION OF candles
             FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
            i, i
        );
        EXECUTE format(
            'SELECT create_hypertable(
                ''candles_p%s'',
                ''time'',
                chunk_time_interval => INTERVAL ''1 day'',
                if_not_exists => TRUE
            )',
            i
        );
    END LOOP;
END $$;

-- ============================================================
-- Trade Ledger 테이블 (Double-Entry 복식부기)
-- ============================================================
CREATE TABLE IF NOT EXISTS trade_ledger (
    id             BIGINT      PRIMARY KEY DEFAULT nextval('snowflake_seq'),
    trade_id       BIGINT      NOT NULL,
    entry_type     TEXT        NOT NULL CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    symbol         TEXT        NOT NULL,
    amount         NUMERIC     NOT NULL,
    balance_before NUMERIC     NOT NULL,
    balance_after  NUMERIC     NOT NULL,
    time           TIMESTAMPTZ NOT NULL,
    CONSTRAINT balance_check CHECK (
        (entry_type = 'DEBIT'  AND balance_after = balance_before - amount) OR
        (entry_type = 'CREDIT' AND balance_after = balance_before + amount)
    )
);

CREATE INDEX IF NOT EXISTS idx_trade_ledger_trade_id
    ON trade_ledger (trade_id);

-- ============================================================
-- isolated_candles 테이블 (이상 데이터 격리)
-- ============================================================
CREATE TABLE IF NOT EXISTS isolated_candles (
    id               BIGSERIAL   PRIMARY KEY,
    time             TIMESTAMPTZ NOT NULL,
    symbol           TEXT        NOT NULL,
    timeframe        TEXT        NOT NULL,
    exchange         TEXT        NOT NULL DEFAULT 'upbit',
    open             NUMERIC,
    high             NUMERIC,
    low              NUMERIC,
    close            NUMERIC,
    volume           NUMERIC,
    raw_data         JSONB,
    isolation_reason TEXT        NOT NULL,
    received_at      TIMESTAMPTZ DEFAULT NOW(),
    reviewed         BOOLEAN     DEFAULT FALSE,
    reviewed_at      TIMESTAMPTZ,
    reviewer         TEXT
);

-- ============================================================
-- MLflow 데이터베이스 (MLOps)
-- ============================================================
CREATE DATABASE IF NOT EXISTS mlflow;
