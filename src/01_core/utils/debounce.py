#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe debounce utilities.

Provides:
- debounce(wait_ms): decorator for ordinary (sync) functions/methods.
- Debounce(wait_ms): same as debounce (class wrapper).
- debounce_qt(wait_ms): decorator that uses PyQt5.QtCore.QTimer when available,
  otherwise falls back to debounce().
- DebounceQt(wait_ms): class wrapper for debounce_qt.
"""
from __future__ import annotations

import threading
import functools
import logging
import asyncio
from typing import Callable, Any
import inspect

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
        logger.exception("Debounced function raised an exception")


def debounce(wait_ms: int):
    wait = float(wait_ms) / 1000.0

    def decorator(fn: Callable):
        timers = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = _make_key(fn, args, kwargs)

            def _runner():
                with lock:
                    timers.pop(key, None)
                _call_target(fn, args, kwargs)

            with lock:
                t = timers.get(key)
                if t is not None:
                    t.cancel()
                t = threading.Timer(wait, _runner)
                t.daemon = True
                timers[key] = t
                t.start()

        def cancel(*c_args, **c_kwargs):
            with lock:
                for t in list(timers.values()):
                    try:
                        t.cancel()
                    except Exception:
                        pass
                timers.clear()

        wrapper.cancel = cancel  # type: ignore
        return wrapper

    return decorator


class Debounce:
    def __init__(self, wait_ms: int):
        self.wait_ms = wait_ms

    def __call__(self, fn: Callable):
        return debounce(self.wait_ms)(fn)


# Qt-aware debounce (QTimer) if PyQt5 available
try:
    from PyQt5.QtCore import QTimer  # type: ignore
    _HAS_QT_TIMER = True
except Exception:
    _HAS_QT_TIMER = False


def debounce_qt(wait_ms: int):
    wait = int(wait_ms)

    if not _HAS_QT_TIMER:
        return debounce(wait_ms)

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            inst = args[0] if len(args) >= 1 else None
            timer_holder = None
            if inst is not None:
                if not hasattr(inst, "_debounce_timers"):
                    setattr(inst, "_debounce_timers", {})
                timer_holder = getattr(inst, "_debounce_timers")
            else:
                if not hasattr(fn, "_debounce_timers"):
                    setattr(fn, "_debounce_timers", {})
                timer_holder = getattr(fn, "_debounce_timers")

            key = "_default"
            existing = timer_holder.get(key)
            if existing and isinstance(existing, QTimer):
                try:
                    existing.stop()
                    existing.deleteLater()
                except Exception:
                    pass

            qtimer = QTimer()
            qtimer.setSingleShot(True)

            def _on_timeout():
                try:
                    fn(*args, **kwargs)
                except Exception:
                    logger.exception("DebounceQt target raised")

            qtimer.timeout.connect(_on_timeout)
            timer_holder[key] = qtimer
            qtimer.start(wait)

        def cancel(*c_args, **c_kwargs):
            inst = c_args[0] if len(c_args) >= 1 else None
            timer_holder = None
            if inst is not None and hasattr(inst, "_debounce_timers"):
                timer_holder = getattr(inst, "_debounce_timers")
            elif hasattr(fn, "_debounce_timers"):
                timer_holder = getattr(fn, "_debounce_timers")
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


class DebounceQt:
    def __init__(self, wait_ms: int):
        self.wait_ms = wait_ms

    def __call__(self, fn: Callable):
        return debounce_qt(self.wait_ms)(fn)


# Aliases
debounce = debounce
Debounce = Debounce
debounce_qt = debounce_qt
DebounceQt = DebounceQt