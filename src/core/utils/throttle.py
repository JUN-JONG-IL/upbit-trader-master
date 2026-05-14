#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe throttle utilities.

Provides:
- throttle(wait_ms): decorator to ensure function is called at most once per interval.
- Throttle(wait_ms): class wrapper.
- throttle_qt(wait_ms): Qt/QTimer-backed throttle when available.
- ThrottleQt(wait_ms): class wrapper for Qt throttle.
"""
from __future__ import annotations

import threading
import functools
import logging
import asyncio
from typing import Callable, Any
import inspect
import time

logger = logging.getLogger(__name__)


def _make_key(fn: Callable, args: tuple, kwargs: dict) -> Any:
    if len(args) >= 1:
        maybe_self = args[0]
        try:
            if hasattr(maybe_self, fn.__name__) or hasattr(type(maybe_self), fn.__name__):
                return id(maybe_self)
        except Exception:
            pass
    return None


def _call_target(fn: Callable, args: tuple, kwargs: dict):
    try:
        if inspect.iscoroutinefunction(fn):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(fn(*args, **kwargs), loop)
                else:
                    asyncio.run(fn(*args, **kwargs))
            except RuntimeError:
                asyncio.run(fn(*args, **kwargs))
        else:
            fn(*args, **kwargs)
    except Exception:
        logger.exception("Throttled function raised an exception")


def throttle(wait_ms: int):
    wait = float(wait_ms) / 1000.0

    def decorator(fn: Callable):
        last_called = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = _make_key(fn, args, kwargs)
            now = time.time()
            with lock:
                last = last_called.get(key, 0.0)
                if now - last >= wait:
                    last_called[key] = now
                    # call without blocking the lock
                    try:
                        _call_target(fn, args, kwargs)
                    except Exception:
                        logger.exception("Throttle call failed")
                else:
                    # ignore call (throttled)
                    pass

        def cancel(*c_args, **c_kwargs):
            with lock:
                last_called.clear()

        wrapper.cancel = cancel  # type: ignore
        return wrapper

    return decorator


class Throttle:
    def __init__(self, wait_ms: int):
        self.wait_ms = wait_ms

    def __call__(self, fn: Callable):
        return throttle(self.wait_ms)(fn)


# Qt-backed throttle using QTimer (coalescing)
try:
    from PyQt5.QtCore import QTimer  # type: ignore
    _HAS_QT_TIMER = True
except Exception:
    _HAS_QT_TIMER = False


def throttle_qt(wait_ms: int):
    wait = int(wait_ms)

    if not _HAS_QT_TIMER:
        return throttle(wait_ms)

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            inst = args[0] if len(args) >= 1 else None
            timer_holder = None
            if inst is not None:
                if not hasattr(inst, "_throttle_timers"):
                    setattr(inst, "_throttle_timers", {})
                timer_holder = getattr(inst, "_throttle_timers")
            else:
                if not hasattr(fn, "_throttle_timers"):
                    setattr(fn, "_throttle_timers", {})
                timer_holder = getattr(fn, "_throttle_timers")

            key = "_default"
            existing = timer_holder.get(key)
            if existing and isinstance(existing, QTimer):
                # Already scheduled, ignore new requests (coalesce)
                return

            qtimer = QTimer()
            qtimer.setSingleShot(True)

            def _on_timeout():
                try:
                    fn(*args, **kwargs)
                except Exception:
                    logger.exception("ThrottleQt target raised")
                finally:
                    try:
                        timer_holder.pop(key, None)
                    except Exception:
                        pass

            qtimer.timeout.connect(_on_timeout)
            timer_holder[key] = qtimer
            qtimer.start(wait)

        def cancel(*c_args, **c_kwargs):
            inst = c_args[0] if len(c_args) >= 1 else None
            timer_holder = None
            if inst is not None and hasattr(inst, "_throttle_timers"):
                timer_holder = getattr(inst, "_throttle_timers")
            elif hasattr(fn, "_throttle_timers"):
                timer_holder = getattr(fn, "_throttle_timers")
            if timer_holder:
                t = timer_holder.pop("_default", None)
                if t and isinstance(t, QTimer):
                    try:
                        t.stop()
                        t.deleteLater()
                    except Exception:
                        pass

        wrapper.cancel = cancel  # type: ignore
        return wrapper

    return decorator


class ThrottleQt:
    def __init__(self, wait_ms: int):
        self.wait_ms = wait_ms

    def __call__(self, fn: Callable):
        return throttle_qt(self.wait_ms)(fn)


# Aliases
throttle = throttle
Throttle = Throttle
throttle_qt = throttle_qt
ThrottleQt = ThrottleQt