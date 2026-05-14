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
