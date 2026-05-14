-- 안전한 isolated_candles -> hypertable 마이그레이션
BEGIN;

-- 1) 새 테이블 생성 (원본에 없는 컬럼은 제외/옵션)
CREATE TABLE IF NOT EXISTS public.isolated_candles_new (
    id BIGSERIAL,
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(64) NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
    open NUMERIC(20,8),
    high NUMERIC(20,8),
    low NUMERIC(20,8),
    close NUMERIC(20,8),
    volume NUMERIC(30,8),
    seq BIGINT,
    exchange VARCHAR(32) DEFAULT 'upbit',
    raw_data JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    isolated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    isolation_reason TEXT NOT NULL,
    reviewed BOOLEAN DEFAULT FALSE,
    CONSTRAINT isolated_candles_new_pkey PRIMARY KEY (id, isolated_at)
);

-- 2) 데이터 복사 (원본의 존재하는 컬럼만 복사; raw_data는 text->jsonb로 안전 변환)
INSERT INTO public.isolated_candles_new (id, time, symbol, timeframe, open, high, low, close, volume, seq, exchange, raw_data, received_at, isolated_at, isolation_reason, reviewed)
SELECT
    id,
    time,
    symbol,
    timeframe,
    open,
    high,
    low,
    close,
    volume,
    seq,
    exchange,
    CASE WHEN raw_data IS NULL THEN NULL ELSE to_jsonb(raw_data::text) END,
    received_at,
    isolated_at,
    isolation_reason,
    reviewed
FROM public.isolated_candles;

-- 3) 이름 스왑(원본 보존)
ALTER TABLE IF EXISTS public.isolated_candles RENAME TO isolated_candles_old;
ALTER TABLE public.isolated_candles_new RENAME TO isolated_candles;

-- 4) hypertable 생성
SELECT create_hypertable('public.isolated_candles', 'isolated_at', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- 5) 인덱스/시퀀스 복구
CREATE INDEX IF NOT EXISTS idx_isolated_reason ON public.isolated_candles (isolation_reason, isolated_at DESC);
CREATE INDEX IF NOT EXISTS idx_isolated_reviewed ON public.isolated_candles (reviewed, isolated_at DESC);
SELECT setval(pg_get_serial_sequence('public.isolated_candles','id'), COALESCE((SELECT MAX(id)+1 FROM public.isolated_candles),1), false);

-- 6) 보존 정책 (시도)
DO $$
BEGIN
  BEGIN
    PERFORM add_retention_policy('public.isolated_candles', INTERVAL '30 days');
  EXCEPTION WHEN others THEN
    RAISE NOTICE 'add_retention_policy for isolated_candles skipped: %', SQLERRM;
  END;
END
$$;

COMMIT;

-- 7) 검증 출력
SELECT 'isolated_new_count' AS tag, count(*) FROM public.isolated_candles;
SELECT 'isolated_old_exists' AS tag, (SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='isolated_candles_old')) AS value;
