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
