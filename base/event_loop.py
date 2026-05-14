#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centralized event loop helpers for the project.

Goals:
- Provide a single robust implementation for:
    * setup_event_loop(): (optional) set Windows selector policy early
    * get_event_loop(): return a usable event loop (prefers running loop)
    * current_running_loop(): return running loop or None
    * safe_create_task(coro, *, loop=None): create/schedule coroutine safely
    * run_coro_threadsafe(coro, loop=None): schedule coroutine thread-safely
- Small, well-documented surface so other modules import these helpers instead
  of defining local fallbacks.
- Avoid creating multiple conflicting event loops at import-time.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import sys
from typing import Optional, Any

logger = logging.getLogger("base.event_loop")

def setup_event_loop():
    """
    Call early in process startup (main thread) to apply process-global policies.
    - On Windows, try to set WindowsSelectorEventLoopPolicy to avoid Proactor/aiodns issues.
    Safe to call multiple times.
    """
    if sys.platform == "win32":
        try:
            # WindowsSelectorEventLoopPolicy is preferred for many network libs on Windows
            policy = asyncio.WindowsSelectorEventLoopPolicy()
            asyncio.set_event_loop_policy(policy)
            logger.debug("WindowsSelectorEventLoopPolicy set")
        except Exception:
            logger.debug("Failed to set WindowsSelectorEventLoopPolicy", exc_info=True)

def current_running_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Return asyncio.get_running_loop() or None if there is no running loop in this thread."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None

def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Return a usable event loop for the current thread.
    Preference:
      1) running loop in current thread (get_running_loop)
      2) asyncio.get_event_loop() (may return a set loop)
      3) create a new event loop, set it for the thread and return it
    Note: creating a new loop will set it as the thread's event loop.
    """
    # Prefer an existing running loop
    try:
        loop = asyncio.get_running_loop()
        if loop is not None and not loop.is_closed():
            return loop
    except RuntimeError:
        # no running loop in this thread
        pass

    # Try asyncio.get_event_loop (may return a loop or raise)
    try:
        loop = asyncio.get_event_loop()
        # If loop is closed, create a new one
        if loop.is_closed():
            logger.debug("get_event_loop: existing loop is closed, creating a new one")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            return new_loop
        return loop
    except Exception:
        # Fallback: create and set a new loop
        logger.debug("get_event_loop: no loop available, creating new event loop")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop

def safe_create_task(coro: Any, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> Optional[asyncio.Task]:
    """
    Create/schedule a coroutine as a Task in a safe way.
    Behavior:
      - If there is a running loop in current thread -> schedule with create_task
      - Else if a loop argument is provided and running -> use loop.create_task
      - Else try to obtain a project loop via get_event_loop() and, if running, schedule
      - Else if a suitable running loop cannot be found, skip and return None (log at debug)
    Returns the Task object when successfully scheduled, otherwise None.
    Important: this function avoids calling asyncio.create_task when the interpreter is shutting down.
    """
    try:
        # 1) If current thread has running loop, schedule there
        running = current_running_loop()
        if running is not None and not running.is_closed():
            return running.create_task(coro)

        # 2) Try provided loop if given
        if loop is not None:
            try:
                if loop.is_running() and not loop.is_closed():
                    return loop.create_task(coro)
            except Exception:
                pass

        # 3) Try to obtain a loop via get_event_loop(), but only schedule if it's running
        try:
            maybe_loop = get_event_loop()
            if maybe_loop and maybe_loop.is_running() and not maybe_loop.is_closed():
                return maybe_loop.create_task(coro)
        except Exception:
            pass

        # 4) No running loop available to safely schedule -> skip
        logger.debug("safe_create_task: no running event loop to schedule coroutine; skipping task creation")
        return None
    except Exception as e:
        logger.debug("safe_create_task: skipping task creation (%s)", e, exc_info=True)
        return None

def run_coro_threadsafe(coro: Any, loop: Optional[asyncio.AbstractEventLoop] = None):
    """
    Schedule a coroutine to run on a loop from another thread via asyncio.run_coroutine_threadsafe.
    Returns the concurrent.futures.Future or None on failure.
    """
    try:
        target = loop or get_event_loop()
        if target is None:
            return None
        if not target.is_running() or target.is_closed():
            logger.debug("run_coro_threadsafe: target loop not running/closed")
            return None
        return asyncio.run_coroutine_threadsafe(coro, target)
    except Exception:
        logger.debug("run_coro_threadsafe failed", exc_info=True)
        return None