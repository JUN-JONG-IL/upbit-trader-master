#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redis ?∞Í≤∞ Í¥ÄÎ¶?""
import logging
import importlib
import importlib.util
import sys
from typing import Optional, Any
from .config import RedisConfig, get_config

# NOTE: This module is part of the local 'redis' package (src/data_01/redis/).
# When src/data_01/ is on sys.path, 'import redis.asyncio' would resolve to this
# local package instead of the PyPI redis package. We work around this by loading
# the external redis package explicitly via its file path in site-packages.
REDIS_AVAILABLE = False
redis = None  # type: ignore

def _load_external_redis_asyncio():
    """
    Load redis.asyncio from the installed PyPI redis package, bypassing the local
    'redis' package namespace collision (this file lives inside a package also
    named 'redis').

    Strategy:
    1. Temporarily remove local 'redis.*' entries from sys.modules and reorder
       sys.path so the external package loads cleanly under the 'redis' namespace.
    2. After import, remove external submodules that shadow local subpackages
       (e.g. the external flat redis/cache.py conflicts with our redis/cache/
       subdirectory).
    3. Restore local redis modules.  External submodules that do NOT conflict
       (redis.utils, redis.asyncio.*, redis.exceptions, ?? remain cached in
       sys.modules and are needed at runtime by the returned asyncio module.
    """
    import os
    # Our own package directory (src/data_01/redis/)
    our_dir = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Collect first-level submodule names that exist in the local package.
    # External redis submodules with the same name must not remain in sys.modules
    # after we return, to avoid masking the local ones.
    local_subnames: set = set()
    try:
        for _name in os.listdir(our_dir):
            if _name.startswith('_'):
                continue
            if os.path.isdir(os.path.join(our_dir, _name)):
                local_subnames.add(_name)
            elif _name.endswith('.py'):
                local_subnames.add(_name[:-3])
    except Exception:
        pass

    for entry in sys.path:
        if not entry:
            continue
        # Look for redis/asyncio/__init__.py to confirm this is a full redis package.
        asyncio_init = os.path.join(entry, 'redis', 'asyncio', '__init__.py')
        if not os.path.isfile(asyncio_init):
            continue
        candidate_dir = os.path.realpath(os.path.join(entry, 'redis'))
        # Skip if this candidate points to our own package
        if candidate_dir == our_dir:
            continue
        # Build a sys.path that excludes our local redis directory and puts the
        # external entry first.
        filtered = [
            e for e in sys.path
            if not (e and os.path.isdir(os.path.join(e, 'redis')) and
                    os.path.realpath(os.path.join(e, 'redis')) == our_dir)
        ]
        if entry not in filtered:
            filtered.insert(0, entry)
        # Save and temporarily remove all local redis modules from sys.modules so
        # the external package can be loaded under the 'redis' namespace.
        saved_mods = {k: v for k, v in sys.modules.items()
                      if k == 'redis' or k.startswith('redis.')}
        for k in saved_mods:
            del sys.modules[k]
        saved_path = sys.path[:]
        sys.path = filtered
        result = None
        try:
            import redis as _ext_pkg  # noqa: F401 ??loads external redis
            result = getattr(_ext_pkg, 'asyncio', None)
        except Exception:
            pass
        finally:
            sys.path = saved_path
            # Remove external modules whose names clash with local subpackages
            # (e.g. external redis/cache.py conflicts with local redis/cache/).
            for k in list(sys.modules.keys()):
                if not k.startswith('redis.'):
                    continue
                subname = k[len('redis.'):].split('.')[0]
                if subname in local_subnames:
                    del sys.modules[k]
            # Restore local redis modules (overwrite the top-level 'redis' entry
            # and any submodules that were previously loaded locally).
            sys.modules.update(saved_mods)
        if result is not None:
            return result
    return None


_ext_asyncio = _load_external_redis_asyncio()
if _ext_asyncio is not None:
    redis = _ext_asyncio
    REDIS_AVAILABLE = True
else:
    try:
        import aioredis as redis  # type: ignore
        REDIS_AVAILABLE = True
    except (ImportError, TypeError):
        # TypeError is raised on Python 3.11+ where asyncio.TimeoutError and
        # builtins.TimeoutError are the same class, causing aioredis to fail
        # with "duplicate base class TimeoutError".  Silently skip in that case.
        pass

LOG = logging.getLogger("redis.connection")

_client: Optional[Any] = None

# --------------------------------------------------------------------
# Background loop & helper (synchronous entry points)
# --------------------------------------------------------------------
import threading
import asyncio
import concurrent.futures
import atexit

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()

def _ensure_bg_loop() -> asyncio.AbstractEventLoop:
    """Ensure a background asyncio loop is running in a dedicated daemon thread."""
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is not None and _bg_thread is not None and _bg_thread.is_alive():
            return _bg_loop
        # create new loop and start thread
        loop = asyncio.new_event_loop()
        def _run_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        t = threading.Thread(target=_run_loop, daemon=True, name="redis-bg-loop")
        t.start()
        _bg_loop = loop
        _bg_thread = t
        return _bg_loop

def _run_coroutine_threadsafe(coro, timeout: Optional[float] = None):
    """
    Schedule a coroutine on the background loop and wait for result.
    Returns concurrent.futures.Future (the same return as run_coroutine_threadsafe).
    """
    loop = _ensure_bg_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    if timeout is not None:
        try:
            return fut.result(timeout=timeout)
        except Exception:
            raise
    return fut

def start_background_loop_and_client(config: Optional[RedisConfig] = None, wait: bool = True, timeout: float = 10.0) -> Optional[Any]:
    """
    Public helper: start a background asyncio loop (if needed) and create Redis client there.
    - If wait=True, this function blocks up to `timeout` seconds and returns the created client (or None on failure).
    - If wait=False, this returns the concurrent.futures.Future for the create_client coroutine.
    Use this from synchronous code (e.g. application bootstrap) to ensure Redis is available before/while GUI shows.
    """
    if not REDIS_AVAILABLE:
        LOG.warning("?†Ô∏è  redis ÎØ∏ÏÑ§Ïπ?- Redis ?∞Í≤∞ Î∂àÍ? (start_background skipped)")
        return None
    if wait:
        try:
            return _run_coroutine_threadsafe(create_client(config), timeout=timeout)
        except Exception as e:
            LOG.error("start_background_loop_and_client failed: %s", e)
            return None
    else:
        # return future so caller may check later
        loop = _ensure_bg_loop()
        return asyncio.run_coroutine_threadsafe(create_client(config), loop)

def stop_background_loop_and_client(wait: bool = True, timeout: float = 5.0) -> None:
    """
    Stop and cleanup background client and loop.
    - Closes client by scheduling close_client on the background loop.
    - Stops the loop and joins the thread.
    """
    global _bg_loop, _bg_thread
    if _bg_loop is None:
        return
    try:
        # ask client to close
        try:
            fut = asyncio.run_coroutine_threadsafe(close_client(), _bg_loop)
            if wait:
                try:
                    fut.result(timeout=timeout)
                except Exception:
                    LOG.warning("stop_background_loop_and_client: close_client did not finish cleanly")
        except Exception:
            LOG.exception("stop_background_loop_and_client: scheduling close_client failed")
        # stop loop
        def _stop_loop():
            try:
                _bg_loop.stop()
            except Exception:
                pass
        _bg_loop.call_soon_threadsafe(_stop_loop)
        # join thread
        if _bg_thread is not None and _bg_thread.is_alive():
            _bg_thread.join(timeout=timeout)
    finally:
        _bg_loop = None
        _bg_thread = None

# ensure cleanup at process exit (best-effort)
atexit.register(lambda: stop_background_loop_and_client(wait=True, timeout=2.0))

# --------------------------------------------------------------------
# Existing async API (unchanged semantics)
# --------------------------------------------------------------------
async def get_client(config: Optional[RedisConfig] = None) -> Optional[Any]:
    """?±Í???Redis ?¥Îùº?¥Ïñ∏??Î∞òÌôò"""
    global _client
    if _client is None:
        await create_client(config)
    return _client


async def create_client(config: Optional[RedisConfig] = None) -> Optional[Any]:
    """??Redis ?¥Îùº?¥Ïñ∏???ùÏÑ±"""
    global _client
    if not REDIS_AVAILABLE:
        LOG.warning("?†Ô∏è  redis ÎØ∏ÏÑ§Ïπ?- Redis ?∞Í≤∞ Î∂àÍ?")
        return None
    cfg = config or get_config()
    try:
        _client = redis.Redis(
            host=cfg.host,
            port=cfg.port,
            password=cfg.password,
            db=cfg.db,
            decode_responses=cfg.decode_responses,
            socket_timeout=cfg.socket_timeout,
            max_connections=cfg.max_connections,
        )
        await _client.ping()
        LOG.info("??Redis ?∞Í≤∞ ?ÑÎ£å (%s:%d)", cfg.host, cfg.port)
    except Exception as e:
        LOG.error("??Redis ?∞Í≤∞ ?§Ìå®: %s", e)
        _client = None
    return _client


async def close_client():
    """Redis ?¥Îùº?¥Ïñ∏??Ï¢ÖÎ£å"""
    global _client
    if _client:
        try:
            await _client.close()
        except Exception:
            pass
        _client = None
        LOG.info("??Redis ?∞Í≤∞ Ï¢ÖÎ£å")
