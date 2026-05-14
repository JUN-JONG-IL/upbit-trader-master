#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
API 응답 포맷팅 유틸리티

[Responsibilities]
- 표준화된 성공/에러 응답 딕셔너리 생성
- 페이지네이션 응답 생성
- 타임스탬프 자동 포함

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional


class ResponseFormatter:
    """
    API 응답 포맷터

    일관된 응답 구조를 보장합니다:

    성공 응답::

        {
            "success": true,
            "data": {...},
            "timestamp": "2026-03-06T00:00:00+00:00"
        }

    에러 응답::

        {
            "success": false,
            "error": "error_code",
            "message": "설명",
            "timestamp": "2026-03-06T00:00:00+00:00"
        }
    """

    @staticmethod
    def success(
        data: Any = None,
        message: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        성공 응답 생성

        Args:
            data: 응답 데이터
            message: 선택적 메시지
            **extra: 추가 필드

        Returns:
            표준화된 성공 응답 딕셔너리
        """
        response: Dict[str, Any] = {
            "success": True,
            "timestamp": _now_iso(),
        }
        if data is not None:
            response["data"] = data
        if message:
            response["message"] = message
        response.update(extra)
        return response

    @staticmethod
    def error(
        error_code: str,
        message: str,
        details: Optional[Any] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        에러 응답 생성

        Args:
            error_code: 에러 코드 (snake_case)
            message: 사람이 읽을 수 있는 설명
            details: 추가 디버그 정보 (선택)
            **extra: 추가 필드

        Returns:
            표준화된 에러 응답 딕셔너리
        """
        response: Dict[str, Any] = {
            "success": False,
            "error": error_code,
            "message": message,
            "timestamp": _now_iso(),
        }
        if details is not None:
            response["details"] = details
        response.update(extra)
        return response

    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 100,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        페이지네이션 응답 생성

        Args:
            items: 현재 페이지 아이템 목록
            total: 전체 아이템 수
            page: 현재 페이지 번호 (1-based)
            page_size: 페이지 크기
            **extra: 추가 필드

        Returns:
            페이지네이션 응답 딕셔너리
        """
        import math
        total_pages = max(1, math.ceil(total / page_size)) if page_size > 0 else 1
        response: Dict[str, Any] = {
            "success": True,
            "data": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "timestamp": _now_iso(),
        }
        response.update(extra)
        return response


def format_success(data: Any = None, message: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    """
    성공 응답 포맷 (함수형 인터페이스)

    Args:
        data: 응답 데이터
        message: 선택적 메시지
        **extra: 추가 필드

    Returns:
        표준화된 성공 응답 딕셔너리
    """
    return ResponseFormatter.success(data=data, message=message, **extra)


def format_error(
    error_code: str,
    message: str,
    details: Optional[Any] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    에러 응답 포맷 (함수형 인터페이스)

    Args:
        error_code: 에러 코드
        message: 설명
        details: 추가 정보
        **extra: 추가 필드

    Returns:
        표준화된 에러 응답 딕셔너리
    """
    return ResponseFormatter.error(
        error_code=error_code, message=message, details=details, **extra
    )


def _now_iso() -> str:
    """현재 UTC 시각을 ISO 8601 형식으로 반환"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
