# -*- coding: utf-8 -*-
"""
에러 로그 빈도 제한 유틸리티

동일한 에러 키를 5분에 1회만 터미널에 출력하고,
억제된 건수를 다음 출력 시 함께 표시합니다.

사용법:
    from src.01_core.utils.error_throttler import log_error_throttled

    log_error_throttled(
        logger,
        error_type="event_loop_closed",
        message=f"get_snapshot 실패 ({symbol}/{interval}): Event loop is closed",
        symbol=symbol,
    )
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


class ErrorThrottler:
    """에러 로그 빈도 제한기 (Thread-safe).

    동일 에러 키에 대해 window_minutes 이내에는 억제하며,
    억제된 건수를 다음 출력 시 포함합니다.
    """

    def __init__(self, window_minutes: int = 5) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._last_logged: Dict[str, datetime] = {}
        self._suppressed_count: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def should_log(self, error_key: str) -> Tuple[bool, int]:
        """
        에러를 로깅해야 하는지 판단합니다.

        Returns:
            (should_log, suppressed_count)
            should_log: True이면 로깅 허용, False이면 억제
            suppressed_count: 이전에 억제된 건수 (should_log=True일 때만 의미 있음)
        """
        with self._lock:
            now = datetime.now()
            last_time = self._last_logged.get(error_key)

            if last_time is None or (now - last_time) > self._window:
                # 로깅 허용: 억제 카운터 초기화 후 타임스탬프 갱신
                count = self._suppressed_count.get(error_key, 0)
                self._last_logged[error_key] = now
                self._suppressed_count[error_key] = 0
                return True, count
            else:
                # 억제: 카운터 증가
                self._suppressed_count[error_key] += 1
                return False, 0

    @staticmethod
    def make_key(error_type: str, symbol: Optional[str] = None, **kwargs: object) -> str:
        """에러 고유 키를 생성합니다.

        Args:
            error_type: 에러 종류 식별자 (예: "event_loop_closed")
            symbol: 심볼 (선택)
            **kwargs: 추가 구분 인자
        """
        parts = [error_type]
        if symbol:
            parts.append(symbol)
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}={v}")
        return ":".join(parts)


# 전역 싱글톤 인스턴스 (앱 전체에서 공유)
_global_throttler = ErrorThrottler(window_minutes=5)


def log_error_throttled(
    logger: object,
    error_type: str,
    message: str,
    symbol: Optional[str] = None,
    exc_info: bool = False,
    **kwargs: object,
) -> None:
    """
    빈도 제한이 적용된 에러 로그를 출력합니다.

    동일한 error_type(+symbol+kwargs 조합)은 5분에 1회만 출력되며,
    억제된 건수가 있으면 다음 출력 시 "(이전 N건 억제됨)" 메시지를 함께 기록합니다.

    Args:
        logger: logging.Logger 인스턴스
        error_type: 에러 타입 식별자 (예: "get_snapshot_failed")
        message: 로그 메시지
        symbol: 심볼 코드 (선택, 에러 키 구분에 사용)
        exc_info: 스택 트레이스 포함 여부
        **kwargs: 추가 에러 키 구분자
    """
    key = _global_throttler.make_key(error_type, symbol, **kwargs)
    should_log, suppressed = _global_throttler.should_log(key)

    if not should_log:
        return

    log_fn = getattr(logger, "error", None)
    if log_fn is None:
        return

    if suppressed > 0:
        full_message = f"{message} (이전 {suppressed}건 억제됨)"
    else:
        full_message = message

    log_fn(full_message, exc_info=exc_info)
