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
