-- TimescaleDB 초기화 스크립트
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS candles_1m (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    quote_volume DOUBLE PRECISION,
    PRIMARY KEY (timestamp, symbol)
);

SELECT create_hypertable('candles_1m', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_1m_symbol_timestamp ON candles_1m (symbol, timestamp DESC);

ALTER TABLE candles_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('candles_1m', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('candles_1m', INTERVAL '180 days', if_not_exists => TRUE);
