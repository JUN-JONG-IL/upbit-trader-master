-- ============================================================
-- 모니터링 스키마 — gap_fill_queue 테이블 생성 및 isolated_candles 확장
-- 버전: v1.0  (DB설계.md 기반)
-- 실행 순서: 00_schema → 01_hypertables → 02_monitoring
-- ============================================================

-- ============================================================
-- 1. gap_fill_queue 테이블 생성 (Gap 백필 작업 큐)
-- ============================================================
CREATE TABLE IF NOT EXISTS gap_fill_queue (
    id              BIGSERIAL       PRIMARY KEY,
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
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (symbol, timeframe, gap_start, gap_end)
);

CREATE INDEX IF NOT EXISTS idx_gap_fill_queue_status
    ON gap_fill_queue (status, priority DESC, gap_seconds DESC);

CREATE INDEX IF NOT EXISTS idx_gap_fill_queue_symbol
    ON gap_fill_queue (symbol, timeframe, status);

COMMENT ON TABLE gap_fill_queue IS '갭 백필 작업 큐 (우선순위 기반)';

-- ============================================================
-- 2. isolated_candles.reason 컬럼 추가 (존재하지 않을 경우만)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'isolated_candles'
          AND column_name = 'reason'
    ) THEN
        ALTER TABLE isolated_candles ADD COLUMN reason TEXT;
        COMMENT ON COLUMN isolated_candles.reason IS '격리 사유';
    END IF;
END
$$;

-- ============================================================
-- 3. 기존 데이터 마이그레이션 (isolation_reason → reason)
-- ============================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'isolated_candles'
          AND column_name = 'isolation_reason'
    ) THEN
        UPDATE isolated_candles SET reason = isolation_reason WHERE reason IS NULL;
    END IF;
END
$$;
