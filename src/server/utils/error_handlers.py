#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
에러 핸들링 유틸리티

[Responsibilities]
- FastAPI 전역 에러 핸들러 등록
- 404, 422, 500 에러 응답 표준화
- 예외 로깅

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .response_formatter import format_error

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """
    FastAPI 앱에 전역 에러 핸들러 등록

    Args:
        app: FastAPI 인스턴스

    Example:
        ```python
        from fastapi import FastAPI
        from utils.error_handlers import register_error_handlers

        app = FastAPI()
        register_error_handlers(app)
        ```
    """
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_server_error)
    logger.debug("[ErrorHandlers] 에러 핸들러 등록 완료")


async def handle_http_exception(request: Request, exc: Any) -> JSONResponse:
    """
    HTTP 예외 처리 (404, 405, etc.)

    Args:
        request: HTTP 요청
        exc: StarletteHTTPException 인스턴스

    Returns:
        표준화된 에러 JSON 응답
    """
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", "요청 처리 실패")

    error_map = {
        404: ("not_found", "요청한 리소스를 찾을 수 없습니다."),
        405: ("method_not_allowed", "허용되지 않는 HTTP 메서드입니다."),
        403: ("forbidden", "접근 권한이 없습니다."),
        401: ("unauthorized", "인증이 필요합니다."),
        429: ("rate_limit_exceeded", "요청 빈도 제한을 초과했습니다."),
    }

    error_code, default_message = error_map.get(status_code, ("http_error", str(detail)))
    message = str(detail) if detail != default_message else default_message

    logger.debug("[ErrorHandlers] HTTP %d: %s", status_code, message)

    return JSONResponse(
        status_code=status_code,
        content=format_error(error_code=error_code, message=message),
    )


async def handle_not_found(request: Request, exc: Any) -> JSONResponse:
    """
    404 Not Found 처리

    Args:
        request: HTTP 요청
        exc: 예외

    Returns:
        404 JSON 응답
    """
    return JSONResponse(
        status_code=404,
        content=format_error(
            error_code="not_found",
            message=f"경로를 찾을 수 없습니다: {request.url.path}",
        ),
    )


async def handle_validation_error(request: Request, exc: Any) -> JSONResponse:
    """
    요청 유효성 검사 실패 처리 (422 Unprocessable Entity)

    Args:
        request: HTTP 요청
        exc: RequestValidationError 인스턴스

    Returns:
        422 JSON 응답
    """
    errors = []
    if hasattr(exc, "errors"):
        try:
            errors = exc.errors()
        except Exception:
            errors = [str(exc)]

    logger.debug("[ErrorHandlers] 유효성 검사 실패: %s", errors)

    return JSONResponse(
        status_code=422,
        content=format_error(
            error_code="validation_error",
            message="요청 파라미터가 유효하지 않습니다.",
            details=errors,
        ),
    )


async def handle_server_error(request: Request, exc: Exception) -> JSONResponse:
    """
    서버 내부 오류 처리 (500 Internal Server Error)

    Args:
        request: HTTP 요청
        exc: 예외

    Returns:
        500 JSON 응답
    """
    tb = traceback.format_exc()
    logger.error(
        "[ErrorHandlers] 내부 서버 오류: %s\n%s",
        exc,
        tb,
    )

    return JSONResponse(
        status_code=500,
        content=format_error(
            error_code="internal_server_error",
            message="서버 내부 오류가 발생했습니다.",
        ),
    )
