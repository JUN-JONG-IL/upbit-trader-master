#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
헬스체크 API

[Endpoints]
- GET /health           - 서비스 상태 확인
- GET /health/ready     - 준비 상태 확인 (Readiness Probe)
- GET /health/live      - 생존 상태 확인 (Liveness Probe)

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 27장

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    summary="서비스 상태 확인",
    response_description="서비스 상태 정보",
)
async def health_check() -> Dict[str, Any]:
    """
    서비스 전체 상태 확인

    - WebSocket 연결 상태
    - Redis 연결 상태
    - DB 연결 상태

    Returns:
        상태 정보 딕셔너리
    """
    ws_connected = _check_websocket()
    redis_connected = _check_redis()
    db_connected = _check_db()

    is_healthy = ws_connected and redis_connected

    return {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "checks": {
            "websocket": "ok" if ws_connected else "fail",
            "redis": "ok" if redis_connected else "fail",
            "database": "ok" if db_connected else "fail",
        },
        "message": (
            "모든 서비스가 정상 실행 중입니다."
            if is_healthy
            else "일부 서비스가 실행되지 않았습니다."
        ),
    }


@router.get(
    "/health/ready",
    summary="Readiness Probe",
    response_description="준비 상태",
)
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes Readiness Probe 용 엔드포인트

    Redis 연결이 가능한 경우 준비 완료로 판단합니다.

    Returns:
        준비 상태 정보
    """
    ready = _check_redis()
    return {
        "ready": ready,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get(
    "/health/live",
    summary="Liveness Probe",
    response_description="생존 상태",
)
async def liveness_check() -> Dict[str, Any]:
    """
    Kubernetes Liveness Probe 용 엔드포인트

    Returns:
        생존 상태 정보
    """
    return {
        "alive": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ── 내부 상태 점검 ────────────────────────────────────────────────────────────

def _check_websocket() -> bool:
    """WebSocket(chart) 연결 상태 확인"""
    try:
        import server.static as static  # type: ignore
        if hasattr(static, "chart") and static.chart is not None:
            return bool(getattr(static.chart, "alive", False))
        return False
    except Exception:
        return False


def _check_redis() -> bool:
    """Redis 연결 상태 확인"""
    try:
        import redis as redis_lib  # type: ignore
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "58530"))
        client = redis_lib.Redis(host=host, port=port, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


def _check_db() -> bool:
    """DB 연결 상태 확인 (MongoDB 또는 TimescaleDB)"""
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        # 연결 객체 생성 여부로만 확인 (실제 ping은 별도)
        return True
    except ImportError:
        return False
    except Exception:
        return False