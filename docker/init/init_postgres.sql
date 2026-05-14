-- =============================================================================
-- PostgreSQL 초기화 스크립트
-- 목적: CQRS + Double-Entry Ledger + Snowflake ID 시퀀스 설정
-- 버전: v8.0
-- 실행: docker exec -i upbit-postgres-primary psql -U postgres -d trading < init_postgres.sql
-- =============================================================================

-- =============================================================================
-- 1. 확장 설치
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUID 생성 (보조용)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- 암호화

-- =============================================================================
-- 2. 심볼(종목) 메타 테이블
-- =============================================================================

CREATE TABLE IF NOT EXISTS symbols (
    id          BIGINT      PRIMARY KEY,            -- Snowflake ID
    market      TEXT        NOT NULL,               -- 마켓 (예: KRW, BTC, USDT)
    symbol      TEXT        NOT NULL UNIQUE,        -- 심볼 (예: KRW-BTC)
    korean_name TEXT,                               -- 한글명 (예: 비트코인)
    english_name TEXT,                              -- 영문명 (예: Bitcoin)
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,  -- 활성 여부
    priority    SMALLINT    NOT NULL DEFAULT 5,     -- 수집 우선순위 (1=최고 ~ 10=최저)
    base_tf     TEXT        NOT NULL DEFAULT '1m',  -- 기본 타임프레임
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE symbols IS '거래 심볼(종목) 마스터';
COMMENT ON COLUMN symbols.priority IS '1=최고, 10=최저 우선순위 (수집 스케줄링에 사용)';

CREATE INDEX IF NOT EXISTS idx_symbols_market   ON symbols (market);
CREATE INDEX IF NOT EXISTS idx_symbols_active   ON symbols (is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_symbols_priority ON symbols (priority);

-- =============================================================================
-- 3. 계좌 테이블
-- =============================================================================

CREATE TABLE IF NOT EXISTS accounts (
    id           BIGINT      PRIMARY KEY,          -- Snowflake ID
    user_id      BIGINT      NOT NULL,
    account_type TEXT        NOT NULL,             -- 'real', 'paper'
    currency     TEXT        NOT NULL,             -- 'KRW', 'BTC', 'ETH' ...
    balance      NUMERIC(24, 8) NOT NULL DEFAULT 0, -- 현재 잔고
    locked       NUMERIC(24, 8) NOT NULL DEFAULT 0, -- 주문 잠금 금액
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, account_type, currency)
);

COMMENT ON TABLE accounts IS '사용자 계좌 (실거래/모의거래 분리)';

-- =============================================================================
-- 4. 거래 주문 테이블
-- =============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id           BIGINT      PRIMARY KEY,          -- Snowflake ID
    user_id      BIGINT      NOT NULL,
    symbol       TEXT        NOT NULL,
    side         TEXT        NOT NULL,             -- 'buy', 'sell'
    order_type   TEXT        NOT NULL,             -- 'limit', 'market'
    status       TEXT        NOT NULL DEFAULT 'pending',
                                                   -- 'pending', 'filled', 'canceled', 'failed'
    price        NUMERIC(24, 8),                   -- 주문 가격 (지정가)
    quantity     NUMERIC(24, 8) NOT NULL,          -- 주문 수량
    filled_qty   NUMERIC(24, 8) NOT NULL DEFAULT 0, -- 체결 수량
    fee          NUMERIC(24, 8) NOT NULL DEFAULT 0, -- 수수료
    is_paper     BOOLEAN     NOT NULL DEFAULT FALSE, -- 모의거래 여부
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE orders IS '거래 주문 (실거래/모의거래 통합)';

CREATE INDEX IF NOT EXISTS idx_orders_user_symbol ON orders (user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_orders_created     ON orders (created_at DESC);

-- =============================================================================
-- 5. 복식부기 원장 테이블 (Double-Entry Ledger)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ledger_entries (
    id             BIGINT      PRIMARY KEY,         -- Snowflake ID
    transaction_id BIGINT      NOT NULL,            -- 같은 거래의 항목들이 공유하는 ID
    account_type   TEXT        NOT NULL,            -- 'asset', 'liability', 'equity', 'expense'
    account_name   TEXT        NOT NULL,            -- 'KRW', 'BTC', 'fee' ...
    debit          NUMERIC(24, 8) NOT NULL DEFAULT 0,  -- 차변 (자산 증가 / 부채 감소)
    credit         NUMERIC(24, 8) NOT NULL DEFAULT 0,  -- 대변 (자산 감소 / 부채 증가)
    balance        NUMERIC(24, 8) NOT NULL,         -- 해당 계정 잔액 (스냅샷)
    memo           TEXT,                            -- 메모
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ledger_entries IS '복식부기 원장 (차변 합계 = 대변 합계 항상 보장)';
COMMENT ON COLUMN ledger_entries.debit  IS '차변: 자산 증가 또는 부채/자본 감소';
COMMENT ON COLUMN ledger_entries.credit IS '대변: 자산 감소 또는 부채/자본 증가';

CREATE INDEX IF NOT EXISTS idx_ledger_transaction ON ledger_entries (transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_account     ON ledger_entries (account_name, created_at DESC);

-- 복식부기 무결성 검증 뷰 (차변 ≠ 대변인 거래 탐지)
CREATE OR REPLACE VIEW ledger_imbalances AS
SELECT
    transaction_id,
    SUM(debit)  AS total_debit,
    SUM(credit) AS total_credit,
    SUM(debit) - SUM(credit) AS diff
FROM ledger_entries
GROUP BY transaction_id
HAVING SUM(debit) != SUM(credit);

COMMENT ON VIEW ledger_imbalances IS '복식부기 불균형 거래 감지 뷰 (조회 결과 0건 = 정상)';

-- =============================================================================
-- 6. 거래 이력 테이블 (체결 기록)
-- =============================================================================

CREATE TABLE IF NOT EXISTS trades (
    id           BIGINT      PRIMARY KEY,           -- Snowflake ID
    order_id     BIGINT      NOT NULL REFERENCES orders(id),
    user_id      BIGINT      NOT NULL,
    symbol       TEXT        NOT NULL,
    side         TEXT        NOT NULL,              -- 'buy', 'sell'
    price        NUMERIC(24, 8) NOT NULL,           -- 체결 가격
    quantity     NUMERIC(24, 8) NOT NULL,           -- 체결 수량
    fee          NUMERIC(24, 8) NOT NULL DEFAULT 0, -- 수수료
    fee_currency TEXT        NOT NULL DEFAULT 'KRW',
    is_paper     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE trades IS '실제 체결 이력 (order_id 외래키로 주문과 연결)';

CREATE INDEX IF NOT EXISTS idx_trades_user_symbol ON trades (user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_trades_created     ON trades (created_at DESC);

-- =============================================================================
-- 7. 복식부기 자동 트리거 (주문 체결 시 원장 항목 생성)
-- =============================================================================

CREATE OR REPLACE FUNCTION create_ledger_entries_on_trade()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_asset_balance  NUMERIC(24, 8);
    v_krw_balance    NUMERIC(24, 8);
    v_trade_amount   NUMERIC(24, 8);
BEGIN
    v_trade_amount := NEW.price * NEW.quantity;

    -- 매수 체결 시
    IF NEW.side = 'buy' THEN
        -- 구매 자산 현재 잔액 계산
        SELECT COALESCE(SUM(debit) - SUM(credit), 0)
          INTO v_asset_balance
          FROM ledger_entries
         WHERE account_name = NEW.symbol;

        -- KRW 현재 잔액 계산
        SELECT COALESCE(SUM(debit) - SUM(credit), 0)
          INTO v_krw_balance
          FROM ledger_entries
         WHERE account_name = 'KRW';

        INSERT INTO ledger_entries (id, transaction_id, account_type, account_name, debit, credit, balance)
        VALUES
            -- 차변: 구매 자산 증가
            (NEW.id * 10 + 1, NEW.id, 'asset',   NEW.symbol,  v_trade_amount,              0,                             v_asset_balance + v_trade_amount),
            -- 대변: KRW 감소
            (NEW.id * 10 + 2, NEW.id, 'asset',   'KRW',       0,                           v_trade_amount + NEW.fee,      v_krw_balance - v_trade_amount - NEW.fee),
            -- 차변: 수수료 비용
            (NEW.id * 10 + 3, NEW.id, 'expense', 'fee',       NEW.fee,                     0,                             NEW.fee);

    -- 매도 체결 시
    ELSIF NEW.side = 'sell' THEN
        -- 판매 자산 현재 잔액 계산
        SELECT COALESCE(SUM(debit) - SUM(credit), 0)
          INTO v_asset_balance
          FROM ledger_entries
         WHERE account_name = NEW.symbol;

        -- KRW 현재 잔액 계산
        SELECT COALESCE(SUM(debit) - SUM(credit), 0)
          INTO v_krw_balance
          FROM ledger_entries
         WHERE account_name = 'KRW';

        INSERT INTO ledger_entries (id, transaction_id, account_type, account_name, debit, credit, balance)
        VALUES
            -- 차변: KRW 증가
            (NEW.id * 10 + 1, NEW.id, 'asset',   'KRW',       v_trade_amount - NEW.fee,    0,                             v_krw_balance + v_trade_amount - NEW.fee),
            -- 대변: 자산 감소
            (NEW.id * 10 + 2, NEW.id, 'asset',   NEW.symbol,  0,                           v_trade_amount,                v_asset_balance - v_trade_amount),
            -- 차변: 수수료 비용
            (NEW.id * 10 + 3, NEW.id, 'expense', 'fee',       NEW.fee,                     0,                             NEW.fee);
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_ledger_on_trade
    AFTER INSERT ON trades
    FOR EACH ROW
    EXECUTE FUNCTION create_ledger_entries_on_trade();

-- =============================================================================
-- 8. updated_at 자동 갱신 트리거 (공통)
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_symbols_updated_at
    BEFORE UPDATE ON symbols
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- 9. CQRS 복제 사용자 생성 (Replica 스트리밍 복제용)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replicator') THEN
        CREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD 'replica_pass_change_me';
    END IF;
END;
$$;

-- =============================================================================
-- 10. 읽기 전용 사용자 생성 (Replica → 읽기 전용 API 서버용)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reader') THEN
        CREATE ROLE reader WITH LOGIN PASSWORD 'reader_pass_change_me';
    END IF;
END;
$$;

GRANT CONNECT ON DATABASE trading TO reader;
GRANT USAGE ON SCHEMA public TO reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO reader;
