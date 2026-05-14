#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL CQRS Event Store — 연결 풀 관리

목적:
    CQRS 패턴의 PostgreSQL Primary/Replica 연결 풀을 제공합니다.
    Primary: 쓰기 전용 (이벤트 INSERT)
    Replica: 읽기 전용 (이벤트 조회, Read Model 빌드)

환경 변수:
    POSTGRES_PRIMARY_HOST  (기본값: localhost)
    POSTGRES_PRIMARY_PORT  (기본값: 5433)
    POSTGRES_PRIMARY_DB    (기본값: trading)
    POSTGRES_PRIMARY_USER  (기본값: trader)
    POSTGRES_PRIMARY_PASSWORD
    POSTGRES_REPLICA_HOST  (기본값: localhost, Primary와 동일)
    POSTGRES_REPLICA_PORT  (기본값: 5434)
    POSTGRES_REPLICA_DB    (기본값: trading)
    POSTGRES_REPLICA_USER  (기본값: trader)
    POSTGRES_REPLICA_PASSWORD
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import asyncpg  # type: ignore
    _ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None  # type: ignore
    _ASYNCPG_AVAILABLE = False

# 싱글톤 풀
_primary_pool: Optional[object] = None
_replica_pool: Optional[object] = None


def _pg_dsn(prefix: str) -> dict:
    """환경 변수에서 PostgreSQL DSN 파라미터를 읽습니다."""
    return {
        "host": os.getenv(f"{prefix}_HOST", "localhost"),
        "port": int(os.getenv(f"{prefix}_PORT", "5433" if prefix == "POSTGRES_PRIMARY" else "5434")),
        "database": os.getenv(f"{prefix}_DB", "trading"),
        "user": os.getenv(f"{prefix}_USER", "trader"),
        "password": os.getenv(f"{prefix}_PASSWORD", ""),
    }


async def get_pool(replica: bool = False) -> Optional["asyncpg.Pool"]:
    """Primary 또는 Replica 연결 풀을 반환합니다.

    Args:
        replica: True이면 Replica 풀, False이면 Primary 풀 반환.

    Returns:
        asyncpg.Pool 또는 None (asyncpg 미설치 시).
    """
    if replica:
        global _replica_pool
        if _replica_pool is None:
            _replica_pool = await create_pool(replica=True)
        return _replica_pool
    else:
        global _primary_pool
        if _primary_pool is None:
            _primary_pool = await create_pool(replica=False)
        return _primary_pool


async def create_pool(
    replica: bool = False,
    min_size: int = 5,
    max_size: int = 10,
) -> Optional["asyncpg.Pool"]:
    """새 asyncpg 연결 풀을 생성합니다.

    Args:
        replica:  True이면 Replica 연결, False이면 Primary 연결.
        min_size: 최소 연결 수.
        max_size: 최대 연결 수.

    Returns:
        asyncpg.Pool 또는 None (asyncpg 미설치 또는 연결 실패 시).
    """
    if not _ASYNCPG_AVAILABLE:
        logger.warning("asyncpg 미설치 — PostgreSQL 연결 불가")
        return None

    prefix = "POSTGRES_REPLICA" if replica else "POSTGRES_PRIMARY"
    dsn = _pg_dsn(prefix)
    role = "replica" if replica else "primary"
    try:
        pool = await asyncpg.create_pool(
            **dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=30,
        )
        logger.info(
            "✅ PostgreSQL %s 연결 풀 생성 (%s:%d/%s, min=%d max=%d)",
            role,
            dsn["host"],
            dsn["port"],
            dsn["database"],
            min_size,
            max_size,
        )
        return pool
    except Exception as exc:
        logger.error("❌ PostgreSQL %s 연결 실패: %s", role, exc)
        return None


async def close_pool(replica: bool = False) -> None:
    """연결 풀을 종료합니다.

    Args:
        replica: True이면 Replica 풀 종료, False이면 Primary 풀 종료.
    """
    global _primary_pool, _replica_pool
    if replica:
        if _replica_pool:
            await _replica_pool.close()
            _replica_pool = None
            logger.info("✅ PostgreSQL replica 연결 풀 종료")
    else:
        if _primary_pool:
            await _primary_pool.close()
            _primary_pool = None
            logger.info("✅ PostgreSQL primary 연결 풀 종료")


async def close_all() -> None:
    """Primary 및 Replica 연결 풀을 모두 종료합니다."""
    await close_pool(replica=False)
    await close_pool(replica=True)
