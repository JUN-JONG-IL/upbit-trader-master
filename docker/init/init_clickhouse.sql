-- =============================================================================
-- ClickHouse 초기화 스크립트
-- 목적: 이벤트 소싱 기반 실시간 OLAP 분석 테이블 설정
-- 버전: v8.0
-- 실행: docker exec -i upbit-clickhouse clickhouse-client --multiquery < init_clickhouse.sql
-- =============================================================================

-- =============================================================================
-- 1. 캔들 이벤트 테이블 (ReplicatedMergeTree)
-- =============================================================================

CREATE TABLE IF NOT EXISTS candle_events (
    event_id        UInt64,                         -- Snowflake ID
    event_time      DateTime64(3, 'UTC'),           -- 이벤트 시각 (밀리초 정밀도)
    symbol          String,                         -- 심볼 (예: KRW-BTC)
    timeframe       LowCardinality(String),         -- 타임프레임 (낮은 카디널리티)
    open            Decimal(24, 8),                 -- 시가
    high            Decimal(24, 8),                 -- 고가
    low             Decimal(24, 8),                 -- 저가
    close           Decimal(24, 8),                 -- 종가
    volume          Decimal(24, 8),                 -- 거래량
    partition_key   UInt16 MATERIALIZED
                        cityHash64(symbol) % 16     -- 파티션 키 (심볼 Hash)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)                   -- 월 단위 파티션
ORDER BY (partition_key, symbol, timeframe, event_time)
TTL event_time + INTERVAL 2 YEAR                   -- 2년 후 자동 삭제
SETTINGS index_granularity = 8192;

-- =============================================================================
-- 2. 주문 이벤트 테이블
-- =============================================================================

CREATE TABLE IF NOT EXISTS order_events (
    event_id        UInt64,
    event_time      DateTime64(3, 'UTC'),
    order_id        UInt64,
    user_id         UInt64,
    symbol          String,
    side            LowCardinality(String),         -- 'buy', 'sell'
    order_type      LowCardinality(String),         -- 'limit', 'market'
    status          LowCardinality(String),         -- 'pending', 'filled', 'canceled'
    price           Decimal(24, 8),
    quantity        Decimal(24, 8),
    filled_qty      Decimal(24, 8),
    fee             Decimal(24, 8),
    is_paper        UInt8                           -- 0=실거래, 1=모의거래
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (user_id, symbol, event_time)
TTL event_time + INTERVAL 3 YEAR
SETTINGS index_granularity = 8192;

-- =============================================================================
-- 3. 체결 이벤트 테이블
-- =============================================================================

CREATE TABLE IF NOT EXISTS trade_events (
    event_id        UInt64,
    event_time      DateTime64(3, 'UTC'),
    trade_id        UInt64,
    order_id        UInt64,
    user_id         UInt64,
    symbol          String,
    side            LowCardinality(String),
    price           Decimal(24, 8),
    quantity        Decimal(24, 8),
    fee             Decimal(24, 8),
    is_paper        UInt8
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (user_id, symbol, event_time)
TTL event_time + INTERVAL 3 YEAR
SETTINGS index_granularity = 8192;

-- =============================================================================
-- 4. Kafka 엔진 테이블 (Kafka → ClickHouse 자동 소비)
-- =============================================================================

-- 캔들 이벤트 Kafka 큐 테이블
CREATE TABLE IF NOT EXISTS candle_events_queue (
    event_id        UInt64,
    event_time      String,                         -- JSON에서 문자열로 수신
    symbol          String,
    timeframe       String,
    open            Float64,
    high            Float64,
    low             Float64,
    close           Float64,
    volume          Float64
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list         = 'kafka:9092',
    kafka_topic_list          = 'trading.candles.1m,trading.candles.5m,trading.candles.1h',
    kafka_group_name          = 'clickhouse-candle-consumer',
    kafka_format              = 'JSONEachRow',
    kafka_num_consumers       = 2,
    kafka_max_block_size      = 65536;

-- 캔들 Kafka → candle_events 자동 저장 Materialized View
CREATE MATERIALIZED VIEW IF NOT EXISTS candle_events_mv
TO candle_events AS
SELECT
    event_id,
    parseDateTimeBestEffort(event_time) AS event_time,
    symbol,
    timeframe,
    CAST(open  AS Decimal(24, 8)) AS open,
    CAST(high  AS Decimal(24, 8)) AS high,
    CAST(low   AS Decimal(24, 8)) AS low,
    CAST(close AS Decimal(24, 8)) AS close,
    CAST(volume AS Decimal(24, 8)) AS volume
FROM candle_events_queue;

-- =============================================================================
-- 5. 실시간 집계 뷰 (MaterializedView - 사전 계산)
-- =============================================================================

-- 1시간 단위 OHLCV 집계 (실시간 갱신)
CREATE MATERIALIZED VIEW IF NOT EXISTS candle_hourly_agg
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (symbol, timeframe, hour)
AS
SELECT
    symbol,
    timeframe,
    toStartOfHour(event_time)       AS hour,
    minState(low)                   AS low_state,
    maxState(high)                  AS high_state,
    argMinState(open,  event_time)  AS open_state,
    argMaxState(close, event_time)  AS close_state,
    sumState(volume)                AS volume_state
FROM candle_events
GROUP BY symbol, timeframe, hour;

-- =============================================================================
-- 6. 분석 쿼리 예시 (주석)
-- =============================================================================

-- 최근 24시간 심볼별 OHLCV (1초 응답 목표)
-- SELECT
--     symbol,
--     toStartOfHour(event_time) AS hour,
--     max(high)                             AS high,
--     min(low)                              AS low,
--     argMax(open,  event_time)             AS open,
--     argMax(close, event_time)             AS close,
--     sum(volume)                           AS volume
-- FROM candle_events
-- WHERE event_time > now() - INTERVAL 24 HOUR
--   AND timeframe  = '1m'
-- GROUP BY symbol, hour
-- ORDER BY symbol, hour DESC;

-- 심볼별 거래량 Top 10 (오늘)
-- SELECT symbol, sum(volume) AS total_volume
-- FROM candle_events
-- WHERE event_time >= toStartOfDay(now())
--   AND timeframe = '1m'
-- GROUP BY symbol
-- ORDER BY total_volume DESC
-- LIMIT 10;

-- 특정 심볼 변동성 분석 (최근 7일)
-- SELECT
--     toDate(event_time) AS date,
--     stddevPop((close - open) / open * 100) AS daily_volatility_pct
-- FROM candle_events
-- WHERE symbol    = 'KRW-BTC'
--   AND timeframe = '1m'
--   AND event_time >= now() - INTERVAL 7 DAY
-- GROUP BY date
-- ORDER BY date DESC;
