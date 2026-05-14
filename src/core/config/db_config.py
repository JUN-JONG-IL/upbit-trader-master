"""
src/core/config/db_config.py
데이터베이스 연결 설정 (환경 변수 + config.yaml 기반)

지원 DB:
    - TimescaleDB  (asyncpg)
    - Redis        (redis.asyncio / aioredis)
    - MongoDB      (motor)

설정 우선순위:
    1. 환경 변수 (TIMESCALE_PORT → POSTGRES_PORT → PGPORT 등)
    2. config.yaml (TIMESCALE.PORT, REDIS.PORT 등)
    3. constants.py 기본값 (매직 넘버 금지)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .constants import (
    DEFAULT_TIMESCALE_HOST,
    DEFAULT_TIMESCALE_PORT,
    DEFAULT_TIMESCALE_USER,
    DEFAULT_TIMESCALE_DB,
    DEFAULT_REDIS_HOST,
    DEFAULT_REDIS_PORT,
    DEFAULT_MONGO_HOST,
    DEFAULT_MONGO_PORT,
)

_logger = logging.getLogger(__name__)

_CONFIG_SEARCH_PATHS = (
    # Same directory as this file (src/core/config/config.yaml)
    lambda: Path(__file__).parent / "config.yaml",
    # Project root (for running from repo root)
    lambda: Path(__file__).parents[3] / "config.yaml",
)


def _load_yaml_config() -> Dict[str, Any]:
    """config.yaml에서 DB 설정을 로드합니다 (첫 번째로 발견된 파일 사용)."""
    for path_fn in _CONFIG_SEARCH_PATHS:
        path = path_fn()
        if path.exists():
            try:
                import yaml  # type: ignore
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _logger.debug("Loaded DB config from %s", path)
                return data
            except Exception as exc:
                _logger.warning("Failed to load config from %s: %s", path, exc)
    _logger.debug("No config.yaml found; using environment variables and defaults")
    return {}


def _cfg_timescale_port() -> int:
    """TimescaleDB 포트 결정 (TIMESCALE_PORT → POSTGRES_PORT → PGPORT → config.yaml → 기본값).

    환경변수 우선순위:
        TIMESCALE_PORT > POSTGRES_PORT > PGPORT > config.yaml > DEFAULT_TIMESCALE_PORT

    Returns:
        TimescaleDB 연결 포트 번호.
    """
    env_val = (
        os.getenv("TIMESCALE_PORT")
        or os.getenv("POSTGRES_PORT")
        or os.getenv("PGPORT")
    )
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            _logger.warning("TimescaleDB 포트 환경변수 파싱 실패('%s') — config.yaml 조회", env_val)
    data = _load_yaml_config()
    yaml_port = data.get("TIMESCALE", {}).get("PORT")
    if yaml_port:
        try:
            return int(yaml_port)
        except (ValueError, TypeError):
            _logger.warning("config.yaml TIMESCALE.PORT 파싱 실패('%s') — 기본값 사용", yaml_port)
    return DEFAULT_TIMESCALE_PORT


def _cfg_redis_port() -> int:
    """Redis 포트 결정 (REDIS_PORT → config.yaml → 기본값).

    Returns:
        Redis 연결 포트 번호.
    """
    env_val = os.getenv("REDIS_PORT")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            _logger.warning("Redis 포트 환경변수 파싱 실패('%s') — config.yaml 조회", env_val)
    data = _load_yaml_config()
    yaml_port = data.get("REDIS", {}).get("PORT")
    if yaml_port:
        try:
            return int(yaml_port)
        except (ValueError, TypeError):
            _logger.warning("config.yaml REDIS.PORT 파싱 실패('%s') — 기본값 사용", yaml_port)
    return DEFAULT_REDIS_PORT


def _cfg_timescale_host() -> str:
    """TimescaleDB 호스트 결정 (TIMESCALE_HOST → POSTGRES_HOST → PGHOST → config.yaml → 기본값).

    Returns:
        TimescaleDB 연결 호스트.
    """
    env_val = (
        os.getenv("TIMESCALE_HOST")
        or os.getenv("POSTGRES_HOST")
        or os.getenv("PGHOST")
    )
    if env_val:
        return env_val
    data = _load_yaml_config()
    return data.get("TIMESCALE", {}).get("HOST", DEFAULT_TIMESCALE_HOST)


def _cfg_redis_host() -> str:
    """Redis 호스트 결정 (REDIS_HOST → config.yaml → 기본값).

    Returns:
        Redis 연결 호스트.
    """
    env_val = os.getenv("REDIS_HOST")
    if env_val:
        return env_val
    data = _load_yaml_config()
    return data.get("REDIS", {}).get("HOST", DEFAULT_REDIS_HOST)


def _cfg_redis_password() -> str:
    """Redis 비밀번호 결정 (REDIS_PASSWORD → config.yaml → 빈 문자열).

    Returns:
        Redis 인증 비밀번호.
    """
    env_val = os.getenv("REDIS_PASSWORD")
    if env_val:
        return env_val
    data = _load_yaml_config()
    return data.get("REDIS", {}).get("PASSWORD", "") or ""


# ---------------------------------------------------------------------------
# TimescaleDB
# ---------------------------------------------------------------------------
@dataclass
class TimescaleConfig:
    host:       str = field(default_factory=_cfg_timescale_host)
    port:       int = field(default_factory=_cfg_timescale_port)
    database:   str = field(default_factory=lambda: (
        os.getenv("TIMESCALE_DB")
        or os.getenv("POSTGRES_DB")
        or os.getenv("PGDATABASE")
        or DEFAULT_TIMESCALE_DB
    ))
    user:       str = field(default_factory=lambda: (
        os.getenv("TIMESCALE_USER")
        or os.getenv("POSTGRES_USER")
        or os.getenv("PGUSER")
        or DEFAULT_TIMESCALE_USER
    ))
    password:   str = field(default_factory=lambda: (
        os.getenv("TIMESCALE_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or os.getenv("PGPASSWORD")
        or ""
    ))
    min_size:   int = 10
    max_size:   int = 100

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
@dataclass
class RedisConfig:
    host:            str   = field(default_factory=_cfg_redis_host)
    port:            int   = field(default_factory=_cfg_redis_port)
    password:        str   = field(default_factory=_cfg_redis_password)
    db:              int   = 0
    max_connections: int   = 50
    candle_ttl:      int   = 604_800   # 7일
    candle_limit:    int   = 10_000


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
@dataclass
class MongoConfig:
    host:     str = field(default_factory=lambda: os.getenv("MONGO_HOST", DEFAULT_MONGO_HOST))
    port:     int = field(default_factory=lambda: int(os.getenv("MONGO_PORT", str(DEFAULT_MONGO_PORT))))
    database: str = field(default_factory=lambda: os.getenv("MONGO_DB",   "upbit_trader"))
    username: str = field(default_factory=lambda: os.getenv("MONGO_INITDB_ROOT_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("MONGO_INITDB_ROOT_PASSWORD", ""))

    @property
    def uri(self) -> str:
        custom = os.getenv("MONGO_URI")
        if custom:
            return custom
        if self.username and self.password:
            return (
                f"mongodb://{self.username}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
            )
        return f"mongodb://{self.host}:{self.port}/{self.database}"


# ---------------------------------------------------------------------------
# 편의 싱글턴
# ---------------------------------------------------------------------------
timescale_config = TimescaleConfig()
redis_config     = RedisConfig()
mongo_config     = MongoConfig()
