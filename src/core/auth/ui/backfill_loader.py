# -*- coding: utf-8 -*-
"""
backfill_loader.py

AutoBackfillManager 로딩/등록/실행 헬퍼.
- widget 쪽에서 단순히 trigger_auto_backfill() 를 호출하면 됨.
- 함수는 (manager, started_flag, reason_info) 를 반환합니다.

변경 요지:
- asyncio.Lock 이 다른 이벤트 루프에 바인딩된 경우 안전하게 처리:
  - 다른 루프에 바인딩된 Lock은 locked() 호출을 피하고 해당 루프에서 매니저 시작을 스케줄
  - 현재 루프에 바인딩된 idle Lock만 교체 시도
  - 교체 실패 시 보수적으로 스케줄링으로 폴백
- mgr.start / run_once_nonblocking 이 동기/비동기 모두일 때 동작하도록 보강
"""
from __future__ import annotations
import importlib
import importlib.util
import logging
import os
import asyncio
import inspect
import threading
from typing import Optional, Tuple, Any, List, Callable

logger = logging.getLogger(__name__)


def _discover_static_module():
    candidates = ("src.server.app.static", "server.app.static", "src.app.static", "app.static", "static")
    for name in candidates:
        try:
            mod = importlib.import_module(name)
            return mod
        except Exception:
            continue
    return None


def _instantiate_from_orchestrator(static_obj=None, cb=None):
    try:
        try:
            pkg = importlib.import_module("src.orchestrator")
        except Exception:
            try:
                pkg = importlib.import_module("orchestrator")
            except Exception:
                pkg = None
        if pkg and hasattr(pkg, "create_auto_backfill_manager"):
            return pkg.create_auto_backfill_manager(static=static_obj, logger=logger, on_run_complete=cb)
    except Exception:
        logger.debug("[backfill_loader] orchestrator factory failed", exc_info=True)
    return None


def _instantiate_from_file_fallback(cb=None):
    try:
        # try package import path first
        mod = None
        try:
            mod = importlib.import_module("src.orchestrator.auto_backfill")
        except Exception:
            try:
                mod = importlib.import_module("orchestrator.auto_backfill")
            except Exception:
                mod = None
        if mod is None:
            # file fallback near project (best-effort)
            here = os.path.dirname(__file__)
            candidate = os.path.abspath(os.path.join(here, "..", "..", "orchestrator", "auto_backfill.py"))
            if os.path.isfile(candidate):
                spec = importlib.util.spec_from_file_location("auto_backfill_file", candidate)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)  # type: ignore
                    spec.loader.exec_module(mod)  # type: ignore
        if mod is not None:
            AB = getattr(mod, "AutoBackfillManager", None)
            if AB:
                try:
                    return AB(logger=logger, on_run_complete=cb)
                except TypeError:
                    try:
                        return AB(logger=logger)
                    except Exception:
                        try:
                            return AB()
                        except Exception:
                            return None
    except Exception:
        logger.debug("[backfill_loader] file fallback instantiate failed", exc_info=True)
    return None


# ----------------------------
# 헬퍼: manager 내부에서 asyncio.Lock 찾기
# ----------------------------
def _find_locks_in_obj(obj: Any, max_depth: int = 3) -> List[Tuple[Any, str, asyncio.Lock]]:
    """
    객체의 속성(및 속성의 속성)을 재귀적으로 탐색하여 asyncio.Lock 인스턴스를 찾음.
    반환: [(parent_obj, attr_name, lock_obj), ...]
    max_depth로 탐색 깊이 제한.
    """
    found: List[Tuple[Any, str, asyncio.Lock]] = []
    seen = set()

    def _walk(o, depth, parent=None, parent_attr=None):
        if depth < 0 or id(o) in seen:
            return
        seen.add(id(o))
        try:
            # check if this object is a Lock
            if isinstance(o, asyncio.Lock):
                if parent is not None and parent_attr:
                    found.append((parent, parent_attr, o))
                return
            # iterate attributes if it's a simple object
            if hasattr(o, "__dict__"):
                for k, v in vars(o).items():
                    try:
                        _walk(v, depth - 1, parent=o, parent_attr=k)
                    except Exception:
                        continue
            # also check mapping-like items (dict)
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    try:
                        _walk(v, depth - 1, parent=o, parent_attr=str(k))
                    except Exception:
                        continue
        except Exception:
            return

    _walk(obj, max_depth)
    return found


def _replace_lock_on_current_loop(parent_obj: Any, attr_name: str, lock_obj: asyncio.Lock) -> bool:
    """
    parent_obj.attr_name 에 있는 lock_obj 가 다른 루프에 바인딩되어 있고
    lock_obj.locked() == False 및 waiters 없음인 경우,
    현재 루프에 바인딩된 새 asyncio.Lock() 으로 교체함.
    반환: 교체했으면 True, 아니면 False
    보수적 변경: lock_obj._loop 가 존재하고 현재 루프와 다르면 교체 시도하지 않음.
    """
    try:
        # Determine the loop the original lock is bound to (implementation detail)
        orig_loop = getattr(lock_obj, "_loop", None)
        try:
            current_loop = asyncio.get_running_loop()
        except Exception:
            current_loop = None

        # If original lock is bound to a different loop, do NOT replace here.
        if orig_loop is not None and current_loop is not None and orig_loop is not current_loop:
            logger.debug("[backfill_loader] Skipping replacement: original lock bound to another loop")
            return False

        # avoid replacing if lock is locked or has waiters
        locked = False
        try:
            locked = lock_obj.locked()
        except Exception:
            # be conservative: if we cannot query locked state, do not replace
            logger.debug("[backfill_loader] lock.locked() raised — abort replacement", exc_info=True)
            return False

        waiters = getattr(lock_obj, "_waiters", None)
        if waiters:
            try:
                # some implementations expose _waiters as list-like
                if len(waiters) > 0:
                    return False
            except Exception:
                # if unable to determine, be conservative
                return False
        if locked:
            return False

        # create new lock bound to current loop
        new_lock = asyncio.Lock()
        # set on parent object
        try:
            # if parent is dict-like and attr_name string of key
            if isinstance(parent_obj, dict) and attr_name in parent_obj:
                parent_obj[attr_name] = new_lock
            else:
                setattr(parent_obj, attr_name, new_lock)
            logger.debug("[backfill_loader] Replaced lock attribute '%s' on %s with new lock bound to current loop", attr_name, type(parent_obj).__name__)
            return True
        except Exception:
            logger.debug("[backfill_loader] Failed to set new lock on parent object: %s.%s", type(parent_obj).__name__, attr_name, exc_info=True)
            return False
    except Exception:
        return False


def _schedule_callable_on_loop(loop: asyncio.AbstractEventLoop, func: Callable, *args, **kwargs) -> Optional[threading.Thread]:
    """
    주어진 loop에서 func(*args, **kwargs)를 안전하게 스케줄합니다.
    - func가 coroutine function 또는 호출 결과가 awaitable이면 run_coroutine_threadsafe를 사용.
    - func가 동기 함수이면 loop.call_soon_threadsafe로 스케줄합니다.
    반환: 스케줄링 정보 문자열 대체로 None (현재 동기 API 유지)
    """
    try:
        # If func is coroutine function, create coroutine
        if inspect.iscoroutinefunction(func):
            coro = func(*args, **kwargs)
            try:
                asyncio.run_coroutine_threadsafe(coro, loop)
                return None
            except Exception as e:
                logger.debug("[backfill_loader] run_coroutine_threadsafe failed: %s", e, exc_info=True)
                return None
        else:
            # call func; if it returns awaitable, schedule that
            try:
                res = func(*args, **kwargs)
            except Exception as e:
                # schedule call itself on loop thread
                try:
                    loop.call_soon_threadsafe(lambda: func(*args, **kwargs))
                except Exception:
                    logger.debug("[backfill_loader] call_soon_threadsafe failed: %s", e, exc_info=True)
                return None

            if inspect.isawaitable(res):
                try:
                    asyncio.run_coroutine_threadsafe(res, loop)
                except Exception as e:
                    logger.debug("[backfill_loader] run_coroutine_threadsafe on returned coroutine failed: %s", e, exc_info=True)
                return None
            else:
                # synchronous return, nothing to wait for
                return None
    except Exception:
        logger.debug("[backfill_loader] _schedule_callable_on_loop unexpected error", exc_info=True)
        return None


# ----------------------------
# 핵심 함수: trigger_auto_backfill
# ----------------------------
def trigger_auto_backfill(cb=None) -> Tuple[Optional[Any], bool, str]:
    """
    안전하게 AutoBackfillManager 찾고 실행 시도.
    반환: (manager_or_None, started(bool), reason_message)
    """
    static_mod = _discover_static_module()
    mgr = None
    # reuse existing on static if present
    try:
        if static_mod is not None:
            for attr in ("auto_backfill_manager", "AutoBackfillManager"):
                if hasattr(static_mod, attr):
                    existing = getattr(static_mod, attr)
                    if existing:
                        mgr = existing
                        logger.info("[backfill_loader] Found existing manager on static")
                        break
    except Exception:
        pass

    # factory instantiate
    if mgr is None:
        mgr = _instantiate_from_orchestrator(static_mod, cb)

    # fallback file/class
    if mgr is None:
        mgr = _instantiate_from_file_fallback(cb)

    if mgr is None:
        return None, False, "AutoBackfillManager not found"

    # register to static best-effort
    try:
        if static_mod is not None:
            try:
                setattr(static_mod, "auto_backfill_manager", mgr)
            except Exception:
                logger.debug("[backfill_loader] set on static failed", exc_info=True)
    except Exception:
        pass

    # --- New: Inspect manager for asyncio.Lock instances bound to other loops ---
    try:
        # find locks in manager (shallow depth)
        locks = _find_locks_in_obj(mgr, max_depth=3)
        current_loop = None
        try:
            current_loop = asyncio.get_running_loop()
        except Exception:
            current_loop = None

        # If we found locks bound to other loops, try to replace those that are idle.
        # If any lock is active (locked or has waiters) or bound to another loop, schedule start on that lock's loop instead.
        schedule_on_loop = None
        for parent, attr_name, lock_obj in locks:
            try:
                lock_loop = getattr(lock_obj, "_loop", None)
                # If lock is explicitly bound to another loop, schedule on that loop (do not attempt to call lock.locked())
                if lock_loop is not None:
                    # If it's already our loop, nothing to do
                    if current_loop is not None and lock_loop is current_loop:
                        continue
                    # Bound to another loop -> schedule there
                    schedule_on_loop = lock_loop
                    logger.debug("[backfill_loader] Detected lock bound to other loop; scheduling on that loop.")
                    break

                # If lock_loop is None (unknown), be conservative:
                # attempt to check locked/waiters but if locked() raises, abort replacement and schedule on current thread's loop (if any).
                locked = False
                try:
                    locked = lock_obj.locked()
                except Exception:
                    # cannot safely query; conservatively assume active -> try scheduling on current_loop if available
                    logger.debug("[backfill_loader] Could not query lock.locked(); treating as active (conservative).", exc_info=True)
                    schedule_on_loop = current_loop
                    break

                waiters = getattr(lock_obj, "_waiters", None)
                waiters_count = 0
                try:
                    if waiters:
                        waiters_count = len(waiters)
                except Exception:
                    waiters_count = 1  # conservative

                if not locked and waiters_count == 0 and current_loop is not None:
                    replaced = _replace_lock_on_current_loop(parent, attr_name, lock_obj)
                    if replaced:
                        logger.debug("[backfill_loader] Replaced manager lock for attribute %s", attr_name)
                        continue
                    else:
                        # replacement failed -> conservatively schedule on current loop (or skip)
                        schedule_on_loop = current_loop
                        logger.debug("[backfill_loader] Replacement failed; will schedule on current loop")
                        break
                else:
                    # lock active -> schedule on its loop if available (we don't know, so use current)
                    schedule_on_loop = lock_loop or current_loop
                    logger.debug("[backfill_loader] Active lock detected; will schedule manager start on lock loop.")
                    break
            except Exception:
                continue
    except Exception:
        logger.debug("[backfill_loader] Lock inspection failed", exc_info=True)
        schedule_on_loop = None

    # decide to start if not running
    try:
        already = False
        if hasattr(mgr, "is_running") and callable(getattr(mgr, "is_running")):
            try:
                already = bool(mgr.is_running())
            except Exception:
                already = False
        if already:
            return mgr, False, "ALREADY_RUNNING"

        # If we determined we must schedule on a specific loop, do so
        if schedule_on_loop is not None:
            # try run_once_nonblocking first if available
            if hasattr(mgr, "run_once_nonblocking") and callable(getattr(mgr, "run_once_nonblocking")):
                try:
                    _schedule_callable_on_loop(schedule_on_loop, mgr.run_once_nonblocking)
                    return mgr, True, "run_once_nonblocking_scheduled_on_lock_loop"
                except Exception:
                    logger.exception("[backfill_loader] scheduling run_once_nonblocking on lock loop failed")
                    return mgr, False, "run_once_nonblocking_schedule_failed"
            # otherwise schedule start()
            if hasattr(mgr, "start") and callable(getattr(mgr, "start")):
                try:
                    _schedule_callable_on_loop(schedule_on_loop, mgr.start)
                    return mgr, True, "start_scheduled_on_lock_loop"
                except Exception:
                    logger.exception("[backfill_loader] scheduling start on lock loop failed")
                    return mgr, False, "start_schedule_failed"

        # Normal path: prefer run_once_nonblocking if available
        if hasattr(mgr, "run_once_nonblocking") and callable(getattr(mgr, "run_once_nonblocking")):
            try:
                res = mgr.run_once_nonblocking()
                # if returns awaitable, try to run it appropriately
                if inspect.isawaitable(res):
                    try:
                        # if we are in an event loop, ensure coroutine scheduled
                        try:
                            loop = asyncio.get_running_loop()
                            # schedule on running loop
                            asyncio.ensure_future(res)
                            return mgr, True, "run_once_nonblocking_scheduled_current_loop"
                        except RuntimeError:
                            # no running loop in this thread -> run in new thread to avoid blocking caller
                            def _runner(coro):
                                try:
                                    asyncio.run(coro)
                                except Exception:
                                    logger.exception("[backfill_loader] run_once_nonblocking coroutine raised in thread")
                            t = threading.Thread(target=_runner, args=(res,), daemon=True)
                            t.start()
                            return mgr, True, "run_once_nonblocking_started_in_thread"
                    except Exception:
                        logger.exception("[backfill_loader] run_once_nonblocking awaitable handling failed")
                        return mgr, False, "run_once_nonblocking_awaitable_failed"
                else:
                    # non-awaitable return value; interpret truthiness as started
                    started = bool(res)
                    return mgr, started, "run_once_nonblocking_called"
            except Exception:
                logger.exception("[backfill_loader] run_once_nonblocking failed")
                return mgr, False, "run_once_nonblocking_failed"

        # fallback to start()
        if hasattr(mgr, "start") and callable(getattr(mgr, "start")):
            try:
                res = mgr.start()
                # if start() returns awaitable (async def start), handle similar to above
                if inspect.isawaitable(res):
                    try:
                        try:
                            loop = asyncio.get_running_loop()
                            asyncio.ensure_future(res)
                            return mgr, True, "start_scheduled_current_loop"
                        except RuntimeError:
                            # run in thread
                            def _runner(coro):
                                try:
                                    asyncio.run(coro)
                                except Exception:
                                    logger.exception("[backfill_loader] start coroutine raised in thread")
                            t = threading.Thread(target=_runner, args=(res,), daemon=True)
                            t.start()
                            return mgr, True, "start_started_in_thread"
                    except Exception:
                        logger.exception("[backfill_loader] start awaitable handling failed")
                        return mgr, False, "start_awaitable_failed"
                else:
                    # start() is sync; assume started if no exception
                    return mgr, True, "start_called"
            except Exception:
                logger.exception("[backfill_loader] start() failed")
                return mgr, False, "start_failed"
    except Exception:
        logger.exception("[backfill_loader] unexpected error during start")
        return mgr, False, "start_exception"

    return mgr, False, "no_start_method"