# -*- coding: utf-8 -*-
"""
로깅 설정 유틸리티 (Logging Configuration Utilities)

목적:
    - 잡음성 서드파티 로거 레벨을 WARNING 이상으로 억제
    - 동일한 에러 메시지를 5분에 1회만 출력하는 RateLimitedErrorFilter 제공
    - 앱 전체에서 일관된 로깅 환경 구성

사용법:
    from src.core.config.logging_config import suppress_noisy_loggers, RateLimitedErrorFilter
    suppress_noisy_loggers()  # 초기화 시 1회 호출
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Tuple

# 억제 대상 로거 목록 (WARNING 이상으로 설정)
_NOISY_LOGGERS: Tuple[str, ...] = (
    "urllib3",
    "urllib3.connectionpool",
    "requests.packages.urllib3",
    "apscheduler",
    "apscheduler.scheduler",
    "apscheduler.executors.default",
    "apscheduler.jobstores.default",
    "asyncio",
    "connectionpool",
    "websockets",
    "aiopyupbit",
)

# uvicorn 로거 (DEBUG 모드가 아닌 경우에만 억제)
_UVICORN_LOGGERS: Tuple[str, ...] = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
)


def suppress_noisy_loggers(debug_mode: bool = False) -> None:
    """
    잡음성 서드파티 로거를 WARNING(또는 ERROR) 레벨로 억제합니다.

    Args:
        debug_mode: True이면 uvicorn 로거는 억제하지 않음
    """
    # 서드파티 잡음 로거 → WARNING
    for name in _NOISY_LOGGERS:
        try:
            logging.getLogger(name).setLevel(logging.WARNING)
        except Exception:
            pass

    # apscheduler 계열 → ERROR (매우 잡음이 심함)
    for name in ("apscheduler", "apscheduler.scheduler", "apscheduler.executors.default", "apscheduler.jobstores.default"):
        try:
            logging.getLogger(name).setLevel(logging.ERROR)
        except Exception:
            pass

    # uvicorn → DEBUG 모드가 아닌 경우에만 WARNING
    if not debug_mode:
        for name in _UVICORN_LOGGERS:
            try:
                logging.getLogger(name).setLevel(logging.WARNING)
            except Exception:
                pass


class RateLimitedErrorFilter(logging.Filter):
    """
    동일한 에러 메시지(첫 100자 기준)를 5분(300초)에 1회만 통과시키는 필터.

    사용법:
        logger = logging.getLogger(__name__)
        logger.addFilter(RateLimitedErrorFilter(interval_seconds=300))

    동작:
        - ERROR / CRITICAL 레벨 레코드만 속도 제한
        - 그 외 레벨(DEBUG, INFO, WARNING)은 그대로 통과
    """

    def __init__(self, interval_seconds: float = 300.0, key_length: int = 100):
        """
        Args:
            interval_seconds: 같은 에러 메시지 재출력 허용 간격 (초), 기본 300초(5분)
            key_length: 에러 메시지 비교 시 사용할 앞 글자 수
        """
        super().__init__()
        self._interval = float(interval_seconds)
        self._key_length = int(key_length)
        # key -> 마지막 출력 시각
        self._last_seen: Dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        # ERROR / CRITICAL 이하 레벨은 그대로 통과
        if record.levelno < logging.ERROR:
            return True

        # 에러 메시지 키 생성 (로거명 + 메시지 앞부분)
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        key = f"{record.name}:{msg[:self._key_length]}"

        now = time.monotonic()
        last = self._last_seen.get(key)
        if last is None or (now - last) >= self._interval:
            self._last_seen[key] = now
            return True

        # 같은 에러가 interval 이내에 반복 → 억제
        return False
