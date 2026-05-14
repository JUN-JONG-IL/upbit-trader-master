# -*- coding: utf-8 -*-
"""
DB 연결 상태 조회 함수 (v1.0)

각 DB/서비스의 연결 가능 여부를 문자열("connected" / "disconnected")로 반환합니다.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import socket
import types
from pathlib import Path
from typing import Any, Optional

from .db_connectors import (
    get_mongo_sync_client,
    get_redis_connector,
    get_timescale_connector,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constants.py 로드 (core 패키지명이 Python 식별자 규칙 위반으로 직접 import 불가)
# ---------------------------------------------------------------------------
_CONST_PATH = Path(__file__).parents[3] / "core" / "config" / "constants.py"

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_db_status_consts", str(_CONST_PATH))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        logger.debug("[db_status] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()

# 각 DB/서비스 기본 포트 (constants.py → 폴백 값 순서)
_CLICKHOUSE_DEFAULT_PORT: int = getattr(_CONSTS, "DEFAULT_CLICKHOUSE_PORT", 8123)
_MLFLOW_DEFAULT_PORT: int = getattr(_CONSTS, "DEFAULT_MLFLOW_PORT", 5000)
_POSTGRES_DEFAULT_PORT: int = getattr(_CONSTS, "DEFAULT_POSTGRES_PRIMARY_PORT", 5433)
_KAFKA_DEFAULT_PORT: int = getattr(_CONSTS, "DEFAULT_KAFKA_PORT", 9092)
# TCP 연결 타임아웃 (초)
_TCP_TIMEOUT: float = 2.0


def get_timescale_status() -> str:
    """TimescaleDB 연결 상태 조회.

    Returns:
        "connected" 또는 "disconnected"
    """
    try:
        conn = get_timescale_connector()
        if conn is not None:
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_timescale_status 실패: %s", e)
    return "disconnected"


def get_redis_status() -> str:
    """Redis 연결 상태 조회.

    Returns:
        "connected" 또는 "disconnected"
    """
    try:
        rc = get_redis_connector()
        if rc is not None:
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_redis_status 실패: %s", e)
    return "disconnected"


def get_mongo_status() -> str:
    """MongoDB 연결 상태 조회.

    Returns:
        "connected" 또는 "disconnected"
    """
    try:
        client = get_mongo_sync_client()
        if client is not None:
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_mongo_status 실패: %s", e)
    return "disconnected"


def get_postgres_status() -> str:
    """PostgreSQL 연결 상태 조회 (TCP 프로브).

    환경 변수:
        POSTGRES_HOST: 호스트 (기본값: 127.0.0.1)
        POSTGRES_PORT: 포트 (기본값: 5433)

    Returns:
        "connected" 또는 "disconnected"
    """
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", str(_POSTGRES_DEFAULT_PORT)))
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT):
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_postgres_status 실패 (%s:%d): %s", host, port, e)
    return "disconnected"


def get_kafka_status() -> str:
    """Kafka 연결 상태 조회 (TCP 프로브).

    환경 변수:
        KAFKA_HOST: 호스트 (기본값: 127.0.0.1)
        KAFKA_PORT: 포트 (기본값: 9092)

    Returns:
        "connected" 또는 "disconnected"
    """
    host = os.getenv("KAFKA_HOST", "127.0.0.1")
    port = int(os.getenv("KAFKA_PORT", str(_KAFKA_DEFAULT_PORT)))
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT):
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_kafka_status 실패 (%s:%d): %s", host, port, e)
    return "disconnected"


def get_clickhouse_status() -> str:
    """ClickHouse 연결 상태 조회 (TCP 프로브, HTTP 인터페이스 포트).

    환경 변수:
        CLICKHOUSE_HOST: 호스트 (기본값: 127.0.0.1)
        CLICKHOUSE_PORT: 포트 (기본값: 8123)

    Returns:
        "connected" 또는 "disconnected"
    """
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("CLICKHOUSE_PORT", str(_CLICKHOUSE_DEFAULT_PORT)))
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT):
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_clickhouse_status 실패 (%s:%d): %s", host, port, e)
    return "disconnected"


def get_mlflow_status() -> str:
    """MLflow 연결 상태 조회 (TCP 프로브).

    환경 변수:
        MLFLOW_HOST: 호스트 (기본값: 127.0.0.1)
        MLFLOW_PORT: 포트 (기본값: 5000)

    Returns:
        "connected" 또는 "disconnected"
    """
    host = os.getenv("MLFLOW_HOST", "127.0.0.1")
    port = int(os.getenv("MLFLOW_PORT", str(_MLFLOW_DEFAULT_PORT)))
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT):
            return "connected"
    except Exception as e:
        logger.debug("[UI Utils] get_mlflow_status 실패 (%s:%d): %s", host, port, e)
    return "disconnected"


def get_gap_queue_size() -> int:
    """Redis Sorted Set 'gap_fill_queue' 의 항목 수 반환.

    Returns:
        gap_fill_queue 의 항목 수 (Redis 연결 불가 시 0)
    """
    rc = get_redis_connector()
    if rc is None:
        return 0
    try:
        return int(rc.zcard("gap_fill_queue") or 0)
    except Exception as e:
        logger.debug("[UI Utils] get_gap_queue_size 실패: %s", e)
        return 0
