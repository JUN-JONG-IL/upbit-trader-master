# -*- coding: utf-8 -*-
"""
Redis 헬스체크(프로덕션용 기본 구현)

- 환경변수:
  - REDIS_HOST (기본: 127.0.0.1)
  - REDIS_PORT (기본: 6379)
  - REDIS_DB   (기본: 0)
  - REDIS_PASSWORD (선택)

- 반환:
  - check_redis_connection() -> 'green' | 'red' | 'gray'
  - health_check() -> dict: {status, reason, host, port, impl}
"""
from __future__ import annotations

import os
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

try:
    import redis  # redis-py
except Exception:
    redis = None

STATUS_GREEN = "green"
STATUS_RED = "red"
STATUS_GRAY = "gray"

# 기본 설정(환경변수)
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", os.environ.get("REDIS_PORT_6379_TCP_PORT", 6379)))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

_impl_name = "data_01.redis.health_check:redis-py"

def _ping_redis_once(timeout: float = 1.0) -> bool:
    """
    한 번 연결 시도 후 PING 확인. timeout은 socket_connect_timeout 및 socket_timeout에 적용.
    """
    if redis is None:
        logger.debug("redis-py 패키지 없음")
        return False
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            decode_responses=True,
        )
        # PING은 연결과 응답 여부 확인에 충분
        return client.ping()
    except Exception as e:
        logger.debug("redis ping 예외: %s", e, exc_info=False)
        return False

def check_redis_connection() -> str:
    """
    간단한 상태 체크 함수: green/red/gray 반환.
    - redis-py 미설치 시 gray 반환(설정 누락)
    - ping 성공 시 green, 실패 시 red
    """
    global _impl_name
    # redis 라이브러리가 없으면 gray로 표시(설�� 또는 패키지 누락)
    if redis is None:
        return STATUS_GRAY

    # 빠른 테스트: 2회의 시도(짧은 재시도)
    for attempt in range(2):
        ok = _ping_redis_once(timeout=1.0)
        if ok:
            return STATUS_GREEN
        # 짧은 대기 후 재시도
        time.sleep(0.15)
    return STATUS_RED

def health_check() -> Dict[str, Optional[str]]:
    """
    상세 헬스 체크 정보를 반환.
    """
    try:
        status = check_redis_connection()
        reason = None
        if status == STATUS_GRAY:
            reason = "redis-py 패키지 미설치 또는 REDIS_HOST 환경변수 누락"
        elif status == STATUS_RED:
            reason = f"연결 실패: {REDIS_HOST}:{REDIS_PORT}"
        else:
            reason = "OK"

        return {
            "status": status,
            "reason": reason,
            "host": REDIS_HOST,
            "port": str(REDIS_PORT),
            "impl": _impl_name,
        }
    except Exception as e:
        logger.exception("health_check 중 예외 발생")
        return {
            "status": STATUS_RED,
            "reason": f"exception: {e}",
            "host": REDIS_HOST,
            "port": str(REDIS_PORT),
            "impl": _impl_name,
        }
