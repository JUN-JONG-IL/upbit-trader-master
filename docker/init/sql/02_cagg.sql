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
