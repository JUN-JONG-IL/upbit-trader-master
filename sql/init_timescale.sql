-- ============================================================
-- 기관급 트레이딩 시스템 - TimescaleDB 메인 스키마
-- 버전: v8.0  (DB설계.md 기반)
-- 실행 순서: 00_schema → 01_hypertables → 02_cagg → 03_policies
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================
-- 1. candles 테이블 (메인 저장소)
-- ============================================================
CREATE TABLE IF NOT EXISTS candles (
    time            TIMESTAMPTZ     NOT NULL,
    symbol          TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,
    exchange        TEXT            NOT NULL DEFAULT 'upbit',
    open            NUMERIC         NOT NULL,
    high            NUMERIC         NOT NULL,
    low             NUMERIC         NOT NULL,
    close           NUMERIC         NOT NULL,
    volume          NUMERIC         NOT NULL DEFAULT 0,
    quote_volume    NUMERIC         NOT NULL DEFAULT 0,
    trade_count     INTEGER         DEFAULT 0,
    is_complete     BOOLEAN         DEFAULT false,
    seq             BIGINT,
    meta            JSONB,
    PRIMARY KEY (symbol, time, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_time
    ON candles (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_candles_timeframe
    ON candles (timeframe, time DESC);

-- ============================================================
-- 2. staging_candles 테이블 (임시 버퍼)
-- ============================================================
CREATE TABLE IF NOT EXISTS staging_candles (
    id              BIGSERIAL       PRIMARY KEY,
    symbol          TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,
    exchange        TEXT            NOT NULL DEFAULT 'upbit',
    time            TIMESTAMPTZ     NOT NULL,
    open            NUMERIC         NOT NULL,
    high            NUMERIC         NOT NULL,
    low             NUMERIC         NOT NULL,
    close           NUMERIC         NOT NULL,
    volume          NUMERIC         DEFAULT 0,
    quote_volume    NUMERIC         DEFAULT 0,
    trade_count     INTEGER         DEFAULT 0,
    is_complete     BOOLEAN         DEFAULT false,
    seq             BIGINT,
    inserted_at     TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staging_inserted
    ON staging_candles (inserted_at);

-- ============================================================
-- 3. isolated_candles 테이블 (이상 데이터 격리)
-- ============================================================
CREATE TABLE IF NOT EXISTS isolated_candles (
    time            TIMESTAMPTZ     NOT NULL,
    symbol          TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    open            NUMERIC,
    high            NUMERIC,
    low             NUMERIC,
    close           NUMERIC,
    volume          NUMERIC,
    quote_volume    NUMERIC,
    raw_data        JSONB,
    isolation_reason TEXT           NOT NULL,
    received_at     TIMESTAMPTZ     DEFAULT NOW(),
    reviewed        BOOLEAN         DEFAULT false,
    reviewed_at     TIMESTAMPTZ,
    reviewer        TEXT
);

-- ============================================================
-- 4. latest_snapshot 테이블 (Gap Detection용)
-- ============================================================
CREATE TABLE IF NOT EXISTS latest_snapshot (
    symbol          TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,
    exchange        TEXT            NOT NULL DEFAULT 'upbit',
    last_candle_time TIMESTAMPTZ    NOT NULL,
    last_price      NUMERIC,
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (symbol, timeframe, exchange)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_time
    ON latest_snapshot (last_candle_time);
-- ============================================================
-- 기관급 트레이딩 시스템 - Hypertable 변환
-- 버전: v8.0  (DB설계.md 기반)
-- 전제: 00_schema.sql 이 먼저 실행되어 있어야 합니다.
-- ============================================================

-- ============================================================
-- candles → Hypertable 변환
-- ============================================================
SELECT create_hypertable(
    'candles',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- ============================================================
-- candles 압축 설정
-- ============================================================
ALTER TABLE candles SET (
    timescaledb.compress          = true,
    timescaledb.compress_segmentby = 'symbol, timeframe'
);

-- ============================================================
-- isolated_candles → Hypertable 변환
-- ============================================================
SELECT create_hypertable(
    'isolated_candles',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);
-- ============================================================
-- 기관급 트레이딩 시스템 - Continuous Aggregates (CAGG)
-- 버전: v8.0  (DB설계.md 기반)
-- 전제: 01_hypertables.sql 이 먼저 실행되어 있어야 합니다.
-- ============================================================

-- ============================================================
-- 5분봉 CAGG  (1m → 5m)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    symbol,
    timeframe,
    exchange,
    first(open,  time)             AS open,
    max(high)                      AS high,
    min(low)                       AS low,
    last(close,  time)             AS close,
    sum(volume)                    AS volume,
    sum(quote_volume)              AS quote_volume
FROM candles
WHERE timeframe = '1m'
GROUP BY bucket, symbol, timeframe, exchange
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'cagg_5m',
    start_offset      => INTERVAL '10 minutes',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists     => TRUE
);

-- ============================================================
-- 1시간봉 CAGG  (1m → 1h)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    symbol,
    timeframe,
    exchange,
    first(open,  time)          AS open,
    max(high)                   AS high,
    min(low)                    AS low,
    last(close,  time)          AS close,
    sum(volume)                 AS volume,
    sum(quote_volume)           AS quote_volume
FROM candles
WHERE timeframe = '1m'
GROUP BY bucket, symbol, timeframe, exchange
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'cagg_1h',
    start_offset      => INTERVAL '2 hours',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists     => TRUE
);

-- ============================================================
-- 1일봉 CAGG  (1m → 1d)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    symbol,
    timeframe,
    exchange,
    first(open,  time)         AS open,
    max(high)                  AS high,
    min(low)                   AS low,
    last(close,  time)         AS close,
    sum(volume)                AS volume,
    sum(quote_volume)          AS quote_volume
FROM candles
WHERE timeframe = '1m'
GROUP BY bucket, symbol, timeframe, exchange
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'cagg_1d',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);
-- ============================================================
-- 기관급 트레이딩 시스템 - 압축 / 보존 정책
-- 버전: v8.0  (DB설계.md 기반)
-- 전제: 02_cagg.sql 이 먼저 실행되어 있어야 합니다.
-- ============================================================

-- ============================================================
-- candles 압축 정책  (7일 후 자동 압축)
-- ============================================================
SELECT add_compression_policy(
    'candles',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================
-- candles 보존 정책  (1년 후 자동 삭제)
-- ============================================================
SELECT add_retention_policy(
    'candles',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- ============================================================
-- isolated_candles 보존 정책  (90일 후 자동 삭제)
-- ============================================================
SELECT add_retention_policy(
    'isolated_candles',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- ============================================================
-- Gap Detection 쿼리 예시  (1분마다 실행)
-- ============================================================
-- SELECT symbol, timeframe, last_candle_time,
--        NOW() - last_candle_time AS gap
-- FROM latest_snapshot
-- WHERE NOW() - last_candle_time > INTERVAL '5 minutes'
--   AND timeframe = '1m'
-- ORDER BY gap DESC;
-- ==============================================================================
-- Hash Partitioning (PostgreSQL / TimescaleDB)
-- v9.0: symbol 기준 16개 파티션
-- ==============================================================================

-- ============================================================================
-- OHLCV 테이블 (16-Way Hash Partitioning by symbol)
-- ============================================================================

DROP TABLE IF EXISTS ohlcv CASCADE;

CREATE TABLE ohlcv (
    id        BIGINT        NOT NULL,
    symbol    VARCHAR(20)   NOT NULL,
    timestamp TIMESTAMPTZ   NOT NULL,
    open      NUMERIC(20,8),
    high      NUMERIC(20,8),
    low       NUMERIC(20,8),
    close     NUMERIC(20,8),
    volume    NUMERIC(30,8),
    PRIMARY KEY (id, symbol)
) PARTITION BY HASH (symbol);

DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS ohlcv_p%s
             PARTITION OF ohlcv
             FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
            i, i
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_ohlcv_timestamp        ON ohlcv (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timestamp ON ohlcv (symbol, timestamp DESC);

COMMENT ON TABLE ohlcv IS '16-way hash partitioned OHLCV data by symbol';

-- ============================================================================
-- ORDERS 테이블 (16-Way Hash Partitioning by symbol)
-- ============================================================================

DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    id         BIGINT        NOT NULL,
    symbol     VARCHAR(20)   NOT NULL,
    order_type VARCHAR(10),
    side       VARCHAR(10),
    price      NUMERIC(20,8),
    quantity   NUMERIC(30,8),
    status     VARCHAR(20),
    created_at TIMESTAMPTZ   DEFAULT NOW(),
    PRIMARY KEY (id, symbol)
) PARTITION BY HASH (symbol);

DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS orders_p%s
             PARTITION OF orders
             FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
            i, i
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at DESC);

COMMENT ON TABLE orders IS '16-way hash partitioned orders by symbol';

-- Hash Partition 테이블 (symbol 기준 16개)
CREATE TABLE IF NOT EXISTS candles_partitioned (
    id          BIGINT        NOT NULL,
    symbol      TEXT          NOT NULL,
    timeframe   TEXT          NOT NULL,
    exchange    TEXT          NOT NULL DEFAULT 'upbit',
    time        TIMESTAMPTZ   NOT NULL,
    open        NUMERIC       NOT NULL,
    high        NUMERIC       NOT NULL,
    low         NUMERIC       NOT NULL,
    close       NUMERIC       NOT NULL,
    volume      NUMERIC       NOT NULL DEFAULT 0,
    quote_volume NUMERIC      DEFAULT 0,
    trade_count INTEGER       DEFAULT 0,
    is_complete BOOLEAN       DEFAULT FALSE,
    seq         BIGINT,
    meta        JSONB,
    PRIMARY KEY (symbol, time, timeframe)
) PARTITION BY HASH (symbol);

-- 16개 파티션 생성 및 Hypertable 변환
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS candles_p%s
             PARTITION OF candles_partitioned
             FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
            i, i
        );
        -- TimescaleDB Hypertable 변환 (TimescaleDB 설치 시)
        BEGIN
            PERFORM create_hypertable(
                format('candles_p%s', i),
                'time',
                chunk_time_interval => INTERVAL '1 day',
                if_not_exists       => TRUE
            );
        EXCEPTION WHEN OTHERS THEN
            -- create_hypertable 사용 불가 시 (일반 PostgreSQL) 건너뜀
            NULL;
        END;
    END LOOP;
END $$;

-- 파티션별 인덱스 (시간 + 심볼 복합 인덱스)
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS candles_p%s_symbol_time_idx
             ON candles_p%s (symbol, time DESC)',
            i, i
        );
    END LOOP;
END $$;

-- 분산 현황 조회 뷰
CREATE OR REPLACE VIEW partition_distribution AS
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size,
    (
        SELECT reltuples::BIGINT
        FROM   pg_class
        WHERE  relname = tablename
    ) AS estimated_row_count
FROM   pg_tables
WHERE  tablename LIKE 'candles_p%'
ORDER  BY tablename;
