-- ============================================================
-- Migration 001: staging_candles 누락 컬럼 추가 (idempotent)
--
-- 목적: 이전 버전에서 생성된 staging_candles 테이블에
--       quote_volume, trade_count, is_complete, seq 컬럼이 없을 경우
--       안전하게 추가합니다. 여러 번 실행해도 안전합니다.
-- ============================================================

DO $$
BEGIN
    -- quote_volume 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'staging_candles'
          AND column_name  = 'quote_volume'
    ) THEN
        ALTER TABLE public.staging_candles
            ADD COLUMN quote_volume NUMERIC(30, 8) DEFAULT 0;
        RAISE NOTICE '[001] staging_candles.quote_volume 컬럼 추가됨';
    END IF;

    -- trade_count 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'staging_candles'
          AND column_name  = 'trade_count'
    ) THEN
        ALTER TABLE public.staging_candles
            ADD COLUMN trade_count INTEGER DEFAULT 0;
        RAISE NOTICE '[001] staging_candles.trade_count 컬럼 추가됨';
    END IF;

    -- is_complete 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'staging_candles'
          AND column_name  = 'is_complete'
    ) THEN
        ALTER TABLE public.staging_candles
            ADD COLUMN is_complete BOOLEAN DEFAULT FALSE;
        RAISE NOTICE '[001] staging_candles.is_complete 컬럼 추가됨';
    END IF;

    -- seq 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'staging_candles'
          AND column_name  = 'seq'
    ) THEN
        ALTER TABLE public.staging_candles
            ADD COLUMN seq BIGINT;
        RAISE NOTICE '[001] staging_candles.seq 컬럼 추가됨';
    END IF;
END $$;
