-- =============================================================================
-- TimescaleDB 초기화 스크립트
-- 목적: Hypertable + 16-Way Hash Partitioning 설정
-- 버전: v8.0
-- 실행: docker exec -i upbit-timescaledb psql -U postgres -d trading < init_timescaledb.sql
-- =============================================================================

-- TimescaleDB 확장 활성화
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- 1. 캔들 테이블 (Hypertable + Hash Partitioning)
-- =============================================================================

CREATE TABLE IF NOT EXISTS candles (
    id          BIGINT      NOT NULL,               -- Snowflake ID (분산 채번)
    symbol      TEXT        NOT NULL,               -- 심볼 (예: KRW-BTC)
    symbol_hash INT         GENERATED ALWAYS AS (hashtext(symbol) % 16) STORED,
                                                    -- 16-Way 파티션 키 (자동 계산)
    timeframe   TEXT        NOT NULL,               -- 타임프레임 (1s, 1m, 5m, 1h, 1d ...)
    time        TIMESTAMPTZ NOT NULL,               -- 캔들 시작 시각 (UTC)
    open        NUMERIC(24, 8) NOT NULL,            -- 시가
    high        NUMERIC(24, 8) NOT NULL,            -- 고가
    low         NUMERIC(24, 8) NOT NULL,            -- 저가
    close       NUMERIC(24, 8) NOT NULL,            -- 종가
    volume      NUMERIC(24, 8) NOT NULL DEFAULT 0,  -- 거래량
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 레코드 생성 시각

    PRIMARY KEY (symbol_hash, time, symbol, timeframe)
);

COMMENT ON TABLE candles IS '시계열 캔들 데이터 (TimescaleDB Hypertable)';
COMMENT ON COLUMN candles.id          IS 'Snowflake ID (분산 채번, 정렬 가능)';
COMMENT ON COLUMN candles.symbol_hash IS '심볼 Hash (hashtext % 16) - 파티션 자동 분산';
COMMENT ON COLUMN candles.timeframe   IS '타임프레임: 1s/1m/3m/5m/15m/30m/1h/4h/1d/1w/1M';

-- Hypertable 변환 (시간 기준 + 심볼 Hash 파티셔닝)
-- 1일 청크 단위, 16개 공간 파티션
SELECT create_hypertable(
    'candles',
    'time',
    partitioning_column   => 'symbol_hash',
    number_partitions     => 16,
    chunk_time_interval   => INTERVAL '1 day',
    if_not_exists         => TRUE
);

-- =============================================================================
-- 2. 캔들 테이블 인덱스
-- =============================================================================

-- 심볼 + 타임프레임 + 시간 복합 인덱스 (가장 자주 사용되는 쿼리 패턴)
CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
    ON candles (symbol, timeframe, time DESC);

-- 최신 캔들 빠른 조회
CREATE INDEX IF NOT EXISTS idx_candles_time_desc
    ON candles (time DESC);

-- =============================================================================
-- 3. 압축 정책 (90일 이상 데이터 자동 압축 - 저장 공간 90% 절감)
-- =============================================================================

ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, timeframe',
    timescaledb.compress_orderby   = 'time DESC'
);

SELECT add_compression_policy(
    'candles',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- 4. 보존 정책 (2년 이상 1분봉 자동 삭제)
-- =============================================================================

SELECT add_retention_policy(
    'candles',
    INTERVAL '2 years',
    if_not_exists => TRUE
);

-- =============================================================================
-- 5. Continuous Aggregate (CAGG) - 자동 집계 뷰
-- =============================================================================

-- 5분봉 CAGG (1분봉 → 5분봉 자동 집계)
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    symbol,
    '5m'::TEXT                     AS timeframe,  -- 집계 결과 타임프레임 명시
    first(open, time)              AS open,
    max(high)                      AS high,
    min(low)                       AS low,
    last(close, time)              AS close,
    sum(volume)                    AS volume
FROM candles
WHERE timeframe = '1m'
GROUP BY bucket, symbol
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'candles_5m',
    start_offset  => INTERVAL '1 hour',
    end_offset    => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- 1시간봉 CAGG (1분봉 → 1시간봉 자동 집계)
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    symbol,
    '1h'::TEXT                  AS timeframe,  -- 집계 결과 타임프레임 명시
    first(open, time)           AS open,
    max(high)                   AS high,
    min(low)                    AS low,
    last(close, time)           AS close,
    sum(volume)                 AS volume
FROM candles
WHERE timeframe = '1m'
GROUP BY bucket, symbol
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'candles_1h',
    start_offset  => INTERVAL '2 hours',
    end_offset    => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- =============================================================================
-- 6. Gap 추적 테이블 (누락 캔들 기록)
-- =============================================================================

CREATE TABLE IF NOT EXISTS candle_gaps (
    id          BIGSERIAL   PRIMARY KEY,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    gap_start   TIMESTAMPTZ NOT NULL,  -- 결측 시작 시각
    gap_end     TIMESTAMPTZ NOT NULL,  -- 결측 종료 시각
    gap_minutes NUMERIC     GENERATED ALWAYS AS
                    (EXTRACT(EPOCH FROM (gap_end - gap_start)) / 60) STORED,
    filled      BOOLEAN     NOT NULL DEFAULT FALSE,  -- 백필 완료 여부
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE candle_gaps IS '캔들 Gap(결측) 추적 테이블 - 자동 백필 관리';

CREATE INDEX IF NOT EXISTS idx_gaps_symbol_tf ON candle_gaps (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_gaps_unfilled  ON candle_gaps (filled) WHERE NOT filled;

-- =============================================================================
-- 7. 조회 예시 (주석)
-- =============================================================================

-- 최근 1시간 KRW-BTC 1분봉 조회 (파티션 프루닝 자동 적용)
-- SELECT * FROM candles
-- WHERE symbol = 'KRW-BTC'
--   AND timeframe = '1m'
--   AND time > NOW() - INTERVAL '1 hour'
-- ORDER BY time DESC;

-- 심볼별 Gap 현황
-- SELECT symbol, timeframe, COUNT(*) AS gap_count, SUM(gap_minutes) AS total_gap_min
-- FROM candle_gaps
-- WHERE NOT filled
-- GROUP BY symbol, timeframe
-- ORDER BY total_gap_min DESC;
