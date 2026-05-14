# -*- coding: utf-8 -*-
"""
Rate Limiter - Token Bucket 알고리즘 기반 API 호출 속도 제한기

Upbit REST API 제한:
  - 초당 최대 10회 (REST)
  - 분당 최대 600회

사용 예:
    limiter = RateLimiter(max_calls=10, period=1.0)
    limiter.acquire()  # 필요 시 sleep 후 통과
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque


class RateLimiter:
    """Token Bucket 알고리즘 기반 Rate Limiter (Thread-safe).

    Args:
        max_calls: period 내 최대 호출 수
        period:    시간 윈도우 (초)
    """

    def __init__(self, max_calls: int = 10, period: float = 1.0) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period <= 0:
            raise ValueError("period must be positive")
        self.max_calls = max_calls
        self.period = period
        self._calls: Deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """호출 허가 대기 (필요 시 sleep).

        현재 윈도우(period) 내 호출이 max_calls에 도달한 경우,
        가장 오래된 호출이 윈도우 밖으로 나갈 때까지 대기합니다.
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.period

            # 윈도우 밖의 오래된 호출 기록 제거
            while self._calls and self._calls[0] <= cutoff:
                self._calls.popleft()

            # 제한 초과 시 대기
            if len(self._calls) >= self.max_calls:
                # 가장 오래된 호출이 윈도우 밖으로 나갈 때까지 대기
                oldest = self._calls[0]
                sleep_time = oldest + self.period - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # 대기 후 재정리
                now = time.time()
                cutoff = now - self.period
                while self._calls and self._calls[0] <= cutoff:
                    self._calls.popleft()

            # 현재 호출 기록
            self._calls.append(now)

    @property
    def current_count(self) -> int:
        """현재 윈도우 내 호출 수."""
        with self._lock:
            now = time.time()
            cutoff = now - self.period
            while self._calls and self._calls[0] <= cutoff:
                self._calls.popleft()
            return len(self._calls)
