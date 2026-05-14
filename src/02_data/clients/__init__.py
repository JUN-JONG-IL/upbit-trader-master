"""
src/02_data/clients — 데이터베이스 클라이언트 패키지 (구 src/db/)

모듈:
  timescale          : TimescaleDB 클라이언트
  redis_client       : Redis 클라이언트
  mongo_client       : MongoDB 클라이언트
  upbit_data_provider: Upbit API 데이터 제공자 (pyupbit 래핑)

CHANGELOG:
- 2026-03-19 | Copilot | upbit_data_provider 추가 (src/06_ai/priority/services/ → clients/ 이동)
"""

from .timescale import TimescaleClient, get_timescale_pool
from .redis_client import RedisClient, get_redis_client
from .mongo_client import MongoClient, get_mongo_db
from .upbit_data_provider import UpbitDataProvider

__all__ = [
    "TimescaleClient",
    "get_timescale_pool",
    "RedisClient",
    "get_redis_client",
    "MongoClient",
    "get_mongo_db",
    "UpbitDataProvider",
]
