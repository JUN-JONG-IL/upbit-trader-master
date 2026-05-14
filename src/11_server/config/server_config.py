#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
서버 설정 관리

[Responsibilities]
- FastAPI 서버 기본 설정 (host, port, workers)
- 환경변수 및 YAML 파일 기반 설정 로딩
- 설정값 유효성 검사

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """
    서버 설정

    환경변수를 우선 적용하며, 기본값은 개발 환경 기준입니다.

    Attributes:
        host: 바인딩 호스트
        port: 바인딩 포트
        workers: uvicorn 워커 수
        log_level: 로그 레벨
        reload: 자동 리로드 (개발 환경)
        cors_origins: CORS 허용 오리진
        rate_limit: 초당 요청 제한
        enable_auth: JWT 인증 활성화
    """

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    log_level: str = "warning"
    reload: bool = False
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    rate_limit: int = 10
    enable_auth: bool = False
    auth_secret_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """
        환경변수에서 설정 로딩

        Returns:
            ServerConfig 인스턴스
        """
        config = cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8000")),
            workers=int(os.getenv("SERVER_WORKERS", "1")),
            log_level=os.getenv("SERVER_LOG_LEVEL", "warning").lower(),
            reload=os.getenv("SERVER_RELOAD", "false").lower() == "true",
            rate_limit=int(os.getenv("RATE_LIMIT", "10")),
            enable_auth=os.getenv("ENABLE_AUTH", "false").lower() == "true",
            auth_secret_key=os.getenv("JWT_SECRET_KEY"),
        )

        cors_env = os.getenv("CORS_ORIGINS", "")
        if cors_env:
            config.cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()]

        logger.debug(
            "[ServerConfig] 로드됨 host=%s port=%d workers=%d",
            config.host, config.port, config.workers,
        )
        return config

    def to_uvicorn_kwargs(self) -> dict:
        """
        uvicorn 실행에 필요한 키워드 인자 반환

        Returns:
            uvicorn.run() 또는 uvicorn.Config()에 전달할 딕셔너리
        """
        return {
            "host": self.host,
            "port": self.port,
            "workers": self.workers,
            "log_level": self.log_level,
            "reload": self.reload,
        }

    def validate(self) -> bool:
        """
        설정 유효성 검사

        Returns:
            유효 여부
        """
        if not (0 < self.port < 65536):
            logger.error("[ServerConfig] 유효하지 않은 포트: %d", self.port)
            return False
        if self.workers < 1:
            logger.error("[ServerConfig] workers는 1 이상이어야 합니다: %d", self.workers)
            return False
        if self.rate_limit < 1:
            logger.error("[ServerConfig] rate_limit는 1 이상이어야 합니다: %d", self.rate_limit)
            return False
        return True


# 기본 설정 인스턴스
default_config = ServerConfig.from_env()
