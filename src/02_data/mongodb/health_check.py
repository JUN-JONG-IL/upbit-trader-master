#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 연결 상태 확인

check_mongo_connection() → "green" | "red" | "gray"
"""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

# 연결 상태 상수
STATUS_GREEN = "green"   # 정상 연결
STATUS_RED   = "red"     # 연결 오류
STATUS_GRAY  = "gray"    # 미설정 / 드라이버 없음

# 연결 상태 캐시 (앱 실행 중 한 번만 로깅)
_connection_status_cache = None
_initial_log_done = False

# 싱글톤 MongoClient (포트 고갈 방지: 연결 풀 재사용)
_mongo_client_singleton = None
_mongo_client_uri_cache: str | None = None
_mongo_client_lock = threading.Lock()


def _get_mongo_client(uri: str):
    """URI에 대한 싱글톤 MongoClient를 반환합니다. 스레드 안전."""
    global _mongo_client_singleton, _mongo_client_uri_cache
    from pymongo import MongoClient  # type: ignore

    with _mongo_client_lock:
        if _mongo_client_singleton is None or _mongo_client_uri_cache != uri:
            _mongo_client_singleton = MongoClient(
                uri,
                serverSelectionTimeoutMS=2000,
                directConnection=True,
                maxPoolSize=10,
                minPoolSize=1,
            )
            _mongo_client_uri_cache = uri
    return _mongo_client_singleton


def check_mongo_connection() -> str:
    """
    MongoDB 연결 상태를 확인합니다.
    싱글톤 연결 풀을 재사용하여 포트 고갈(WinError 10048)을 방지합니다.

    Returns:
        "green"  — 정상 연결
        "red"    — 연결 실패
        "gray"   — pymongo 미설치
    """
    global _connection_status_cache, _initial_log_done
    
    try:
        import pymongo  # type: ignore  # noqa: F401
    except ImportError:
        if not _initial_log_done:
            logger.debug("[MongoHealthCheck] pymongo 미설치")
            _initial_log_done = True
        return STATUS_GRAY

    # 우선순위 1: MONGO_URI 환경변수 (완성된 URI)
    uri = os.getenv("MONGO_URI")
    
    if not uri:
        # 우선순위 2: 개별 설정으로 URI 구성
        host = os.getenv("MONGO_HOST", "localhost")
        port = int(os.getenv("MONGO_PORT", "27017"))
        
        # 인증 정보 (없으면 인증 없이 연결)
        user = (
            os.getenv("MONGO_INITDB_ROOT_USERNAME")
            or os.getenv("MONGO_USER")
        )
        password = (
            os.getenv("MONGO_INITDB_ROOT_PASSWORD")
            or os.getenv("MONGO_PASSWORD")
        )

        if user and password:
            from urllib.parse import quote_plus
            uri = (
                f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
                f"@{host}:{port}/?authSource=admin"
            )
        else:
            uri = f"mongodb://{host}:{port}/"

    try:
        client = _get_mongo_client(uri)
        client.admin.command("ping")
        
        # 최초 연결 성공 시에만 로깅
        if _connection_status_cache != STATUS_GREEN:
            logger.info("[MongoHealthCheck] MongoDB 연결 성공")
            _connection_status_cache = STATUS_GREEN
            _initial_log_done = True
        
        return STATUS_GREEN
    except Exception as e:
        # 최초 실패 시에만 로깅
        if _connection_status_cache != STATUS_RED:
            logger.warning("[MongoHealthCheck] 연결 실패: %s", e)
            _connection_status_cache = STATUS_RED
            _initial_log_done = True
        
        return STATUS_RED