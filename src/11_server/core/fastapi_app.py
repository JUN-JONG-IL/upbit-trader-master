#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
FastAPI 애플리케이션 - API Gateway

[Responsibilities]
- REST API 라우팅
- WebSocket 연결
- 미들웨어 등록 (Auth, CORS, Rate Limit)
- API 버전 관리 (/api/v1)

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 5.1

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..middleware.rate_limiter import RateLimitMiddleware
from ..middleware.auth_middleware import AuthMiddleware
from ..utils.error_handlers import register_error_handlers
from ..api.health import router as health_router
from ..api.candles import router as candles_router
from ..api.symbols import router as symbols_router
from ..api.orders import router as orders_router

logger = logging.getLogger(__name__)


def create_app(
    title: str = "Upbit Trader API",
    version: str = "1.0.0",
    rate_limit: int = 10,
    cors_origins: Optional[list] = None,
    enable_auth: bool = False,
    auth_exclude_paths: Optional[list] = None,
) -> FastAPI:
    """
    FastAPI 애플리케이션 팩토리

    Args:
        title: API 제목
        version: API 버전
        rate_limit: Rate Limit (초당 요청 수)
        cors_origins: 허용 CORS 오리진 목록 (None이면 전체 허용)
        enable_auth: JWT 인증 미들웨어 활성화 여부
        auth_exclude_paths: 인증 제외 경로 목록

    Returns:
        FastAPI: 구성된 FastAPI 인스턴스
    """
    if cors_origins is None:
        cors_origins = ["*"]
    if auth_exclude_paths is None:
        auth_exclude_paths = ["/health", "/docs", "/openapi.json", "/redoc"]

    application = FastAPI(
        title=title,
        version=version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        description=(
            "Upbit 자동매매 시스템 API Gateway\n\n"
            "## 엔드포인트\n"
            "- `/api/v1/health` - 서비스 상태 확인\n"
            "- `/api/v1/candles/{symbol}` - 캔들 데이터 조회\n"
            "- `/api/v1/symbols` - 심볼 목록 조회\n"
            "- `/api/v1/orders` - 주문 관리\n"
        ),
    )

    # ── CORS 미들웨어 ──────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate Limit 미들웨어 (초당 N회) ────────────────────────────────────────
    application.add_middleware(RateLimitMiddleware, rate_limit=rate_limit)

    # ── JWT 인증 미들웨어 (옵션) ───────────────────────────────────────────────
    if enable_auth:
        application.add_middleware(
            AuthMiddleware,
            exclude_paths=auth_exclude_paths,
        )

    # ── API 라우터 등록 ───────────────────────────────────────────────────────
    _prefix = "/api/v1"
    application.include_router(health_router, prefix=_prefix, tags=["Health"])
    application.include_router(candles_router, prefix=_prefix, tags=["Candles"])
    application.include_router(symbols_router, prefix=_prefix, tags=["Symbols"])
    application.include_router(orders_router, prefix=_prefix, tags=["Orders"])

    # ── 에러 핸들러 등록 ──────────────────────────────────────────────────────
    register_error_handlers(application)

    # ── 루트 엔드포인트 ───────────────────────────────────────────────────────
    @application.get("/", tags=["Root"], include_in_schema=False)
    async def root():
        return {
            "service": "Upbit Trader API",
            "version": version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    logger.info("[FastAPIApp] Application created (version=%s)", version)
    return application


# 기본 앱 인스턴스 (uvicorn 실행 시 참조)
app: FastAPI = create_app()
