-- ============================================================
-- 디스크 용량 최적화 - 압축/보존 정책 강화
-- 버전: v1.0  (issue: 디스크 용량 최적화 + 데이터 수집 설정 UI)
-- 전제: 03_policies.sql 이 먼저 실행되어 있어야 합니다.
-- 목표: 75% → 90% 압축률 향상, 7일 → 1일 후 압축
-- ============================================================

-- ============================================================
-- candles 압축 설정 강화 (columnar compression)
-- ============================================================
ALTER TABLE candles SET (
    timescaledb.compress = true,
    timescaledb.compress_segmentby = 'symbol, timeframe',
    timescaledb.compress_orderby = 'time DESC'
);

-- ============================================================
-- 기존 정책 제거 후 신규 정책 적용
-- ============================================================

-- 기존 압축 정책 제거
SELECT remove_compression_policy('candles', if_exists => true);

-- 신규 압축 정책: 1일 후 즉시 압축 (기존 7일 → 1일)
SELECT add_compression_policy(
    'candles',
    INTERVAL '1 day',
    if_not_exists => TRUE
);

-- 기존 보존 정책 제거
SELECT remove_retention_policy('candles', if_exists => true);

-- 신규 보존 정책: 90일 후 삭제 (기존 1년 → 3개월)
SELECT add_retention_policy(
    'candles',
    INTERVAL '90 days',
    if_not_exists => TRUE
);
