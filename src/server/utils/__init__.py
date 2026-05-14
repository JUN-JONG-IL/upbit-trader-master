# name=src/server/utils/__init__.py
# -*- coding: utf-8 -*-
"""
utils 패키지 초기화
- 목적: 공통 유틸리티(ResponseFormatter, error handler 등)를 노출.
- 안정성: 하위 모듈이 없거나 import 중 에러가 발생해도 패키지 임포트 전체가 실패하지 않도록 방어 로직 추가.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

_log = logging.getLogger(__name__)

__all__ = [
    "ResponseFormatter",
    "format_success",
    "format_error",
    "handle_not_found",
    "handle_server_error",
    "handle_validation_error",
    "register_error_handlers",
]

# -----------------------------
# ResponseFormatter 로드(방어적)
# -----------------------------
try:
    # 실제 구현이 존재하면 그것을 사용
    from .response_formatter import ResponseFormatter, format_success, format_error  # type: ignore
except Exception as _err:
    # 디버그 로그: 원인 파악용
    _log.debug("utils.response_formatter import failed: %s", _err, exc_info=True)

    # 최소 대체 구현: 실제 구현이 없을 때 시스템의 다른 부분이 호출해도 동작하도록 함
    class ResponseFormatter:
        """간단한 대체 포매터 (실제 구현이 로드되지 않았을 때 사용)"""

        @staticmethod
        def success(data: Any = None, message: str = "ok") -> Dict[str, Any]:
            return {"status": "success", "message": message, "data": data}

        @staticmethod
        def error(error: Any = None, code: int = 500, message: str = "error") -> Dict[str, Any]:
            return {"status": "error", "code": code, "message": message, "detail": str(error)}

    def format_success(data: Any = None, message: str = "ok") -> Dict[str, Any]:
        return ResponseFormatter.success(data=data, message=message)

    def format_error(error: Any = None, code: int = 500, message: str = "error") -> Dict[str, Any]:
        return ResponseFormatter.error(error=error, code=code, message=message)


# -----------------------------
# Error handlers 로드(방어적)
# -----------------------------
try:
    from .error_handlers import (  # type: ignore
        handle_not_found,
        handle_server_error,
        handle_validation_error,
        register_error_handlers,
    )
except Exception as _err:
    _log.debug("utils.error_handlers import failed: %s", _err, exc_info=True)

    # 대체 핸들러들: Flask/FastAPI 등에서 사용 시 최소한의 응답을 반환하도록 함
    def handle_not_found(exc: Exception):
        _log.warning("handle_not_found fallback invoked: %s", exc)
        return format_error(exc, code=404, message="Not Found")

    def handle_server_error(exc: Exception):
        _log.warning("handle_server_error fallback invoked: %s", exc)
        return format_error(exc, code=500, message="Internal Server Error")

    def handle_validation_error(exc: Exception):
        _log.warning("handle_validation_error fallback invoked: %s", exc)
        return format_error(exc, code=400, message="Validation Error")

    def register_error_handlers(app: Any):
        """
        대체 register 함수: 애플리케이션 객체에 에러 핸들러를 등록하려 할 때
        실제 error_handlers 모듈이 있으면 그게 호출되도록 하고, 없으면 로그만 남김.
        """
        _log.debug("register_error_handlers fallback invoked for app=%s", getattr(app, "__class__", app))


# __all__ 은 위에서 정의한 이름을 유지