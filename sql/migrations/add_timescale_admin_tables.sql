-- sql/migrations/add_timescale_admin_tables.sql
-- 안전 주의: 운영 DB에 적용 전 백업하세요.

-- 1) backfill_jobs 테이블(백필 작업 기록)
CREATE TABLE IF NOT EXISTS public.backfill_jobs (
    job_id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_ts TIMESTAMPTZ,
    end_ts TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_attempt TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    attempts INT DEFAULT 0
);

-- 2) job run/jobs meta (예시)
CREATE TABLE IF NOT EXISTS public.jobs (
    job_id SERIAL PRIMARY KEY,
    name TEXT,
    last_run_started_at TIMESTAMPTZ,
    last_run_finished_at TIMESTAMPTZ,
    status TEXT
);

-- 3) compress_after 컬럼이 참조된 경우, 예시로 pges (압축정책 테이블) 생성/대체용
-- NOTE: 실제 Timescale 압축정책은 timescaledb의 정책 테이블을 사용합니다. 아래는 fallback용 정보를 제공하기 위한 샘플.
CREATE TABLE IF NOT EXISTS public.compression_policies (
    id SERIAL PRIMARY KEY,
    hypertable TEXT,
    compress_after INTERVAL,
    created_at TIMESTAMPTZ DEFAULT now()
);