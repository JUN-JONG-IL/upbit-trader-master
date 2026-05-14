# -*- coding: utf-8 -*-
"""
비동기 글로벌 Rate Limiter (Upbit REST 전용)

설계 메모
---------
- Upbit 공개 REST 한도: 초당 10회, 분당 600회.
- 다중 심볼 × 다중 타임프레임 동시 호출 시 기존 ``asyncio.Semaphore`` + 고정
  ``request_delay`` 만으로는 즉시 한도를 초과하여 ``요청 수 제한을 초과했습니다``
  경고가 발생함. (rest_candle_collector / auto_backfill_manager 양쪽이 한도를
  공유하지 않는 점이 근본 원인)
- 본 모듈은 두 윈도우(초/분)를 동시에 만족시키는 비동기 토큰버킷을 제공하며,
  애플리케이션 전 영역에서 단일 인스턴스를 공유할 수 있도록
  ``get_global_upbit_rate_limiter()`` 싱글톤을 노출함.
- 안전마진: per-second=9 (한도 10 대비 -1), per-minute=550 (한도 600 대비 -50).

이 모듈은 신규 추가 모듈이며 기존 ``rate_limiter.py`` (동기 버전)를 변경하지
않는다. 호출자가 점진적으로 마이그레이션할 수 있도록 한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Deque, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "AsyncRateLimiter",
    "get_global_upbit_rate_limiter",
    "is_rate_limit_error",
    "rate_limit_backoff_delays",
    "UPBIT_REST_PER_SECOND_LIMIT",
    "UPBIT_REST_PER_MINUTE_LIMIT",
]

# Upbit 공식 REST API 한도 — 클램프/검증의 단일 진실 소스
UPBIT_REST_PER_SECOND_LIMIT = 10   # 공식 한도 (초)
UPBIT_REST_PER_MINUTE_LIMIT = 600  # 공식 한도 (분)
UPBIT_REST_PER_SECOND_FLOOR = 1
UPBIT_REST_PER_MINUTE_FLOOR = 10


class AsyncRateLimiter:
    """비동기 다중 윈도우 토큰버킷 Rate Limiter.

    여러 코루틴이 동시에 ``acquire()`` 를 호출해도 안전하게 직렬화한다.
    초/분 윈도우 두 개를 동시에 만족시킬 때까지 sleep 한다.

    Args:
        per_second: 1초 윈도우 내 최대 호출 수
        per_minute: 60초 윈도우 내 최대 호출 수
    """

    def __init__(self, per_second: int = 9, per_minute: int = 550) -> None:
        if per_second <= 0 or per_minute <= 0:
            raise ValueError("per_second/per_minute must be positive")
        self._per_second = int(per_second)
        self._per_minute = int(per_minute)
        self._sec_calls: Deque[float] = deque()
        self._min_calls: Deque[float] = deque()
        self._lock = asyncio.Lock()

    @property
    def per_second(self) -> int:
        return self._per_second

    @property
    def per_minute(self) -> int:
        return self._per_minute

    async def acquire(self) -> None:
        """호출 허가를 획득할 때까지 대기.

        초/분 윈도우 둘 다 여유가 있을 때만 즉시 통과시키고, 그렇지 않으면
        가장 가까운 만료 시점까지 sleep 한다. 락을 잡은 채 sleep 하므로 호출
        순서가 자연스럽게 직렬화된다.
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                self._evict(now)

                wait_sec = 0.0
                if len(self._sec_calls) >= self._per_second:
                    wait_sec = max(wait_sec, self._sec_calls[0] + 1.0 - now)
                if len(self._min_calls) >= self._per_minute:
                    wait_sec = max(wait_sec, self._min_calls[0] + 60.0 - now)

                if wait_sec <= 0.0:
                    self._sec_calls.append(now)
                    self._min_calls.append(now)
                    return

                # 약간의 jitter 를 더해 thundering herd 회피
                await asyncio.sleep(wait_sec + 0.005)

    def _evict(self, now: float) -> None:
        sec_cut = now - 1.0
        min_cut = now - 60.0
        while self._sec_calls and self._sec_calls[0] <= sec_cut:
            self._sec_calls.popleft()
        while self._min_calls and self._min_calls[0] <= min_cut:
            self._min_calls.popleft()

    def snapshot(self) -> dict:
        """디버그용 현재 사용량 스냅샷."""
        now = time.monotonic()
        self._evict(now)
        return {
            "per_second_used": len(self._sec_calls),
            "per_second_limit": self._per_second,
            "per_minute_used": len(self._min_calls),
            "per_minute_limit": self._per_minute,
        }


# ---------------------------------------------------------------------------
# 글로벌 싱글톤 — REST 수집기 / 백필러가 공유
# ---------------------------------------------------------------------------

_global_limiter: Optional[AsyncRateLimiter] = None


def _load_ssot_rate_limits() -> tuple:
    """performance_settings.py SSOT 에서 (per_sec, per_min) 을 읽는다.

    성능 설정 모듈은 ``14_orchestrator`` 패키지(숫자 시작)에 있어 표준
    import 가 불가능하므로 파일 기반 동적 로드로 접근한다. 실패 시 None 반환.
    """
    try:
        import importlib.util
        import pathlib
        import sys
        _key = "_perf_settings_for_arl"
        if _key in sys.modules:
            mod = sys.modules[_key]
        else:
            here = pathlib.Path(__file__).resolve()
            # src/02_data/collectors/async_rate_limiter.py → src/
            src_root = here.parents[2]
            ps_path = src_root / "14_orchestrator" / "backfill" / "performance_settings.py"
            if not ps_path.exists():
                return None, None
            spec = importlib.util.spec_from_file_location(_key, str(ps_path))
            if spec is None or spec.loader is None:
                return None, None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[_key] = mod
            spec.loader.exec_module(mod)
        per_sec_fn = getattr(mod, "get_rest_rate_per_second", None)
        per_min_fn = getattr(mod, "get_rest_rate_per_minute", None)
        per_sec = int(per_sec_fn()) if callable(per_sec_fn) else None
        per_min = int(per_min_fn()) if callable(per_min_fn) else None
        return per_sec, per_min
    except Exception as exc:
        logger.debug("[AsyncRateLimiter] SSOT 로드 실패: %s", exc)
        return None, None


def get_global_upbit_rate_limiter() -> AsyncRateLimiter:
    """전역 Upbit REST Rate Limiter 인스턴스를 반환한다.

    한도 결정 우선순위:
        1) MongoDB ui_settings.backfill_scheduler.performance.rest_rate_per_*
           (performance_settings.py SSOT)
        2) 환경변수 UPBIT_REST_RATE_PER_SECOND / UPBIT_REST_RATE_PER_MINUTE
        3) 정적 기본값 (9 / 550)
    """
    global _global_limiter
    if _global_limiter is None:
        # 1) SSOT 우선
        per_sec, per_min = _load_ssot_rate_limits()
        # 2) env 폴백
        if per_sec is None:
            try:
                per_sec = int(os.getenv("UPBIT_REST_RATE_PER_SECOND", "9"))
            except (TypeError, ValueError):
                per_sec = 9
        if per_min is None:
            try:
                per_min = int(os.getenv("UPBIT_REST_RATE_PER_MINUTE", "550"))
            except (TypeError, ValueError):
                per_min = 550
        # 3) 안전 범위 클램프 (Upbit 공식 한도 초과 방지)
        per_sec = max(UPBIT_REST_PER_SECOND_FLOOR, min(int(per_sec), UPBIT_REST_PER_SECOND_LIMIT))
        per_min = max(UPBIT_REST_PER_MINUTE_FLOOR, min(int(per_min), UPBIT_REST_PER_MINUTE_LIMIT))
        _global_limiter = AsyncRateLimiter(per_second=per_sec, per_minute=per_min)
        logger.info(
            "[AsyncRateLimiter] 글로벌 인스턴스 생성: %d req/s, %d req/min",
            per_sec, per_min,
        )
    return _global_limiter


# ---------------------------------------------------------------------------
# 공통 유틸: 429 / 한도 초과 메시지 감지 & 백오프 시퀀스
# ---------------------------------------------------------------------------

# Upbit 한국어/영문 한도 메시지를 모두 커버.
_RATE_LIMIT_TOKENS = (
    "요청 수 제한",
    "too many requests",
    "rate limit",
    "429",
)


def is_rate_limit_error(exc: BaseException | str | None) -> bool:
    """주어진 예외/문자열이 레이트리밋 관련인지 판정한다."""
    if exc is None:
        return False
    msg = str(exc).lower()
    return any(tok.lower() in msg for tok in _RATE_LIMIT_TOKENS)


def rate_limit_backoff_delays() -> tuple:
    """지수 백오프 시퀀스 (초). 0.5 → 1 → 2 → 4 (최대 4회 대기)."""
    return (0.5, 1.0, 2.0, 4.0)
