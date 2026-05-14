-- isolated_candles 테이블 DDL (Timescale 환경을 고려한 권장 스키마)
-- 설명:
--  - 검증 실패한 캔들/원본 레코드를 보존합니다.
--  - raw_data는 JSONB로 저장(원본 구조 보존).
--  - 기본 인덱스: symbol, timeframe, time(쿼리/조회용)
--  - TimescaleDB가 설치되어 있으면 hypertable로 전환 가능(주석 해제)
-- 사용법(예):
--  psql -h <host> -p <port> -U <user> -d <dbname> -f isolated_candles_ddl.sql

BEGIN;

-- 1) 테이블 생성
CREATE TABLE IF NOT EXISTS isolated_candles (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1m',
    exchange TEXT NOT NULL DEFAULT 'upbit',
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    quote_volume NUMERIC,
    trade_count INTEGER,
    seq TEXT,
    is_complete BOOLEAN DEFAULT FALSE,
    raw_data JSONB,                     -- 원본 레코드 보존
    isolation_reason TEXT,              -- 검증 실패 사유
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2) 성능/조회용 인덱스
CREATE INDEX IF NOT EXISTS ix_isolated_candles_symbol_timeframe_time
    ON isolated_candles (symbol, timeframe, time DESC);

CREATE INDEX IF NOT EXISTS ix_isolated_candles_received_at
    ON isolated_candles (received_at DESC);

CREATE INDEX IF NOT EXISTS ix_isolated_candles_isolation_reason
    ON isolated_candles (isolation_reason);

-- 3) (선택) Timescale hypertable 전환: 운영환경에서 Timescale이 설치된 경우 사용
-- 주석을 해제하여 hypertable로 만들면 자동 파티셔닝/압축 정책 적용 가능
-- 주의: hypertable 생성은 슈퍼유저/권한이 필요할 수 있음
-- SELECT create_hypertable('isolated_candles', 'time', if_not_exists => TRUE);

-- 4) (권장) 보존 정책 샘플: 90일 이후 자동 삭제(운영 정책에 맞게 조정)
-- 예시: pg_cron 또는 Timescale 정책으로 주기적으로 삭제하도록 설정
-- 아래는 단순한 SQL 예시(운영환경에선 백업/법적요건 확인 후 설정)
-- DELETE FROM isolated_candles WHERE received_at < now() - INTERVAL '90 days';

COMMIT;