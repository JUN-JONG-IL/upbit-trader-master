-- ============================================================
-- Migration 003: 우선순위 설정 + ML 모델 테이블 추가
-- 대상 DB: PostgreSQL (TimescaleDB 포함)
-- 실행 방법:
--   psql -U postgres -d upbit_trader < database/migrations/003_add_priority_ml_tables.sql
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. priority_settings – 우선순위 설정 테이블
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS priority_settings (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    setting_name    VARCHAR(100) NOT NULL,

    -- 우선순위 항목 활성화 여부 (체크박스)
    volume_enabled              BOOLEAN DEFAULT false,
    market_cap_enabled          BOOLEAN DEFAULT false,
    popularity_enabled          BOOLEAN DEFAULT false,
    new_listings_enabled        BOOLEAN DEFAULT false,
    volatility_enabled          BOOLEAN DEFAULT false,
    price_change_enabled        BOOLEAN DEFAULT false,
    pattern_detection_enabled   BOOLEAN DEFAULT false,
    social_mentions_enabled     BOOLEAN DEFAULT false,

    -- 우선순위 순서 (JSON 배열, 예: ["volume","market_cap"])
    priority_order  JSONB DEFAULT '[]'::jsonb,

    -- 로직 선택
    logic_type      VARCHAR(10) DEFAULT 'OR'
                    CHECK (logic_type IN ('OR', 'AND')),

    -- 메타데이터
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (user_id, setting_name)
);

CREATE INDEX IF NOT EXISTS idx_priority_user
    ON priority_settings (user_id);

CREATE INDEX IF NOT EXISTS idx_priority_active
    ON priority_settings (is_active)
    WHERE is_active = true;


-- ─────────────────────────────────────────────────────────────
-- 2. ml_model_settings – ML 모델 설정 테이블
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_model_settings (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,

    -- Gap 예측 모델
    gap_model_type      VARCHAR(50)  DEFAULT 'lightgbm'
                        CHECK (gap_model_type IN ('xgboost', 'lightgbm', 'catboost', 'prophet')),
    gap_model_params    JSONB        DEFAULT '{}'::jsonb,
    gap_model_enabled   BOOLEAN      DEFAULT true,

    -- Adaptive TimeFrame
    adaptive_tf_enabled BOOLEAN      DEFAULT false,
    adaptive_tf_method  VARCHAR(50)  DEFAULT 'symbol_based'
                        CHECK (adaptive_tf_method IN ('symbol_based', 'volatility_based', 'hybrid')),
    adaptive_tf_params  JSONB        DEFAULT '{}'::jsonb,

    -- 이상치 감지
    anomaly_model_type  VARCHAR(50)  DEFAULT 'isolation_forest'
                        CHECK (anomaly_model_type IN ('autoencoder', 'isolation_forest', 'one_class_svm')),
    anomaly_threshold   DECIMAL(5,2) DEFAULT 0.95
                        CHECK (anomaly_threshold BETWEEN 0 AND 1),
    anomaly_enabled     BOOLEAN      DEFAULT true,

    -- Drift 모니터링
    drift_monitor_type  VARCHAR(50)  DEFAULT 'evidently'
                        CHECK (drift_monitor_type IN ('alibi_detect', 'evidently')),
    drift_check_interval INTEGER     DEFAULT 3600
                        CHECK (drift_check_interval > 0),
    drift_enabled       BOOLEAN      DEFAULT true,

    -- 메타데이터
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_ml_model_user
    ON ml_model_settings (user_id);

CREATE INDEX IF NOT EXISTS idx_ml_model_active
    ON ml_model_settings (is_active)
    WHERE is_active = true;


-- ─────────────────────────────────────────────────────────────
-- 3. symbol_priority_scores – 심볼별 우선순위 점수
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS symbol_priority_scores (
    id              BIGSERIAL PRIMARY KEY,
    exchange        VARCHAR(50)   NOT NULL,
    symbol          VARCHAR(50)   NOT NULL,

    -- 각 우선순위 항목 점수 (0-100)
    volume_score        DECIMAL(10,4) DEFAULT 0,
    market_cap_score    DECIMAL(10,4) DEFAULT 0,
    popularity_score    DECIMAL(10,4) DEFAULT 0,
    new_listing_score   DECIMAL(10,4) DEFAULT 0,
    volatility_score    DECIMAL(10,4) DEFAULT 0,
    price_change_score  DECIMAL(10,4) DEFAULT 0,
    pattern_score       DECIMAL(10,4) DEFAULT 0,
    social_score        DECIMAL(10,4) DEFAULT 0,

    -- 최종 점수
    total_score     DECIMAL(10,4) DEFAULT 0,
    weighted_score  DECIMAL(10,4) DEFAULT 0,
    rank            INTEGER,

    -- 메타데이터
    calculated_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at      TIMESTAMP WITH TIME ZONE,

    UNIQUE (exchange, symbol, calculated_at)
);

CREATE INDEX IF NOT EXISTS idx_symbol_priority_exchange_symbol
    ON symbol_priority_scores (exchange, symbol);

CREATE INDEX IF NOT EXISTS idx_symbol_priority_total_score
    ON symbol_priority_scores (total_score DESC);

CREATE INDEX IF NOT EXISTS idx_symbol_priority_calculated
    ON symbol_priority_scores (calculated_at DESC);


-- ─────────────────────────────────────────────────────────────
-- 4. ml_predictions – ML 예측 결과 저장
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_predictions (
    id              BIGSERIAL PRIMARY KEY,
    exchange        VARCHAR(50)   NOT NULL,
    symbol          VARCHAR(50)   NOT NULL,

    -- 모델 정보
    model_type      VARCHAR(50)   NOT NULL,
    model_version   VARCHAR(50),

    -- 예측 결과
    prediction_type  VARCHAR(50)  NOT NULL,
    prediction_value JSONB        NOT NULL,
    confidence_score DECIMAL(5,4),

    -- 메타데이터
    predicted_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at      TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_ml_pred_symbol
    ON ml_predictions (exchange, symbol);

CREATE INDEX IF NOT EXISTS idx_ml_pred_type
    ON ml_predictions (prediction_type);

CREATE INDEX IF NOT EXISTS idx_ml_pred_time
    ON ml_predictions (predicted_at DESC);


-- ─────────────────────────────────────────────────────────────
-- 5. updated_at 자동 갱신 트리거 (priority_settings, ml_model_settings)
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_priority_settings_updated_at'
    ) THEN
        CREATE TRIGGER trg_priority_settings_updated_at
        BEFORE UPDATE ON priority_settings
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ml_model_settings_updated_at'
    ) THEN
        CREATE TRIGGER trg_ml_model_settings_updated_at
        BEFORE UPDATE ON ml_model_settings
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END
$$;
