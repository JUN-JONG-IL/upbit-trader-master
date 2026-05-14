#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MongoDB 연결 관리 (motor 비동기)"""
import logging
from typing import Optional, Any
from .config import MongoConfig, get_config

try:
    import motor.motor_asyncio as motor
    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False
    motor = None  # type: ignore

LOG = logging.getLogger("mongo.connection")

_client: Optional[Any] = None
_db: Optional[Any] = None


async def get_db(config: Optional[MongoConfig] = None) -> Optional[Any]:
    """싱글톤 MongoDB 데이터베이스 반환"""
    global _client, _db
    if _db is None:
        await create_connection(config)
    return _db


async def create_connection(config: Optional[MongoConfig] = None) -> Optional[Any]:
    """MongoDB 연결 생성"""
    global _client, _db
    if not MOTOR_AVAILABLE:
        LOG.warning("⚠️  motor 미설치 - MongoDB 연결 불가")
        return None
    cfg = config or get_config()
    try:
        _client = motor.AsyncIOMotorClient(
            cfg.get_uri(),
            maxPoolSize=cfg.max_pool_size,
            serverSelectionTimeoutMS=5000,
        )
        _db = _client[cfg.database]
        # 연결 확인
        await _client.admin.command("ping")
        LOG.info("✅ MongoDB 연결 완료 (%s:%d/%s)", cfg.host, cfg.port, cfg.database)
    except Exception as e:
        LOG.error("❌ MongoDB 연결 실패: %s", e)
        _client = None
        _db = None
    return _db


async def close_connection():
    """MongoDB 연결 종료"""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        LOG.info("✅ MongoDB 연결 종료")
