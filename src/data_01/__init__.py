"""
Data Layer - TimescaleDB, Redis, MongoDB, Feature Store

[Purpose]
Unified data access layer for the Upbit trading system.

[Modules]
- timescale: TimescaleDB operations (time-series candle/trade data, 10-stage pipeline)
- redis:     Redis operations (L1 cache, pub/sub, gap-fill queue)
- mongodb:   MongoDB operations (document storage for orders, settings, positions)
- features:  AI/ML feature engineering and feature store
- pipeline:  10단계 데이터 수집 파이프라인 (구 src/data_pipeline/)
- clients:   데이터베이스 클라이언트 (구 src/db/)
- gap:       Gap Detection 패키지 (구 src/gap/)
"""

try:
    from .timescale import (
        TimescaleConfig, get_pool, create_pool, close_pool,
        DataChecker, DataStager, DataFinalizer,
    )
except Exception:
    pass

try:
    from .redis import RedisConfig, get_client, L1Cache
except Exception:
    pass

try:
    from .mongodb import MongoConfig, get_db, SymbolManager, SettingsManager
except Exception:
    pass

try:
    from .features import FeatureStore, FeatureEngineer, Normalizer
except Exception:
    pass

try:
    from .kafka import get_producer, get_consumer
except Exception:
    pass

try:
    from .clickhouse import get_client as get_clickhouse_client
except Exception:
    pass

__all__ = [
    # TimescaleDB
    'TimescaleConfig', 'get_pool', 'create_pool', 'close_pool',
    'DataChecker', 'DataStager', 'DataFinalizer',
    # Redis
    'RedisConfig', 'get_client', 'L1Cache',
    # MongoDB
    'MongoConfig', 'get_db', 'SymbolManager', 'SettingsManager',
    # Features
    'FeatureStore', 'FeatureEngineer', 'Normalizer',
    # Kafka
    'get_producer', 'get_consumer',
    # ClickHouse
    'get_clickhouse_client',
]
