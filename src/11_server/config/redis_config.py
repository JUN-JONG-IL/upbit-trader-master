#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
Redis 연결 설정 관리

[Responsibilities]
- Redis 연결 파라미터 관리 (host, port, password, db)
- 환경변수 기반 설정 로딩
- 연결 URL 생성

[References]
- work_order/DB설계.md 6.2 (L1 캐시 구조)

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """
    Redis 연결 설정

    Attributes:
        host: Redis 호스트
        port: Redis 포트
        password: Redis 비밀번호 (옵션)
        db: Redis DB 인덱스
        decode_responses: 응답 문자열 디코딩 여부
        socket_connect_timeout: 연결 타임아웃 (초)
        socket_timeout: 소켓 타임아웃 (초)
    """

    host: str = "localhost"
    port: int = 58530
    password: Optional[str] = None
    db: int = 0
    decode_responses: bool = True
    socket_connect_timeout: float = 5.0
    socket_timeout: float = 5.0

    @classmethod
    def from_env(cls) -> "RedisConfig":
        """
        환경변수에서 Redis 설정 로딩

        지원하는 환경변수:
        - ``REDIS_URL``: Redis URL (우선 적용)
        - ``REDIS_HOST``, ``REDIS_PORT``, ``REDIS_PASSWORD``, ``REDIS_DB``

        Returns:
            RedisConfig 인스턴스
        """
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            return cls._from_url(redis_url)

        config = cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "58530")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
        )
        logger.debug(
            "[RedisConfig] 로드됨 host=%s port=%d db=%d",
            config.host, config.port, config.db,
        )
        return config

    @classmethod
    def _from_url(cls, url: str) -> "RedisConfig":
        """Redis URL 파싱"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            password = parsed.password or None
            db = int(parsed.path.lstrip("/") or "0") if parsed.path else 0
            return cls(
                host=parsed.hostname or "localhost",
                port=parsed.port or 58530,
                password=password,
                db=db,
            )
        except Exception as exc:
            logger.warning("[RedisConfig] URL 파싱 실패: %s", exc)
            return cls()

    def to_url(self) -> str:
        """
        Redis URL 문자열 생성

        Returns:
            redis://:password@host:port/db 형식
        """
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"

    def to_client_kwargs(self) -> dict:
        """
        redis.Redis() 생성자에 전달할 키워드 인자

        Returns:
            redis.Redis(**kwargs) 에 사용할 딕셔너리
        """
        kwargs: dict = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "decode_responses": self.decode_responses,
            "socket_connect_timeout": self.socket_connect_timeout,
            "socket_timeout": self.socket_timeout,
        }
        if self.password:
            kwargs["password"] = self.password
        return kwargs

    def create_client(self) -> Optional[Any]:
        """
        redis.Redis 클라이언트 생성 및 반환

        Returns:
            redis.Redis 인스턴스 또는 None (연결 실패 시)
        """
        try:
            import redis as redis_lib  # type: ignore
            client = redis_lib.Redis(**self.to_client_kwargs())
            client.ping()
            logger.debug("[RedisConfig] 클라이언트 생성 성공")
            return client
        except ImportError:
            logger.warning("[RedisConfig] redis 패키지 없음")
            return None
        except Exception as exc:
            logger.warning("[RedisConfig] Redis 연결 실패: %s", exc)
            return None


# 기본 설정 인스턴스
default_config = RedisConfig.from_env()