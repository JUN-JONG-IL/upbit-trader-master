#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
CORS 설정 모듈

[Responsibilities]
- FastAPI 앱에 CORSMiddleware 등록
- 환경별 오리진 허용 정책 설정
- 개발/운영 환경 분리

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 5.1

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

_DEFAULT_ALLOW_ORIGINS = ["*"]
_PRODUCTION_ORIGINS = [
    "http://localhost:8080",
    "http://localhost:3000",
]


def setup_cors(
    app: FastAPI,
    allow_origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> None:
    """
    FastAPI 앱에 CORS 미들웨어 등록

    환경변수 ``CORS_ORIGINS`` (콤마 구분)로 허용 오리진을 동적으로 설정할 수 있습니다.

    Args:
        app: FastAPI 인스턴스
        allow_origins: 허용 오리진 목록 (None이면 env 또는 기본값 사용)
        allow_credentials: 자격증명 허용 여부
        allow_methods: 허용 HTTP 메서드 목록
        allow_headers: 허용 HTTP 헤더 목록

    Example:
        ```python
        from fastapi import FastAPI
        from middleware.cors_middleware import setup_cors

        app = FastAPI()
        setup_cors(app, allow_origins=["http://localhost:3000"])
        ```
    """
    if allow_methods is None:
        allow_methods = ["*"]
    if allow_headers is None:
        allow_headers = ["*"]

    # 환경변수에서 오리진 로드
    if allow_origins is None:
        env_origins = os.getenv("CORS_ORIGINS", "")
        if env_origins:
            allow_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
        else:
            env = os.getenv("APP_ENV", "development").lower()
            allow_origins = _DEFAULT_ALLOW_ORIGINS if env == "development" else _PRODUCTION_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )

    logger.debug("[CORS] 허용 오리진: %s", allow_origins)


def get_cors_origins() -> List[str]:
    """
    현재 환경에 맞는 CORS 허용 오리진 반환

    Returns:
        허용 오리진 목록
    """
    env_origins = os.getenv("CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    env = os.getenv("APP_ENV", "development").lower()
    return _DEFAULT_ALLOW_ORIGINS if env == "development" else _PRODUCTION_ORIGINS
