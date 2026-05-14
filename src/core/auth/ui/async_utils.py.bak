# -*- coding: utf-8 -*-
"""
async_utils.py (위치: src/01_core/auth/ui)

PyQt/asyncio 통합을 위한 유틸:
- 메인 이벤트 루프 등록(set_main_loop)
- 백그라운드 스레드에서 코루틴을 안전하게 제출(run_coroutine_threadsafe_or_run)
- 동기/비동기 함수를 통합 호출하는 run_sync_callable
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None

def set_main_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """앱(메인) 이벤트 루프를 등록합니다."""
    global _MAIN_LOOP
    _MAIN_LOOP = loop
    logger.debug("[async_utils] main loop set: %r", loop)

def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _MAIN_LOOP

def run_coroutine_threadsafe_or_run(coro):
    """
    안전 실행:
    - 메인 루프 등록 및 실행 중이면 run_coroutine_threadsafe로 제출하고 결과 반환(블로킹).
    - 아니면 asyncio.run으로 실행(개발/테스트 폴백).
    """
    loop = get_main_loop()
    try:
        if loop is not None and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result()
        return asyncio.run(coro)
    except Exception:
        logger.exception("[async_utils] coroutine run failed")
        raise

def run_sync_callable(fn: Callable, *args, **kwargs):
    """
    동기함수 또는 coroutine을 안전히 실행:
    - fn(...) 호출 결과가 coroutine이면 run_coroutine_threadsafe_or_run으로 실행
    - 그렇지 않으면 동기값 반환
    """
    try:
        res = fn(*args, **kwargs)
        if asyncio.iscoroutine(res) or asyncio.iscoroutinefunction(fn):
            coro = res if asyncio.iscoroutine(res) else fn(*args, **kwargs)
            return run_coroutine_threadsafe_or_run(coro)
        return res
    except Exception:
        logger.exception("[async_utils] run_sync_callable failed for %s", getattr(fn, "__name__", str(fn)))
        raise