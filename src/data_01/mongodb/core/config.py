#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MongoDB 설정 (환경변수 기반)"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MongoConfig:
    """MongoDB 연결 설정"""
    host: str = None
    port: int = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: str = "upbit_trader"
    auth_source: str = "admin"
    max_pool_size: int = 10

    def __post_init__(self):
        self.host = self.host or os.getenv("MONGO_HOST", "localhost")
        self.port = self.port or int(os.getenv("MONGO_PORT", 27017))
        self.username = (
            self.username
            or os.getenv("MONGO_USER")
            or os.getenv("MONGO_ID")
            or os.getenv("MONGO_INITDB_ROOT_USERNAME")
            or os.getenv("MONGO_INITDB_ROOT_USERNAME_CONTAINER")
        )
        self.password = (
            self.password
            or os.getenv("MONGO_PASSWORD")
            or os.getenv("MONGO_INITDB_ROOT_PASSWORD")
            or os.getenv("MONGO_INITDB_ROOT_PASSWORD_CONTAINER")
        )
        self.database = os.getenv("MONGO_DB", self.database)

    @classmethod
    def from_env(cls) -> "MongoConfig":
        return cls()

    def get_uri(self) -> str:
        """MongoDB URI 생성 (비밀번호 특수문자 URL 인코딩 포함)"""
        from urllib.parse import quote_plus
        if self.username and self.password:
            return (
                f"mongodb://{quote_plus(self.username)}:{quote_plus(self.password)}"
                f"@{self.host}:{self.port}/{self.database}"
                f"?authSource={self.auth_source}"
            )
        return f"mongodb://{self.host}:{self.port}/{self.database}"


_default_config: MongoConfig = None


def get_config() -> MongoConfig:
    global _default_config
    if _default_config is None:
        _default_config = MongoConfig.from_env()
    return _default_config
