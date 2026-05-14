# -*- coding: utf-8 -*-
"""
src/core/config/constants.py
DB 연결 기본값 상수 모음

실제 환경 스펙 (work_order/DB설계1.md 기준):
    TimescaleDB : 127.0.0.1:58529  (Docker: 58529:5432)
    Redis       : 127.0.0.1:58530  (Docker: 58530:6379)
    PostgreSQL Primary : 127.0.0.1:5433  (Docker: 5433:5432)
    PostgreSQL Replica : 127.0.0.1:5434  (Docker: 5434:5432)
    MongoDB     : localhost:27017
    Kafka       : localhost:9092
    ClickHouse  : 127.0.0.1:8123

주의:
    - 코드에서 포트 번호를 직접 하드코딩하지 말고 이 파일의 상수를 import하여 사용.
    - 환경변수 우선 순위: 환경변수 → .env 파일 → 이 파일의 기본값.
"""

# ---------------------------------------------------------------------------
# TimescaleDB (Warm Tier) — Docker: 127.0.0.1:58529:5432
# ---------------------------------------------------------------------------
DEFAULT_TIMESCALE_HOST: str = "127.0.0.1"
DEFAULT_TIMESCALE_PORT: int = 58529
DEFAULT_TIMESCALE_USER: str = "postgres"
DEFAULT_TIMESCALE_DB: str = "upbit_trader"

# ---------------------------------------------------------------------------
# Redis (Hot Tier) — Docker: 127.0.0.1:58530:6379
# ---------------------------------------------------------------------------
DEFAULT_REDIS_HOST: str = "127.0.0.1"
DEFAULT_REDIS_PORT: int = 58530

# ---------------------------------------------------------------------------
# PostgreSQL Primary (Core Tier) — Docker: 127.0.0.1:5433:5432
# PostgreSQL Replica             — Docker: 127.0.0.1:5434:5432
# ---------------------------------------------------------------------------
DEFAULT_POSTGRES_PRIMARY_HOST: str = "127.0.0.1"
DEFAULT_POSTGRES_PRIMARY_PORT: int = 5433
DEFAULT_POSTGRES_REPLICA_PORT: int = 5434
DEFAULT_POSTGRES_USER: str = "postgres"
DEFAULT_POSTGRES_DB: str = "upbit_trader"

# ---------------------------------------------------------------------------
# MongoDB (Core Tier)
# ---------------------------------------------------------------------------
DEFAULT_MONGO_HOST: str = "localhost"
DEFAULT_MONGO_PORT: int = 27017

# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------
DEFAULT_KAFKA_HOST: str = "127.0.0.1"
DEFAULT_KAFKA_PORT: int = 9092

# ---------------------------------------------------------------------------
# ClickHouse (Cold Tier) — HTTP 인터페이스 포트
# ---------------------------------------------------------------------------
DEFAULT_CLICKHOUSE_HOST: str = "127.0.0.1"
DEFAULT_CLICKHOUSE_PORT: int = 8123

# ---------------------------------------------------------------------------
# MLflow
# ---------------------------------------------------------------------------
DEFAULT_MLFLOW_HOST: str = "127.0.0.1"
DEFAULT_MLFLOW_PORT: int = 5000
