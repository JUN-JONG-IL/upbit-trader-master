-- ============================================================
-- 기관급 트레이딩 시스템 - TimescaleDB 메인 스키마
-- 버전: v8.2  (isolated_at, reason, gap_fill_queue 완전 수정)
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

-- flush_staging_to_candles() DISTINCT ON (symbol, timeframe, time) ORDER BY inserted_at DESC 최적화용
CREATE INDEX IF NOT EXISTS idx_staging_symbol_timeframe_time
    ON staging_candles (symbol, timeframe, time, inserted_at DESC);

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
    isolated_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    reason          TEXT,
    received_at     TIMESTAMPTZ     DEFAULT NOW(),
    reviewed        BOOLEAN         DEFAULT false,
    reviewed_at     TIMESTAMPTZ,
    reviewer        TEXT
);

CREATE INDEX IF NOT EXISTS idx_isolated_at ON isolated_candles(isolated_at DESC);
CREATE INDEX IF NOT EXISTS idx_isolated_reason ON isolated_candles(isolation_reason);

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
-- 5. gaps 테이블 (Gap 검출 결과 저장)
-- ============================================================
CREATE TABLE IF NOT EXISTS gaps (
    id             BIGSERIAL    PRIMARY KEY,
    symbol         TEXT         NOT NULL,
    timeframe      TEXT         NOT NULL,
    exchange       TEXT         NOT NULL DEFAULT 'upbit',
    gap_start      TIMESTAMPTZ  NOT NULL,
    gap_end        TIMESTAMPTZ  NOT NULL,
    gap_seconds    BIGINT       NOT NULL,
    priority       FLOAT        NOT NULL DEFAULT 1.0,
    status         TEXT         NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'in_progress', 'resolved', 'failed')),
    retry_count    INTEGER      NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at    TIMESTAMPTZ,
    CONSTRAINT gaps_unique UNIQUE (symbol, timeframe, gap_start)
);

CREATE INDEX IF NOT EXISTS idx_gaps_status_priority
    ON gaps (status, priority DESC, gap_seconds DESC);

CREATE INDEX IF NOT EXISTS idx_gaps_symbol_timeframe
    ON gaps (symbol, timeframe, status);

-- ============================================================
-- 6. gap_fill_queue 테이블 (Gap 백필 작업 큐)
-- ============================================================
CREATE TABLE IF NOT EXISTS gap_fill_queue (
    id              BIGSERIAL       PRIMARY KEY,
    time            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    symbol          TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL DEFAULT '1m',
    gap_start       TIMESTAMPTZ     NOT NULL,
    gap_end         TIMESTAMPTZ     NOT NULL,
    gap_seconds     INTEGER         NOT NULL,
    expected_candles INTEGER        DEFAULT 0,
    priority        NUMERIC(10, 4)  DEFAULT 0 CHECK (priority >= 0),
    status          TEXT            DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'resolved', 'failed')),
    retry_count     INTEGER         DEFAULT 0,
    error_message   TEXT,
    filled_candles  INTEGER         DEFAULT 0,
    -- ──────────────────────────────────────────────────────────────
    -- do_not_retry: 상장 전/폐지 등 영구적으로 백필이 불가능한 갭 표시
    --   • TRUE 인 (symbol,timeframe,gap_start) 는 GapFinder 가 재큐잉 차단
    --   • AutoBackfillManager 가 30일 초과 갭에서 빈 DF 수신 시 자동 마킹
    -- ──────────────────────────────────────────────────────────────
    do_not_retry    BOOLEAN         DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (symbol, timeframe, gap_start, gap_end)
);

-- ──────────────────────────────────────────────────────────────
-- 기존 배포 환경 마이그레이션 (do_not_retry 컬럼 자동 추가)
-- 신규 배포는 위 CREATE TABLE 에 이미 포함되어 있어 no-op.
-- 기존 운영 DB(00_schema.sql 이전 버전이 적용된 상태)는 이 ALTER 가 컬럼을 추가한다.
-- ──────────────────────────────────────────────────────────────
ALTER TABLE gap_fill_queue
    ADD COLUMN IF NOT EXISTS do_not_retry BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_gap_fill_queue_time ON gap_fill_queue(time DESC);
CREATE INDEX IF NOT EXISTS idx_gap_fill_queue_status ON gap_fill_queue(status, priority DESC, gap_seconds DESC);
CREATE INDEX IF NOT EXISTS idx_gap_fill_queue_symbol ON gap_fill_queue(symbol, timeframe, status);