# -*- coding: utf-8 -*-
"""
Redis 연결 중앙 관리 팩토리
config.yaml의 REDIS 섹션을 읽어 전역 Redis 클라이언트 제공

[Purpose]
- config.yaml의 REDIS 섹션 기반 싱글톤 Redis 클라이언트 제공
- 환경변수(REDIS_URL, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)로 오버라이드 가능

[Usage]
    from _01_core.database.redis_factory import get_redis_client, get_redis_url

    client = get_redis_client()
    url    = get_redis_url()
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_redis_client: Optional[object] = None


def _load_redis_config() -> dict:
    """
    config.yaml의 REDIS 섹션을 로드합니다.
    로드 실패 시 기본값(port=58530, password=dummy)을 반환합니다.
    """
    try:
        import yaml  # type: ignore
        from pathlib import Path

        # redis_factory.py is at src/01_core/database/redis_factory.py
        # config.yaml is at src/01_core/config/config.yaml
        config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
        if not config_path.exists():
            # Fallback: look for config.yaml from src/
            _src = Path(__file__).resolve().parent.parent.parent
            for candidate in [
                _src / "01_core" / "config" / "config.yaml",
                _src.parent / "config.yaml",
            ]:
                if candidate.exists():
                    config_path = candidate
                    break

        if not config_path.exists():
            logger.debug("[RedisFactory] config.yaml not found, using defaults")
            return {}

        with open(config_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get('REDIS', {})
    except Exception as exc:
        logger.debug("[RedisFactory] config.yaml 로드 실패 (%s), 기본값 사용", exc)
        return {}


def get_redis_url() -> str:
    """
    Redis 연결 URL 생성 (redis://[:password@]host:port/db)

    우선순위:
    1. REDIS_URL 환경변수
    2. config.yaml REDIS 섹션
    3. 기본값 (127.0.0.1:58530, password=dummy)

    Returns:
        str: Redis 연결 URL
    """
    # 1) 환경변수로 완전한 URL이 있으면 그대로 사용
    env_url = os.getenv("REDIS_URL")
    if env_url:
        return env_url

    # 2) config.yaml 또는 환경변수 개별 항목
    redis_cfg = _load_redis_config()

    host = os.getenv("REDIS_HOST") or redis_cfg.get('HOST', '127.0.0.1')
    port = int(os.getenv("REDIS_PORT") or redis_cfg.get('PORT', 58530))
    db = int(os.getenv("REDIS_DB") or redis_cfg.get('DB', 0))
    password = os.getenv("REDIS_PASSWORD") or redis_cfg.get('PASSWORD') or ''
    if not password:
        logger.warning("[RedisFactory] Redis 패스워드가 설정되지 않았습니다. config.yaml의 REDIS.PASSWORD를 확인하세요.")

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def get_redis_client():
    """
    전역 Redis 클라이언트 싱글톤 반환.
    config.yaml의 REDIS 섹션 참조 (환경변수로 오버라이드 가능).

    Returns:
        redis.Redis: 설정된 Redis 클라이언트

    Raises:
        RuntimeError: redis 패키지가 설치되지 않은 경우
        redis.ConnectionError: Redis 연결 실패 시
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        import redis  # type: ignore
    except ImportError as exc:
        raise RuntimeError("redis 패키지가 필요합니다: pip install redis") from exc

    redis_cfg = _load_redis_config()

    host = os.getenv("REDIS_HOST") or redis_cfg.get('HOST', '127.0.0.1')
    port = int(os.getenv("REDIS_PORT") or redis_cfg.get('PORT', 58530))
    db = int(os.getenv("REDIS_DB") or redis_cfg.get('DB', 0))
    password = os.getenv("REDIS_PASSWORD") or redis_cfg.get('PASSWORD') or None
    if not password:
        logger.warning("[RedisFactory] Redis 패스워드가 설정되지 않았습니다. config.yaml의 REDIS.PASSWORD를 확인하세요.")
    decode_responses = redis_cfg.get('DECODE_RESPONSES', True)
    socket_timeout = int(redis_cfg.get('SOCKET_TIMEOUT', 5))
    socket_connect_timeout = int(redis_cfg.get('SOCKET_CONNECT_TIMEOUT', 5))
    retry_on_timeout = bool(redis_cfg.get('RETRY_ON_TIMEOUT', True))
    health_check_interval = int(redis_cfg.get('HEALTH_CHECK_INTERVAL', 30))

    logger.info("[RedisFactory] Creating Redis client: %s:%s (db=%s)", host, port, db)

    client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        retry_on_timeout=retry_on_timeout,
        health_check_interval=health_check_interval,
    )

    try:
        client.ping()
        logger.info("[RedisFactory] ✅ Redis connection successful (%s:%s)", host, port)
    except Exception as exc:
        logger.error("[RedisFactory] ❌ Redis connection failed: %s", exc)
        raise

    _redis_client = client
    return _redis_client


def reset_redis_client() -> None:
    """Redis 클라이언트 재생성 (테스트/재연결용)"""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        _redis_client = None
    logger.info("[RedisFactory] Redis client reset")
