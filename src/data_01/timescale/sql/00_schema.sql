-- ============================================================
-- 기관급 트레이딩 시스템 - TimescaleDB Schema (Idempotent DDL)
-- 개선판: idempotency / 안전한 압축 설정 / latest_snapshot trigger 추가
-- 주의: 이 파일을 적용하기 전에 백업을 권장합니다.
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
-- PL/Python 설치는 운영환경에서 신중 권장 (주석 처리되어 있으면 설치하지 마세요)
-- CREATE EXTENSION IF NOT EXISTS plpython3u;

-- ============================================================
-- 1. Base Hypertable: candles (base 1m TF)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.candles (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(64) NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(30, 8) NOT NULL DEFAULT 0,
    seq BIGINT,
    exchange VARCHAR(32) DEFAULT 'upbit',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT candles_pkey PRIMARY KEY (time, symbol, timeframe),
    CONSTRAINT candles_ohlc_check CHECK (
        high >= low AND
        high >= open AND
        high >= close AND
        low <= open AND
        low <= close
    ),
    CONSTRAINT candles_volume_check CHECK (volume >= 0)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'candles'
    ) THEN
        PERFORM create_hypertable('public.candles', 'time', chunk_time_interval => INTERVAL '1 day');
        RAISE NOTICE 'Hypertable candles created';
    ELSE
        RAISE NOTICE 'Hypertable candles already exists';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_candles_symbol_time ON public.candles (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_candles_timeframe_time ON public.candles (timeframe, time DESC);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_timeframe ON public.candles (symbol, timeframe, time DESC);
CREATE INDEX IF NOT EXISTS brin_candles_time ON public.candles USING BRIN (time);

DO $$
BEGIN
    BEGIN
        EXECUTE 'ALTER TABLE public.candles SET (timescaledb.compress = true, timescaledb.compress_segmentby = ''symbol,timeframe'')';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'ALTER TABLE SET(...) for compression failed or not supported: %', SQLERRM;
    END;
    BEGIN
        PERFORM add_compression_policy('public.candles', INTERVAL '7 days');
        RAISE NOTICE 'Compression policy added for candles (7 days)';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Compression policy setup skipped/failed: %', SQLERRM;
    END;
END
$$;

-- ============================================================
-- 2. Staging Table: staging_candles (임시 저장)
--    Goal: ensure staging_candles is a hypertable on received_at with a composite PK
--          that includes received_at so Timescale can accept unique/index constraints.
-- ============================================================

-- If staging_candles does not exist, create it as hypertable-friendly table.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'staging_candles'
    ) THEN
        CREATE TABLE public.staging_candles (
            id BIGSERIAL,
            time TIMESTAMPTZ NOT NULL,
            symbol VARCHAR(64) NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
            open NUMERIC(20, 8) NOT NULL,
            high NUMERIC(20, 8) NOT NULL,
            low NUMERIC(20, 8) NOT NULL,
            close NUMERIC(20, 8) NOT NULL,
            volume NUMERIC(30, 8) NOT NULL DEFAULT 0,
            quote_volume NUMERIC(30, 8) DEFAULT 0,
            seq BIGINT,
            exchange VARCHAR(32) DEFAULT 'upbit',
            raw_data JSONB,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed BOOLEAN DEFAULT FALSE,
            trade_count BIGINT,
            is_complete BOOLEAN DEFAULT FALSE,
            is_closed BOOLEAN,
            ts BIGINT,
            CONSTRAINT staging_candles_pkey PRIMARY KEY (id, received_at),
            CONSTRAINT staging_candles_ohlc_check CHECK (
                high >= low AND
                high >= open AND
                high >= close AND
                low <= open AND
                low <= close
            ),
            CONSTRAINT staging_candles_volume_check CHECK (volume >= 0)
        );
        PERFORM create_hypertable('public.staging_candles', 'received_at', chunk_time_interval => INTERVAL '1 day');
        RAISE NOTICE 'Created new staging_candles as hypertable';
    ELSE
        -- If table exists but is not hypertable, migrate safely to hypertable if not already migrated.
        IF NOT EXISTS (
            SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'staging_candles'
        ) THEN
            -- Avoid re-running migration if staging_candles_new already exists.
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='staging_candles_new') THEN
                -- Create a new table with desired PK (id, received_at)
                CREATE TABLE public.staging_candles_new (
                    id BIGSERIAL,
                    time TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(64) NOT NULL,
                    timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
                    open NUMERIC(20, 8) NOT NULL,
                    high NUMERIC(20, 8) NOT NULL,
                    low NUMERIC(20, 8) NOT NULL,
                    close NUMERIC(20, 8) NOT NULL,
                    volume NUMERIC(30, 8) NOT NULL DEFAULT 0,
                    quote_volume NUMERIC(30, 8) DEFAULT 0,
                    seq BIGINT,
                    exchange VARCHAR(32) DEFAULT 'upbit',
                    raw_data JSONB,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    processed BOOLEAN DEFAULT FALSE,
                    trade_count BIGINT,
                    is_complete BOOLEAN DEFAULT FALSE,
                    is_closed BOOLEAN,
                    ts BIGINT,
                    CONSTRAINT staging_candles_new_pkey PRIMARY KEY (id, received_at)
                );
                -- Copy data, attempt safe cast for raw_data
                -- quote_volume and is_complete were not in the original schema;
                -- default to 0 and FALSE respectively during migration.
                INSERT INTO public.staging_candles_new (id, time, symbol, timeframe, open, high, low, close, volume, quote_volume, seq, exchange, raw_data, received_at, processed, trade_count, is_complete, is_closed, ts)
                SELECT id, time, symbol, timeframe, open, high, low, close, volume,
                       0 AS quote_volume,
                       seq, exchange,
                       CASE
                           WHEN raw_data IS NULL THEN NULL
                           WHEN jsonb_typeof(raw_data::jsonb) IS NOT NULL THEN raw_data::jsonb
                           ELSE to_jsonb(raw_data::text)
                       END,
                       received_at, processed, trade_count,
                       -- is_complete mirrors is_closed semantically; preserve existing NULL values
                       is_closed AS is_complete,
                       is_closed, ts
                FROM public.staging_candles;
                -- Swap names
                ALTER TABLE public.staging_candles RENAME TO staging_candles_old;
                ALTER TABLE public.staging_candles_new RENAME TO staging_candles;
                -- Make hypertable
                PERFORM create_hypertable('public.staging_candles', 'received_at', chunk_time_interval => INTERVAL '1 day');
                -- Recreate indexes
                CREATE INDEX IF NOT EXISTS idx_staging_symbol_time_seq ON public.staging_candles (symbol, time, seq) WHERE NOT processed;
                CREATE INDEX IF NOT EXISTS idx_staging_processed ON public.staging_candles (processed, received_at DESC);
                -- Set sequence value
                PERFORM setval(pg_get_serial_sequence('public.staging_candles','id'), COALESCE((SELECT MAX(id)+1 FROM public.staging_candles),1), false);
                RAISE NOTICE 'Migrated staging_candles -> hypertable (staging_candles_old retained)';
            ELSE
                RAISE NOTICE 'staging_candles_new already exists, skipping migration';
            END IF;
        ELSE
            RAISE NOTICE 'staging_candles already a hypertable';
        END IF;
    END IF;
END
$$;

-- Add retention policy if hypertable present
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'staging_candles') THEN
        BEGIN
            PERFORM add_retention_policy('public.staging_candles', INTERVAL '7 days');
            RAISE NOTICE 'Retention policy added for staging_candles (7 days)';
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Retention policy setup for staging_candles skipped/failed: %', SQLERRM;
        END;
    END IF;
END
$$;

-- ============================================================
-- 2b. staging_candles 스키마 정규화 (idempotent)
--     이전 버전에서 생성된 테이블에 누락된 컬럼을 자동으로 추가합니다.
--     여러 번 실행해도 안전합니다.
-- ============================================================
DO $$
BEGIN
    -- quote_volume 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'staging_candles'
          AND column_name = 'quote_volume'
    ) THEN
        ALTER TABLE public.staging_candles
        ADD COLUMN quote_volume NUMERIC(30, 8) DEFAULT 0;
        RAISE NOTICE '[00_schema] staging_candles.quote_volume 컬럼 추가됨';
    END IF;

    -- trade_count 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'staging_candles'
          AND column_name = 'trade_count'
    ) THEN
        ALTER TABLE public.staging_candles
        ADD COLUMN trade_count INTEGER DEFAULT 0;
        RAISE NOTICE '[00_schema] staging_candles.trade_count 컬럼 추가됨';
    END IF;

    -- is_complete 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'staging_candles'
          AND column_name = 'is_complete'
    ) THEN
        ALTER TABLE public.staging_candles
        ADD COLUMN is_complete BOOLEAN DEFAULT FALSE;
        RAISE NOTICE '[00_schema] staging_candles.is_complete 컬럼 추가됨';
    END IF;
END $$;

-- ============================================================
-- 3. Isolated Table: isolated_candles (이�� 데이터 격리)
--    Similar safe migration to hypertable on isolated_at
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'isolated_candles'
    ) THEN
        CREATE TABLE public.isolated_candles (
            id BIGSERIAL,
            time TIMESTAMPTZ NOT NULL,
            symbol VARCHAR(64) NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
            open NUMERIC(20, 8),
            high NUMERIC(20, 8),
            low NUMERIC(20, 8),
            close NUMERIC(20, 8),
            volume NUMERIC(30, 8),
            seq BIGINT,
            exchange VARCHAR(32) DEFAULT 'upbit',
            raw_data JSONB,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            isolated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            isolation_reason TEXT NOT NULL,
            reviewed BOOLEAN DEFAULT FALSE,
            trade_count BIGINT,
            CONSTRAINT isolated_candles_pkey PRIMARY KEY (id, isolated_at)
        );
        PERFORM create_hypertable('public.isolated_candles', 'isolated_at', chunk_time_interval => INTERVAL '7 days');
        RAISE NOTICE 'Created isolated_candles as hypertable';
    ELSE
        IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'isolated_candles') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='isolated_candles_new') THEN
                CREATE TABLE public.isolated_candles_new (
                    id BIGSERIAL,
                    time TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(64) NOT NULL,
                    timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
                    open NUMERIC(20, 8),
                    high NUMERIC(20, 8),
                    low NUMERIC(20, 8),
                    close NUMERIC(20, 8),
                    volume NUMERIC(30, 8),
                    seq BIGINT,
                    exchange VARCHAR(32) DEFAULT 'upbit',
                    raw_data JSONB,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    isolated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    isolation_reason TEXT NOT NULL,
                    reviewed BOOLEAN DEFAULT FALSE,
                    trade_count BIGINT,
                    CONSTRAINT isolated_candles_new_pkey PRIMARY KEY (id, isolated_at)
                );
                INSERT INTO public.isolated_candles_new (id, time, symbol, timeframe, open, high, low, close, volume, seq, exchange, raw_data, received_at, isolated_at, isolation_reason, reviewed, trade_count)
                SELECT id, time, symbol, timeframe, open, high, low, close, volume, seq, exchange,
                       CASE WHEN raw_data IS NULL THEN NULL WHEN jsonb_typeof(raw_data::jsonb) IS NOT NULL THEN raw_data::jsonb ELSE to_jsonb(raw_data::text) END,
                       received_at, isolated_at, isolation_reason, reviewed, trade_count
                FROM public.isolated_candles;
                ALTER TABLE public.isolated_candles RENAME TO isolated_candles_old;
                ALTER TABLE public.isolated_candles_new RENAME TO isolated_candles;
                PERFORM create_hypertable('public.isolated_candles', 'isolated_at', chunk_time_interval => INTERVAL '7 days');
                CREATE INDEX IF NOT EXISTS idx_isolated_reason ON public.isolated_candles (isolation_reason, isolated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_isolated_reviewed ON public.isolated_candles (reviewed, isolated_at DESC);
                PERFORM setval(pg_get_serial_sequence('public.isolated_candles','id'), COALESCE((SELECT MAX(id)+1 FROM public.isolated_candles),1), false);
                RAISE NOTICE 'Migrated isolated_candles -> hypertable (isolated_candles_old retained)';
            ELSE
                RAISE NOTICE 'isolated_candles_new already exists, skipping migration';
            END IF;
        ELSE
            RAISE NOTICE 'isolated_candles already a hypertable';
        END IF;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'isolated_candles') THEN
        BEGIN
            PERFORM add_retention_policy('public.isolated_candles', INTERVAL '30 days');
            RAISE NOTICE 'Retention policy added for isolated_candles (30 days)';
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Retention policy setup for isolated_candles skipped/failed: %', SQLERRM;
        END;
    END IF;
END
$$;

-- ============================================================
-- 4. Snapshot Table: latest_snapshot (마지막 캔들 시간)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.latest_snapshot (
    symbol VARCHAR(64) NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT '1m',
    last_candle_time TIMESTAMPTZ,
    last_seq BIGINT,
    candle_count BIGINT DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT latest_snapshot_pkey PRIMARY KEY (symbol, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_updated
    ON public.latest_snapshot (updated_at DESC);

-- ============================================================
-- 5. Function & Trigger: update latest_snapshot on candles insert/update
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_update_latest_snapshot()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO public.latest_snapshot (symbol, timeframe, last_candle_time, last_seq, updated_at)
  VALUES (NEW.symbol, NEW.timeframe, NEW.time, NEW.seq, NOW())
  ON CONFLICT (symbol, timeframe) DO UPDATE
  SET
    last_candle_time = GREATEST(EXCLUDED.last_candle_time, public.latest_snapshot.last_candle_time),
    last_seq = GREATEST(COALESCE(EXCLUDED.last_seq,0), COALESCE(public.latest_snapshot.last_seq,0)),
    updated_at = NOW();
  RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_update_latest_snapshot'
    ) THEN
        CREATE TRIGGER trg_update_latest_snapshot
        AFTER INSERT OR UPDATE ON public.candles
        FOR EACH ROW EXECUTE FUNCTION public.fn_update_latest_snapshot();
        RAISE NOTICE 'Trigger trg_update_latest_snapshot created';
    ELSE
        RAISE NOTICE 'Trigger trg_update_latest_snapshot already exists';
    END IF;
END
$$;

-- ============================================================
-- 6. Continuous Aggregates (파생 TF)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS public.cagg_candles_5m
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('5 minutes', time) AS time,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    count(*) AS candle_count
FROM public.candles
WHERE timeframe = '1m'
GROUP BY time_bucket('5 minutes', time), symbol
WITH NO DATA;

DO $$
BEGIN
    BEGIN
        PERFORM add_continuous_aggregate_policy(
            'public.cagg_candles_5m',
            start_offset => INTERVAL '1 hour',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes'
        );
        RAISE NOTICE 'Refresh policy added for cagg_candles_5m';
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE 'cagg_candles_5m policy setup skipped/failed: %', SQLERRM;
    END;
END
$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS public.cagg_candles_15m
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('15 minutes', time) AS time,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    count(*) AS candle_count
FROM public.candles
WHERE timeframe = '1m'
GROUP BY time_bucket('15 minutes', time), symbol
WITH NO DATA;

DO $$
BEGIN
    BEGIN
        PERFORM add_continuous_aggregate_policy(
            'public.cagg_candles_15m',
            start_offset => INTERVAL '3 hours',
            end_offset => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '15 minutes'
        );
        RAISE NOTICE 'Refresh policy added for cagg_candles_15m';
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE 'cagg_candles_15m policy setup skipped/failed: %', SQLERRM;
    END;
END
$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS public.cagg_candles_1h
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS time,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    count(*) AS candle_count
FROM public.candles
WHERE timeframe = '1m'
GROUP BY time_bucket('1 hour', time), symbol
WITH NO DATA;

DO $$
BEGIN
    BEGIN
        PERFORM add_continuous_aggregate_policy(
            'public.cagg_candles_1h',
            start_offset => INTERVAL '1 day',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        );
        RAISE NOTICE 'Refresh policy added for cagg_candles_1h';
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE 'cagg_candles_1h policy setup skipped/failed: %', SQLERRM;
    END;
END
$$;

CREATE MATERIALIZED VIEW IF NOT EXISTS public.cagg_candles_1d
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS time,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    count(*) AS candle_count
FROM public.candles
WHERE timeframe = '1m'
GROUP BY time_bucket('1 day', time), symbol
WITH NO DATA;

DO $$
BEGIN
    BEGIN
        PERFORM add_continuous_aggregate_policy(
            'public.cagg_candles_1d',
            start_offset => INTERVAL '7 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day'
        );
        RAISE NOTICE 'Refresh policy added for cagg_candles_1d';
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE 'cagg_candles_1d policy setup skipped/failed: %', SQLERRM;
    END;
END
$$;

-- ============================================================
-- 7. Role / Permissions (app_user)
-- Note: In production, manage passwords via secret managers, not plaintext in SQL.
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        EXECUTE format('CREATE ROLE app_user WITH LOGIN PASSWORD %L', 'AppUser!2026Example');
        RAISE NOTICE 'Role app_user created (note: consider secret manager instead of hardcoded password)';
    ELSE
        RAISE NOTICE 'Role app_user already exists';
    END IF;

    BEGIN
        EXECUTE 'GRANT CONNECT ON DATABASE upbit_trader TO app_user';
        EXECUTE 'GRANT USAGE ON SCHEMA public TO app_user';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON public.candles TO app_user';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON public.staging_candles TO app_user';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON public.isolated_candles TO app_user';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.latest_snapshot TO app_user';
        EXECUTE 'GRANT SELECT ON public.cagg_candles_5m TO app_user';
        EXECUTE 'GRANT SELECT ON public.cagg_candles_15m TO app_user';
        EXECUTE 'GRANT SELECT ON public.cagg_candles_1h TO app_user';
        EXECUTE 'GRANT SELECT ON public.cagg_candles_1d TO app_user';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user';
        RAISE NOTICE 'Permissions granted to app_user';
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE 'Granting permissions to app_user skipped/failed: %', SQLERRM;
    END;
END
$$;

-- ============================================================
-- 8. Ensure unique index on candles
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS idx_candles_symbol_timeframe_unique ON public.candles (symbol, time, timeframe);

-- ============================================================
-- 9. Done message
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Schema initialization completed successfully';
    RAISE NOTICE '   - Hypertables: candles (+ staging_candles/isolated_candles migrated if applicable)';
    RAISE NOTICE '   - Snapshot: latest_snapshot';
    RAISE NOTICE '   - CAGG: cagg_candles_5m/15m/1h/1d';
    RAISE NOTICE '   - Policies: Compression(7d), Retention(staging:7d, isolated:30d) applied when hypertable exists';
    RAISE NOTICE '   - User: app_user (permissions granted if created)';
END
$$;