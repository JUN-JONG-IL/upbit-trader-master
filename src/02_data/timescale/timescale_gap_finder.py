#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
timescale_gap_finder - gap detection and enqueue helper

Responsibilities:
- detect_all_and_enqueue(): 비교적 보수적인 gap 감지(최근 스냅샷 기반) 및 job 생성
- get_queue_length(): 로컬 JSONL 또는 Redis 기반 큐 길이 반환
- Robust imports: TimescaleConnector, Redis optional
- Writes JSONL to ~/.timescale_gap_queue.jsonl and (if redis available) pushes to list 'timescale:gap_queue'
- Publishes lightweight event to 'timescale:events' channel when enqueueing (if redis available)

변경 사항:
- Redis 클라이언트 캐시 유지
- Redis lpush 실패시 reconnect 시도(재생성 후 1회 재시도)
- 실패 시 전체 예외 스택(traceback)을 로그/출력에 남기도록 보강
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

# optional logger (use static.log if available)
try:
    import server.static as static
    LOG = getattr(static, "log", None)
except Exception:
    LOG = None

# Defaults
LOCAL_QUEUE_PATH = os.path.expanduser("~/.timescale_gap_queue.jsonl")
REDIS_QUEUE_KEY = "timescale:gap_queue"
REDIS_EVENT_CHANNEL = "timescale:events"
DEFAULT_STALE_MINUTES = 5
DEFAULT_FALLBACK_WINDOW_HOURS = 1
MAX_JOBS_PER_RUN = 10_000

# Cached redis client (to avoid repeated ping/connect overhead and environment differences)
_CACHED_REDIS = None
_REDIS_CHECKED = False


def _log_info(msg: str, *args):
    if LOG:
        try:
            LOG.info(msg % args if args else msg)
            return
        except Exception:
            pass
    try:
        print("[timescale_gap_finder][INFO]", msg % args if args else msg)
    except Exception:
        pass


def _log_warning(msg: str, *args):
    if LOG:
        try:
            LOG.warning(msg % args if args else msg)
            return
        except Exception:
            pass
    try:
        print("[timescale_gap_finder][WARN]", msg % args if args else msg)
    except Exception:
        pass


def _log_exception(msg: str, *args):
    if LOG:
        try:
            LOG.exception(msg % args if args else msg)
            return
        except Exception:
            pass
    try:
        # include formatted traceback if available in args or capture current
        if args:
            try:
                print("[timescale_gap_finder][EXC]", (msg % args))
            except Exception:
                print("[timescale_gap_finder][EXC]", msg, args)
        else:
            print("[timescale_gap_finder][EXC]", msg)
        print(traceback.format_exc())
    except Exception:
        pass


def _import_timescale_connector():
    """Robust import of TimescaleConnector class."""
    candidates = (
        "src.data.timescale.timescale_db",
        "data.timescale.timescale_db",
        "data.timescale.timescale_db",
        "src.timescale_db",
    )
    for p in candidates:
        try:
            mod = importlib.import_module(p)
            cls = getattr(mod, "TimescaleConnector", None)
            if cls:
                _log_info("Imported TimescaleConnector from %s", p)
                return cls
        except Exception:
            continue
    # try file fallback relative to repo
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.abspath(os.path.join(here, "..", "timescale", "timescale_db.py"))
        if os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location("timescale_db_file", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                cls = getattr(mod, "TimescaleConnector", None)
                if cls:
                    _log_info("Imported TimescaleConnector from file %s", candidate)
                    return cls
    except Exception:
        _log_exception("file-load fallback for TimescaleConnector failed")
    return None


def _create_redis_client():
    """Try to create a new redis client (no caching)."""
    try:
        import redis as redis_mod  # type: ignore
    except Exception:
        return None, "redis package not available"
    # decide URL/host
    url = os.environ.get("REDIS_URL")
    try:
        if url:
            r = redis_mod.Redis.from_url(url)
        else:
            host = os.environ.get("REDIS_HOST", "localhost")
            port = int(os.environ.get("REDIS_PORT", 6379))
            password = os.environ.get("REDIS_PASSWORD", None)
            if password:
                r = redis_mod.Redis(host=host, port=port, password=password, decode_responses=False)
            else:
                r = redis_mod.Redis(host=host, port=port, decode_responses=False)
    except Exception as e:
        return None, f"redis client init failed: {e}"
    # ping
    try:
        r.ping()
        return r, None
    except Exception as e:
        return None, f"redis ping failed: {e}"


def _get_cached_redis_client():
    """
    Return a cached redis client or None. Will attempt to initialize once per process.
    """
    global _CACHED_REDIS, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _CACHED_REDIS
    _REDIS_CHECKED = True
    try:
        client, err = _create_redis_client()
        if client:
            _CACHED_REDIS = client
            _log_info("Connected to Redis for queue/pubsub")
        else:
            _CACHED_REDIS = None
            _log_warning("Redis unavailable: %s", err)
    except Exception as e:
        _CACHED_REDIS = None
        _log_exception("Unexpected error while creating redis client: %s", e)
    return _CACHED_REDIS


def _recreate_redis_client():
    """
    Force recreate redis client (used when cached client fails during use).
    """
    global _CACHED_REDIS, _REDIS_CHECKED
    try:
        client, err = _create_redis_client()
        if client:
            _CACHED_REDIS = client
            _REDIS_CHECKED = True
            _log_info("Recreated Redis client successfully")
            return client
        else:
            _CACHED_REDIS = None
            _REDIS_CHECKED = True
            _log_warning("Recreate Redis client failed: %s", err)
            return None
    except Exception as e:
        _CACHED_REDIS = None
        _REDIS_CHECKED = True
        _log_exception("Recreate redis unexpected: %s", e)
        return None


def _append_local_queue(job: Dict[str, Any]) -> None:
    """Append job as JSON line to local queue file."""
    try:
        parent = os.path.dirname(LOCAL_QUEUE_PATH) or os.path.expanduser("~")
        os.makedirs(parent, exist_ok=True)
    except Exception:
        pass
    try:
        with open(LOCAL_QUEUE_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(job, default=str, ensure_ascii=False) + "\n")
    except Exception:
        _log_exception("Failed to append job to local queue file")


def _publish_redis(r, job: Dict[str, Any]) -> bool:
    """Push job to Redis list and publish event (best-effort). Returns True if lpush succeeded."""
    try:
        payload = json.dumps(job, default=str, ensure_ascii=False)
    except Exception:
        payload = str(job)
    # attempt using provided client
    try:
        r.lpush(REDIS_QUEUE_KEY, payload)
        try:
            r.publish(REDIS_EVENT_CHANNEL, json.dumps({"type": "job_enqueued", "job": job}, default=str, ensure_ascii=False))
        except Exception:
            _log_warning("Redis publish failed (advisory)")
        _log_info("Redis lpush succeeded for job symbol=%s tf=%s", job.get("symbol"), job.get("timeframe"))
        return True
    except Exception as e:
        # log full exception stack for diagnosis
        _log_exception("Redis lpush failed (first attempt): %s", e)
        # try ping; if ping fails then try recreate client and retry once
        try:
            r.ping()
            _log_warning("Redis ping succeeded after lpush failure (unexpected). Not retrying.")
            return False
        except Exception:
            _log_warning("Redis ping failed (client appears dead) - attempting recreate and retry")
        new_r = _recreate_redis_client()
        if not new_r:
            _log_warning("Redis recreate failed; will fallback to local queue")
            return False
        # retry once with new client
        try:
            new_r.lpush(REDIS_QUEUE_KEY, payload)
            try:
                new_r.publish(REDIS_EVENT_CHANNEL, json.dumps({"type": "job_enqueued", "job": job}, default=str, ensure_ascii=False))
            except Exception:
                _log_warning("Redis publish failed on retry (advisory)")
            _log_info("Redis lpush succeeded on retry for job symbol=%s tf=%s", job.get("symbol"), job.get("timeframe"))
            return True
        except Exception as e2:
            _log_exception("Redis lpush failed on retry: %s", e2)
            return False


def _parse_iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # try datetime.fromisoformat
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            # fallback to common formats
            from dateutil import parser as _p  # type: ignore
            dt = _p.parse(s)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def should_enqueue(symbol: Optional[str]) -> bool:
    """
    Guard: decide whether a symbol should be enqueued.
    """
    if not symbol:
        return False
    regex = os.environ.get("NO_ENQUEUE_REGEX")
    if regex:
        try:
            if re.search(regex, symbol):
                _log_info("Guard: symbol '%s' blocked by NO_ENQUEUE_REGEX='%s'", symbol, regex)
                return False
        except re.error:
            _log_warning("Invalid NO_ENQUEUE_REGEX pattern: '%s'", regex)
    v = os.environ.get("NO_TEST_ENQUEUE", "").lower()
    if v in ("1", "true", "yes", "on"):
        if symbol.startswith("KRW-TEST"):
            _log_info("Guard: symbol '%s' blocked by NO_TEST_ENQUEUE", symbol)
            return False
    return True


def detect_all_and_enqueue(limit: int = 100, stale_minutes: int = DEFAULT_STALE_MINUTES, fallback_hours: int = DEFAULT_FALLBACK_WINDOW_HOURS) -> int:
    """
    Detect gaps across known symbols/timeframes and enqueue backfill jobs.

    Returns number of jobs enqueued.
    """
    enqueued = 0
    connector_cls = _import_timescale_connector()
    if connector_cls is None:
        _log_warning("TimescaleConnector not available; cannot detect gaps")
        return 0

    # try to create connector
    try:
        conn = connector_cls()
        if not conn.connect():
            _log_warning("TimescaleConnector.connect() failed; aborting detection")
            try:
                conn.close()
            except Exception:
                pass
            return 0
    except Exception:
        _log_exception("Failed to instantiate TimescaleConnector")
        return 0

    redis_client = _get_cached_redis_client()
    if redis_client is None:
        _log_info("Redis client not available for this run; jobs will be appended to local JSONL only")
    else:
        _log_info("Redis client available; jobs will be pushed to Redis and local JSONL (best-effort)")

    try:
        symbols = conn.get_distinct_symbols()
    except Exception:
        _log_exception("conn.get_distinct_symbols failed")
        symbols = []

    now = datetime.now(timezone.utc)
    limit_remaining = max(0, int(limit))

    for symbol in (symbols or []):
        if limit_remaining <= 0:
            break

        try:
            if not should_enqueue(symbol):
                _log_info("Skipping symbol by guard: %s", symbol)
                continue
        except Exception:
            _log_warning("should_enqueue check failed for '%s', skipping", symbol)
            continue

        try:
            tfs = conn.get_distinct_timeframes(symbol) or []
        except Exception:
            _log_exception("get_distinct_timeframes failed for %s", symbol)
            tfs = []
        for tf in tfs:
            if limit_remaining <= 0:
                break
            try:
                last = conn.get_last_timestamp(symbol, tf)
            except Exception:
                last = None
            last_dt = _parse_iso_to_dt(last)
            if last_dt is None:
                start = now - timedelta(hours=fallback_hours)
            else:
                start = last_dt
            if (now - start) <= timedelta(minutes=stale_minutes):
                continue
            job = {
                "symbol": symbol,
                "timeframe": tf,
                "start": start.isoformat() if isinstance(start, datetime) else str(start),
                "end": now.isoformat(),
                "created_at": now.isoformat(),
                "source": "timescale_gap_finder",
            }
            try:
                _append_local_queue(job)
                pushed = False
                if redis_client:
                    pushed = _publish_redis(redis_client, job)
                    if not pushed:
                        _log_warning("Redis push failed for %s %s; job written to local queue as fallback", symbol, tf)
                enqueued += 1
                limit_remaining -= 1
                _log_info("Enqueued job: %s %s %s -> %s (redis_pushed=%s)", symbol, tf, job["start"], job["end"], pushed)
            except Exception:
                _log_exception("Failed enqueuing job for %s %s", symbol, tf)
            if enqueued >= MAX_JOBS_PER_RUN:
                _log_warning("Reached MAX_JOBS_PER_RUN (%d), stopping", MAX_JOBS_PER_RUN)
                break

    try:
        conn.close()
    except Exception:
        pass

    _log_info("detect_all_and_enqueue completed, enqueued=%d", enqueued)
    return enqueued


# alias names
def detect_gaps_and_enqueue_all(*args, **kwargs):
    return detect_all_and_enqueue(*args, **kwargs)


def detect_gaps_for_all(*args, **kwargs):
    return detect_all_and_enqueue(*args, **kwargs)


def get_queue_length() -> int:
    """Return approximate queue length (Redis LLEN preferred, fallback to local JSONL)."""
    try:
        r = _get_cached_redis_client()
        if r:
            try:
                l = r.llen(REDIS_QUEUE_KEY)
                return int(l)
            except Exception as e:
                _log_warning("Redis LLEN failed: %s; falling back to file", e)
        if os.path.isfile(LOCAL_QUEUE_PATH):
            try:
                with open(LOCAL_QUEUE_PATH, "r", encoding="utf-8") as fh:
                    return sum(1 for _ in fh)
            except Exception:
                _log_exception("counting local queue file failed")
                return 0
        return 0
    except Exception:
        _log_exception("get_queue_length unexpected error")
        return 0