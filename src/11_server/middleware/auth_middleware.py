#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
JWT 인증 미들웨어

[Responsibilities]
- Authorization 헤더에서 JWT 토큰 추출 및 검증
- 제외 경로(health, docs 등) 인증 우회
- 유효하지 않은 토큰에 401 응답 반환

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 5.1

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# JWT 라이브러리 (옵션)
try:
    import jwt as pyjwt  # type: ignore
    JWT_AVAILABLE = True
except ImportError:
    pyjwt = None  # type: ignore
    JWT_AVAILABLE = False


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 인증 미들웨어

    ``Authorization: Bearer <token>`` 헤더를 통해 JWT 토큰을 검증합니다.
    exclude_paths에 포함된 경로는 인증 없이 접근을 허용합니다.

    Attributes:
        secret_key: JWT 서명 키
        algorithm: JWT 알고리즘
        exclude_paths: 인증 제외 경로 목록
    """

    def __init__(
        self,
        app: Any,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        exclude_paths: Optional[list] = None,
    ) -> None:
        super().__init__(app)
        self.secret_key: str = secret_key or os.getenv("JWT_SECRET_KEY", "upbit-trader-secret")
        self.algorithm: str = algorithm
        self.exclude_paths: set = set(
            exclude_paths
            or ["/health", "/docs", "/openapi.json", "/redoc", "/api/v1/health"]
        )

        if not JWT_AVAILABLE:
            logger.warning("[AuthMiddleware] PyJWT 없음 - 인증 비활성화")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청 처리 - JWT 검증"""
        path = request.url.path

        # 제외 경로 또는 JWT 미사용 시 통과
        if not JWT_AVAILABLE or any(path.startswith(ep) for ep in self.exclude_paths):
            return await call_next(request)

        token = self._extract_token(request)

        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": "인증 토큰이 없습니다."},
            )

        payload = self._verify_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_token", "message": "유효하지 않은 토큰입니다."},
            )

        # 요청 상태에 사용자 정보 추가
        request.state.user = payload.get("sub")
        request.state.session_id = payload.get("sid")

        return await call_next(request)

    def _extract_token(self, request: Request) -> Optional[str]:
        """Authorization 헤더에서 Bearer 토큰 추출"""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    def _verify_token(self, token: str) -> Optional[dict]:
        """JWT 토큰 검증"""
        if not JWT_AVAILABLE or pyjwt is None:
            return None
        try:
            return pyjwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except Exception as exc:
            logger.debug("[AuthMiddleware] 토큰 검증 실패: %s", exc)
            return None
