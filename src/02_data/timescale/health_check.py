#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimescaleDB 연결 상태 확인

check_timescale_connection() → "green" | "red" | "gray"

기존 TimescaleConnector(psycopg2 기반)의 연결 풀을 재사용하여
포트 고갈(Address already in use / WinError 10048)을 방지합니다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

STATUS_GREEN = "green"
STATUS_RED   = "red"
STATUS_GRAY  = "gray"

# 연결 상태 캐시
_connection_status_cache = None


def check_timescale_connection() -> str:
    """
    TimescaleDB 연결 상태를 확인합니다.
    기존 TimescaleConnector 연결 풀을 재사용합니다.

    Returns:
        "green" — 정상 연결
        "red"   — 연결 실패
        "gray"  — psycopg2 미설치 또는 설정 없음
    """
    global _connection_status_cache

    try:
        from .timescale_db import TimescaleConnector  # type: ignore
    except Exception:
        try:
            from timescale.timescale_db import TimescaleConnector  # type: ignore
        except Exception:
            if _connection_status_cache != STATUS_GRAY:
                logger.warning("[TimescaleHealthCheck] TimescaleConnector 로드 실패")
                _connection_status_cache = STATUS_GRAY
            return STATUS_GRAY

    try:
        conn = TimescaleConnector()
        if conn.connect():
            try:
                conn.execute("SELECT 1")
                if _connection_status_cache != STATUS_GREEN:
                    logger.info("[TimescaleHealthCheck] TimescaleDB 연결 성공")
                    _connection_status_cache = STATUS_GREEN
                return STATUS_GREEN
            finally:
                conn.close()
        else:
            if _connection_status_cache != STATUS_RED:
                logger.warning("[TimescaleHealthCheck] TimescaleConnector 연결 실패")
                _connection_status_cache = STATUS_RED
            return STATUS_RED
    except Exception as e:
        if _connection_status_cache != STATUS_RED:
            logger.warning("[TimescaleHealthCheck] 연결 실패: %s", e)
            _connection_status_cache = STATUS_RED
        return STATUS_RED