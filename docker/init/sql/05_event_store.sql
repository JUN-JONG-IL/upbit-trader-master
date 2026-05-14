-- ==============================================================================
-- CQRS Event Store (PostgreSQL / TimescaleDB)
-- v9.0: aggregate_id + version 기반 Append-Only 이벤트 소싱 테이블
-- ==============================================================================

CREATE TABLE IF NOT EXISTS event_store (
    event_id       BIGINT        PRIMARY KEY,
    aggregate_id   VARCHAR(100)  NOT NULL,
    aggregate_type VARCHAR(50)   NOT NULL,
    event_type     VARCHAR(100)  NOT NULL,
    event_data     JSONB         NOT NULL,
    metadata       JSONB,
    created_at     TIMESTAMPTZ   DEFAULT NOW(),
    version        INT           NOT NULL,
    CONSTRAINT event_store_unique_version UNIQUE (aggregate_id, version)
);

-- aggregate 기준 버전 순 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_event_store_aggregate
    ON event_store (aggregate_id, version);

-- 이벤트 타입 + 시간 기준 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_event_store_type
    ON event_store (aggregate_type, event_type);

-- 시간 기준 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_event_store_created_at
    ON event_store (created_at DESC);

-- ==============================================================================
-- 이벤트 발행 트리거 (PostgreSQL NOTIFY → Kafka 연동)
-- ==============================================================================

CREATE OR REPLACE FUNCTION notify_event_store()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'event_store_channel',
        json_build_object(
            'event_id',      NEW.event_id,
            'aggregate_id',  NEW.aggregate_id,
            'event_type',    NEW.event_type,
            'event_data',    NEW.event_data
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS event_store_notify ON event_store;
CREATE TRIGGER event_store_notify
    AFTER INSERT ON event_store
    FOR EACH ROW EXECUTE FUNCTION notify_event_store();

-- ==============================================================================
-- 스냅샷 테이블 (Aggregate 재구성 성능 최적화)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS aggregate_snapshots (
    aggregate_id   VARCHAR(100)  PRIMARY KEY,
    aggregate_type VARCHAR(50)   NOT NULL,
    snapshot_data  JSONB         NOT NULL,
    version        INT           NOT NULL,
    created_at     TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_type
    ON aggregate_snapshots (aggregate_type);

COMMENT ON TABLE event_store           IS 'CQRS event sourcing store with Kafka integration';
COMMENT ON TABLE aggregate_snapshots   IS 'Aggregate snapshots for performance optimization';
