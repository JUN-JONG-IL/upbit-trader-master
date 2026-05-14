# -*- coding: utf-8 -*-
"""
종료 정리 헬퍼
- 스케줄러/AutoBackfill/WebSocket/DataManager 종료
"""
from __future__ import annotations

import asyncio as aio
import concurrent.futures
import os
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional

from .logger import SafeLogger

# 로컬/모듈 수준 상수: 코루틴 대기 기본 타임아웃 (초)
_CLEANUP_CORO_TIMEOUT = float(os.getenv("CLEANUP_CORO_TIMEOUT_SEC", "10"))


def cleanup_on_exit(static: SimpleNamespace, log: SafeLogger):
    """앱 종료 시 리소스 정리 (동기 함수).

    이 함수는 다양한 구성요소의 stop/close 메서드가 동기 또는 비동기일 수 있으므로
    안전하게 호출하도록 방어적으로 구현되어 있습니다.
    """
    def _run_coro_safe(coro, timeout: float = _CLEANUP_CORO_TIMEOUT) -> None:
        """코루틴을 안���하게 실행하고 완료를 기다립니다 (동기 컨텍스트에서 사용)."""
        try:
            # 현재 프로세스의 이벤트 루프 얻기 시도
            loop = None
            try:
                loop = aio.get_event_loop()
            except Exception:
                loop = None

            # 만약 루프가 실행 중이면 run_coroutine_threadsafe로 제출해서 기다립니다.
            if loop is not None and loop.is_running():
                try:
                    fut = aio.run_coroutine_threadsafe(coro, loop)
                except RuntimeError as re:
                    # 예: "cannot schedule new futures after shutdown"
                    log.debug("[cleanup] run_coroutine_threadsafe failed (runtime): %s", re, exc_info=True)
                    # 폴백으로 새 루프에 실행 시도
                    try:
                        aio.run(coro)
                    except Exception:
                        log.debug("[cleanup] aio.run fallback failed for coroutine", exc_info=True)
                    return
                try:
                    fut.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    log.warning("[cleanup] coroutine timed out after %s seconds", timeout)
                except Exception:
                    log.debug("[cleanup] coroutine raised during cleanup", exc_info=True)
            else:
                # 루프가 없거나 실행중이 아니면 새 루프에서 실행
                try:
                    aio.run(coro)
                except Exception:
                    log.debug("[cleanup] aio.run failed for coroutine", exc_info=True)
        except Exception:
            log.debug("[cleanup] unexpected error while running coroutine safely", exc_info=True)

    def _call_maybe_sync_or_async(fn_or_coro: Any, *args, **kwargs) -> None:
        """
        전달된 대상이:
         - 함수(동기)라면 호출(fn(*args, **kwargs))
         - 함수(비동기/coroutinefunction)라면 생성된 coroutine을 안전하게 실행
         - 이미 coroutine object이면 안전하게 실행
        모든 예외는 내부에서 로깅 처리합니다.
        """
        try:
            # 이미 coroutine object 인 경우
            if aio.iscoroutine(fn_or_coro):
                _run_coro_safe(fn_or_coro)
                return

            # 대상이 callable이면 호출해 결과를 검사
            if callable(fn_or_coro):
                try:
                    res = fn_or_coro(*args, **kwargs)
                except TypeError:
                    # 일부 API는 인자를 받지 않으므로 재시도 (호환성)
                    try:
                        res = fn_or_coro()
                    except Exception as e:
                        log.debug("[cleanup] callable invocation failed: %s", e, exc_info=True)
                        return
                except Exception:
                    log.debug("[cleanup] callable invocation raised", exc_info=True)
                    return

                # 호출 결과가 coroutine이면 안전 실행
                if aio.iscoroutine(res):
                    _run_coro_safe(res)
                    return

                # 결과가 awaitable(예: asyncio.Future)일 수도 있으므로 체크
                try:
                    if isinstance(res, aio.Future):
                        # 미래 객체이면 안전하게 기다리기
                        try:
                            # get event loop if running and use run_coroutine_threadsafe on an awaitable wrapper
                            loop = None
                            try:
                                loop = aio.get_event_loop()
                            except Exception:
                                loop = None
                            if loop is not None and loop.is_running():
                                fut = aio.run_coroutine_threadsafe(_awaitable_wrapper(res), loop)
                                try:
                                    fut.result(timeout=_CLEANUP_CORO_TIMEOUT)
                                except Exception:
                                    log.debug("[cleanup] awaiting Future failed", exc_info=True)
                            else:
                                # no running loop; run a small wrapper to await the future
                                aio.run(_awaitable_wrapper(res))
                        except Exception:
                            log.debug("[cleanup] awaiting Future raised", exc_info=True)
                        return
                except Exception:
                    # ignore and continue
                    pass

                # 동기 결과라면 이미 처리된 것이므로 반환
                return

            # 기타 타입은 무시
            return
        except Exception:
            log.debug("[cleanup] unexpected error in _call_maybe_sync_or_async", exc_info=True)

    async def _awaitable_wrapper(awaitable):
        """awaitable을 받아 await만 하는 코루틴 wrapper (run_coroutine_threadsafe에서 사용 가능)."""
        return await awaitable

    # === 실제 cleanup 시작 ===
    try:
        log.info("[cleanup] Running bootstrap cleanup")

        # 스케줄러 종료 (동기)
        sched = getattr(static, "scheduler", None)
        if sched:
            try:
                # APScheduler 등에서는 shutdown(wait=False) 권장
                sched.shutdown(wait=False)
                log.info("[cleanup] scheduler.shutdown called")
            except Exception:
                log.debug("[cleanup] scheduler.shutdown failed", exc_info=True)

        # AutoBackfill 종료 (stop/stop_periodic/shutdown) - 함수가 coroutine일 수 있음
        mgr = getattr(static, "auto_backfill_manager", None)
        if mgr:
            for fn_name in ("stop", "stop_periodic", "shutdown"):
                fn = getattr(mgr, fn_name, None)
                if callable(fn):
                    try:
                        _call_maybe_sync_or_async(fn)
                        log.info("[cleanup] auto_backfill_manager.%s called", fn_name)
                        break
                    except Exception:
                        log.debug("[cleanup] auto_backfill_manager.%s failed", fn_name, exc_info=True)

        # RealtimeManager 종료 (chart)
        chart = getattr(static, "chart", None)
        if chart:
            stop_fn = getattr(chart, "stop", None)
            if callable(stop_fn):
                try:
                    _call_maybe_sync_or_async(stop_fn)
                    log.info("[cleanup] chart.stop called")
                except Exception:
                    log.debug("[cleanup] chart.stop failed", exc_info=True)
            else:
                if hasattr(chart, "alive"):
                    try:
                        chart.alive = False
                        log.info("[cleanup] chart.alive set False")
                    except Exception:
                        log.debug("[cleanup] chart.alive set failed", exc_info=True)

        # DataManager 종료 (close / shutdown)
        dm = getattr(static, "data_manager", None)
        if dm:
            close_fn = getattr(dm, "close", None) or getattr(dm, "shutdown", None)
            if callable(close_fn):
                try:
                    _call_maybe_sync_or_async(close_fn)
                    log.info("[cleanup] data_manager closed")
                except Exception:
                    log.debug("[cleanup] data_manager close failed", exc_info=True)

        # WebSocket 종료 (stop) — stop may be coroutine
        ws_manager = getattr(static, "websocket_manager", None)
        if ws_manager:
            stop_fn = getattr(ws_manager, "stop", None)
            if callable(stop_fn):
                try:
                    _call_maybe_sync_or_async(stop_fn)
                    log.info("[cleanup] websocket_manager.stop called")
                except Exception:
                    log.debug("[cleanup] websocket_manager.stop failed", exc_info=True)

        # Qt QThreadPool 대기 및 WorkerManager 정리
        try:
            try:
                from PyQt5 import QtCore  # type: ignore
                pool = QtCore.QThreadPool.globalInstance()
                if pool is not None:
                    try:
                        timeout_ms = int(os.getenv("QTPOOL_WAIT_MS", "2000"))
                        pool.waitForDone(timeout_ms)
                        log.info("[cleanup] QThreadPool.waitForDone(%dms) returned", timeout_ms)
                    except Exception:
                        log.debug("[cleanup] QThreadPool.waitForDone failed", exc_info=True)
            except Exception:
                pass

            try:
                wm = getattr(static, "worker_manager", None)
                if wm is not None:
                    for stop_name in ("stop_all", "stop", "shutdown", "close"):
                        fn = getattr(wm, stop_name, None)
                        if callable(fn):
                            try:
                                _call_maybe_sync_or_async(fn)
                                log.info("[cleanup] worker_manager.%s called", stop_name)
                                break
                            except Exception:
                                log.debug("[cleanup] worker_manager.%s failed", stop_name, exc_info=True)
            except Exception:
                log.debug("[cleanup] worker_manager cleanup attempts failed", exc_info=True)
        except Exception:
            log.debug("[cleanup] Qt/WorkerManager cleanup block failed", exc_info=True)

    except Exception:
        log.debug("[cleanup] unexpected error during cleanup", exc_info=True)