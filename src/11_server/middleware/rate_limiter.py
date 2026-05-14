#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
Rate Limit 미들웨어 (Redis 기반)

[Responsibilities]
- 클라이언트 IP 기반 초당 요청 수 제한
- Redis sliding window 카운터 사용
- Redis 미사용 시 인메모리 카운터로 fallback

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 5.1

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_RATE_LIMIT_KEY_PREFIX = "rate_limit"
_RATE_LIMIT_WINDOW = 1  # 슬라이딩 윈도우 (초)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis 기반 Rate Limit 미들웨어

    슬라이딩 윈도우 방식으로 IP별 초당 요청 수를 제한합니다.

    Attributes:
        rate_limit: 초당 최대 허용 요청 수
        exclude_paths: Rate Limit 제외 경로 목록
    """

    def __init__(
        self,
        app: Any,
        rate_limit: int = 10,
        exclude_paths: Optional[list] = None,
    ) -> None:
        super().__init__(app)
        self.rate_limit = rate_limit
        self.exclude_paths = set(exclude_paths or ["/health", "/docs", "/openapi.json"])
        self._redis: Optional[Any] = None
        # Redis 미사용 시 인메모리 fallback
        self._counters: Dict[str, list] = defaultdict(list)
        self._init_redis()

    def _init_redis(self) -> None:
        """Redis 클라이언트 초기화"""
        try:
            import redis as redis_lib  # type: ignore
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self._redis = redis_lib.Redis(host=host, port=port, decode_responses=True)
            self._redis.ping()
            logger.debug("[RateLimitMiddleware] Redis 연결 성공")
        except Exception:
            self._redis = None
            logger.debug("[RateLimitMiddleware] Redis 없음 - 인메모리 카운터 사용")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청 처리 - Rate Limit 확인"""
        path = request.url.path

        # 제외 경로 체크
        if any(path.startswith(ep) for ep in self.exclude_paths):
            return await call_next(request)

        # 클라이언트 IP 추출
        client_ip = self._get_client_ip(request)
        key = f"{_RATE_LIMIT_KEY_PREFIX}:{client_ip}"

        # Rate Limit 확인
        if not self._check_rate_limit(key):
            logger.debug("[RateLimitMiddleware] Rate limit 초과: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"초당 {self.rate_limit}회 요청 제한을 초과했습니다.",
                    "retry_after": 1,
                },
                headers={"Retry-After": "1"},
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 추출 (프록시 헤더 포함)"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        if request.client:
            return request.client.host
        return "unknown"

    def _check_rate_limit(self, key: str) -> bool:
        """
        Rate Limit 확인 및 카운터 증가

        Args:
            key: Redis 키 (클라이언트 IP 포함)

        Returns:
            True: 허용, False: 제한 초과
        """
        if self._redis:
            return self._check_redis_rate_limit(key)
        return self._check_memory_rate_limit(key)

    def _check_redis_rate_limit(self, key: str) -> bool:
        """Redis 슬라이딩 윈도우 Rate Limit"""
        try:
            pipe = self._redis.pipeline()
            now = time.time()
            window_start = now - _RATE_LIMIT_WINDOW

            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, _RATE_LIMIT_WINDOW + 1)
            results = pipe.execute()

            current_count = results[2]
            return current_count <= self.rate_limit
        except Exception as exc:
            logger.debug("[RateLimitMiddleware] Redis 확인 실패: %s", exc)
            return self._check_memory_rate_limit(key)

    def _check_memory_rate_limit(self, key: str) -> bool:
        """인메모리 슬라이딩 윈도우 Rate Limit (Redis fallback)"""
        now = time.time()
        window_start = now - _RATE_LIMIT_WINDOW
        # 만료된 항목 제거
        self._counters[key] = [t for t in self._counters[key] if t > window_start]
        # 현재 요청 추가
        self._counters[key].append(now)
        return len(self._counters[key]) <= self.rate_limit
