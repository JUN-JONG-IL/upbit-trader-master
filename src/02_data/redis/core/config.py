#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redis 설정 (환경변수 기반)"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RedisConfig:
    """Redis 연결 설정"""
    host: str = None
    port: int = None
    password: Optional[str] = None
    db: int = 0
    decode_responses: bool = False
    socket_timeout: int = 5
    max_connections: int = 20

    def __post_init__(self):
        self.host = self.host or os.getenv("REDIS_HOST", "localhost")
        self.port = self.port or int(os.getenv("REDIS_PORT", 58530))
        self.password = self.password if self.password is not None else os.getenv("REDIS_PASSWORD", None)

    @classmethod
    def from_env(cls) -> "RedisConfig":
        return cls()


_default_config: RedisConfig = None


def get_config() -> RedisConfig:
    global _default_config
    if _default_config is None:
        _default_config = RedisConfig.from_env()
    return _default_config