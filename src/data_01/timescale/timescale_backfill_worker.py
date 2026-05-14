#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill worker for Timescale gap jobs.

- Adds schema_version and job_id to all published events.
- Other behavior unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Local connector
from .timescale_db import TimescaleConnector

# Optional validator (repo may provide this)
try:
    from .timescale_validator import validate_candles_advanced  # type: ignore
except Exception:
    validate_candles_advanced = None  # type: ignore

# Redis optional (low-level redis library for queue ops)
try:
    import redis as _redis_lib  # type: ignore
except Exception:
    _redis_lib = None  # type: ignore

# Optional higher-level project redis wrapper (publish/set helpers)
try:
    from redis.core import get_client as _get_redis_client  # type: ignore
except Exception:
    try:
        from src.data.redis import get_client as _get_redis_client  # type: ignore
    except Exception:
        _get_redis_client = None  # type: ignore

logger = logging.getLogger("timescale_backfill")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] [timescale_backfill] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)
logger.propagate = False

QUEUE_PATH = Path.home() / ".timescale_gap_queue.jsonl"
FAILED_PATH = Path.home() / ".timescale_gap_failed.jsonl"
REDIS_QUEUE_KEY = "timescale:gap_queue"
EVENT_CHANNEL = "timescale:events"
JOB_STATUS_PREFIX = "timescale:job_status:"


@dataclass
class GapJob:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    interval_seconds: int
    priority: int = 0
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GapJob":
        j = d.get("job") if "job" in d else d
        raw_prio = j.get("priority", 0)
        priority = 0
        try:
            priority = int(raw_prio)
        except Exception:
            try:
                priority = int(float(str(raw_prio)))
            except Exception:
                mapping = {"low": 0, "medium": 5, "med": 5, "high": 10, "urgent": 15}
                if isinstance(raw_prio, str) and raw_prio.lower() in mapping:
                    priority = mapping[raw_prio.lower()]
                else:
                    priority = 0
        start = _parse_dt(j.get("start"))
        end = _parse_dt(j.get("end"))
        return cls(
            symbol=j["symbol"],
            timeframe=j.get("timeframe", "1m"),
            start=start,
            end=end,
            interval_seconds=int(j.get("interval_seconds", 60)),
            priority=priority,
            raw=j,
        )


def _parse_dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(float(v), tz=timezone.utc)
    else:
        dt = datetime.fromisoformat(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _job_key(job_raw: Dict[str, Any]) -> str:
    symbol = str(job_raw.get("symbol", ""))
    timeframe = str(job_raw.get("timeframe", ""))
    start = str(job_raw.get("start", ""))
    end = str(job_raw.get("end", ""))
    s = f"{symbol}|{timeframe}|{start}|{end}"
    h = hashlib.sha1(s.encode("utf8")).hexdigest()
    return JOB_STATUS_PREFIX + h


class BackfillWorker:
    def __init__(
        self,
        simulate: bool = True,
        use_redis: Optional[bool] = None,
        connector: Optional[TimescaleConnector] = None,
        max_retries: int = 3,
        base_backoff: float = 2.0,
    ):
        self.simulate = simulate
        self.use_redis = use_redis if use_redis is not None else bool(os.environ.get("REDIS_HOST") and _redis_lib is not None)
        self.connector = connector or TimescaleConnector()
        self.max_retries = int(os.environ.get("BACKFILL_MAX_RETRIES", max_retries))
        self.base_backoff = float(os.environ.get("BACKFILL_BASE_BACKOFF", base_backoff))
        self.redis_client = None
        if self.use_redis:
            if _redis_lib is None:
                logger.warning("Redis requested but 'redis' package not available; falling back to local JSONL queue")
                self.use_redis = False
            else:
                try:
                    self.redis_client = _redis_lib.Redis(
                        host=os.environ.get("REDIS_HOST", "localhost"),
                        port=int(os.environ.get("REDIS_PORT", "6379")),
                        password=os.environ.get("REDIS_PASSWORD") or None,
                        db=int(os.environ.get("REDIS_DB", "0")),
                        decode_responses=False,
                    )
                except Exception:
                    logger.exception("failed to create low-level redis client; disabling use_redis")
                    self.use_redis = False
                    self.redis_client = None
        self.pub_client = None
        if _get_redis_client is not None:
            try:
                self.pub_client = _get_redis_client()
            except Exception:
                logger.warning("project redis wrapper available but failed to initialize; continuing without pub_client")
                self.pub_client = None

    def connect_db(self) -> bool:
        ok = self.connector.connect()
        if ok:
            logger.info("Connected to DB")
        return ok

    # queue helpers (unchanged) ------------------------------------------------
    def _pop_local_queue(self) -> Optional[Dict[str, Any]]:
        if not QUEUE_PATH.exists():
            return None
        try:
            lines = QUEUE_PATH.read_text(encoding="utf8").splitlines()
            if not lines:
                return None
            first = lines[0]
            rest = lines[1:]
            QUEUE_PATH.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf8")
            try:
                obj = json.loads(first)
                return obj
            except Exception:
                logger.exception("Failed to parse queue line")
                return None
        except Exception:
            logger.exception("error popping local queue")
            return None

    def _requeue_local(self, obj: Dict[str, Any], front: bool = False) -> bool:
        try:
            QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if front and QUEUE_PATH.exists():
                existing = QUEUE_PATH.read_text(encoding="utf8")
                with QUEUE_PATH.open("w", encoding="utf8") as f:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    if existing:
                        f.write(existing)
            else:
                with QUEUE_PATH.open("a", encoding="utf8") as f:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            return True
        except Exception:
            logger.exception("failed to requeue local")
            return False

    def _pop_redis_queue(self) -> Optional[Dict[str, Any]]:
        try:
            raw = self.redis_client.lpop(REDIS_QUEUE_KEY)
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf8")
            return json.loads(raw)
        except Exception:
            logger.exception("error popping redis queue")
            return None

    def _requeue_redis(self, obj: Dict[str, Any], front: bool = False) -> bool:
        try:
            payload = json.dumps(obj, ensure_ascii=False)
            if front:
                self.redis_client.lpush(REDIS_QUEUE_KEY, payload)
            else:
                self.redis_client.rpush(REDIS_QUEUE_KEY, payload)
            return True
        except Exception:
            logger.exception("failed to requeue redis")
            return False

    # events / status ---------------------------------------------------------
    def _publish_event(self, event: Dict[str, Any]) -> None:
        try:
            if self.pub_client is not None:
                try:
                    if "ts" not in event:
                        event["ts"] = datetime.now(timezone.utc).isoformat()
                    self.pub_client.publish_event(EVENT_CHANNEL, event)
                    return
                except Exception:
                    logger.exception("pub_client.publish_event failed; falling back to low-level publish")
        except Exception:
            logger.exception("unexpected error in _publish_event pub_client path")

        if self.redis_client:
            try:
                self.redis_client.publish(EVENT_CHANNEL, json.dumps(event, default=str))
            except Exception:
                logger.exception("redis publish failed")

    def _mark_status(self, job_raw: Dict[str, Any], status: str, extra: Optional[Dict[str, Any]] = None, ttl_seconds: int = 86400) -> None:
        payload: Dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        if extra:
            payload.update(extra)
        j = job_raw.get("job") if isinstance(job_raw, dict) and "job" in job_raw else job_raw
        if isinstance(j, dict):
            for f in ("symbol", "timeframe", "start", "end"):
                v = j.get(f)
                if v is not None:
                    payload[f] = v

        if self.pub_client is not None:
            try:
                key = _job_key(job_raw)
                self.pub_client.set(key, payload, ttl_seconds)
                return
            except Exception:
                logger.exception("pub_client.set failed; falling back to low-level set")

        if self.redis_client:
            try:
                key = _job_key(job_raw)
                self.redis_client.set(key, json.dumps(payload, default=str), ex=ttl_seconds)
            except Exception:
                logger.exception("failed to mark job status in redis")

    def _write_failed(self, job_raw: Dict[str, Any], reason: str) -> None:
        try:
            line = json.dumps({"failed_at": datetime.now(timezone.utc).isoformat(), "reason": reason, "job": job_raw}, ensure_ascii=False)
            FAILED_PATH.parent.mkdir(parents=True, exist_ok=True)
            with FAILED_PATH.open("a", encoding="utf8") as f:
                f.write(line + "\n")
        except Exception:
            logger.exception("failed to write failed job record")

    # fetch & process ---------------------------------------------------------
    def _job_payload_has_dates(self, obj: Dict[str, Any]) -> bool:
        j = obj.get("job") if "job" in obj else obj
        if not isinstance(j, dict):
            return False
        s = j.get("start")
        e = j.get("end")
        invalid_vals = (None, "", "None")
        if s in invalid_vals or e in invalid_vals:
            return False
        return True

    def fetch_job(self) -> Optional[GapJob]:
        if self.use_redis and self.redis_client:
            obj = self._pop_redis_queue()
            if obj:
                if not self._job_payload_has_dates(obj):
                    logger.error("invalid job in redis queue (missing start/end) - moving to failed: %s", obj)
                    try:
                        self._write_failed(obj, "missing start or end")
                    except Exception:
                        logger.exception("failed to record invalid redis job")
                    return None
                try:
                    return GapJob.from_dict(obj)
                except Exception:
                    logger.exception("invalid job from redis queue")
                    try:
                        self._write_failed(obj, "parse error in GapJob.from_dict")
                    except Exception:
                        logger.exception("failed to record invalid redis job")
                    return None
        obj = self._pop_local_queue()
        if obj:
            if not self._job_payload_has_dates(obj):
                logger.error("invalid job in local queue (missing start/end) - moving to failed: %s", obj)
                try:
                    self._write_failed(obj, "missing start or end")
                except Exception:
                    logger.exception("failed to record invalid local job")
                return None
            try:
                return GapJob.from_dict(obj)
            except Exception:
                try:
                    if all(k in obj for k in ("symbol", "start", "end")):
                        return GapJob.from_dict({"job": obj})
                except Exception:
                    pass
                logger.exception("invalid job from local queue")
                try:
                    self._write_failed(obj, "parse error in GapJob.from_dict")
                except Exception:
                    logger.exception("failed to record invalid local job")
                return None
        return None

    def simulate_fetch_candles(self, job: GapJob, max_bars_per_batch: int = 500) -> List[tuple]:
        rows = []
        t = job.start
        i = int(job.interval_seconds)
        seq = 0
        try:
            symbol_full = str(job.symbol)
            symbol_safe = symbol_full[:20]
        except Exception:
            symbol_full = ""
            symbol_safe = ""
        while t <= job.end:
            open_v = 100 + (seq % 10)
            high_v = open_v + 1
            low_v = open_v - 1
            close_v = open_v
            volume = 1 + (seq % 5)
            ts = int(t.timestamp())
            rows.append(("upbit", symbol_safe, symbol_full, job.timeframe, t, open_v, high_v, low_v, close_v, volume, 0, True, ts))
            seq += 1
            t = t + timedelta(seconds=i)
            if len(rows) >= 10000:
                break
        return rows

    def _validate_rows(self, rows: List[tuple]) -> List[tuple]:
        if validate_candles_advanced is None:
            return rows
        try:
            res = validate_candles_advanced(rows)
            if res is False or res is None:
                raise RuntimeError("validator rejected rows")
            if isinstance(res, list):
                return res
            return rows
        except Exception:
            logger.exception("validator failed")
            raise

    def _requeue_job(self, job_raw: Dict[str, Any], attempt: int, priority: int) -> None:
        job_copy = dict(job_raw)
        job_copy["_attempt"] = attempt
        front = int(priority) >= 10
        if self.use_redis and self.redis_client:
            self._requeue_redis(job_copy, front=front)
        else:
            self._requeue_local(job_copy, front=front)

    def process_job(self, job: GapJob) -> bool:
        job_raw = job.raw or {
            "symbol": job.symbol,
            "timeframe": job.timeframe,
            "start": job.start.isoformat(),
            "end": job.end.isoformat(),
            "interval_seconds": job.interval_seconds,
            "priority": job.priority,
        }
        job_id = _job_key(job_raw)
        source = "simulate" if self.simulate else "exchange"
        base_event = {
            "schema_version": "1",
            "job_id": job_id,
            "source": source,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("Processing job: %s %s %s -> %s", job.symbol, job.timeframe, job.start.isoformat(), job.end.isoformat())
        self._mark_status(job_raw, "running")
        ev = dict(base_event)
        ev.update({"event": "backfill.started", "symbol": job.symbol, "timeframe": job.timeframe, "start": job.start.isoformat(), "end": job.end.isoformat()})
        self._publish_event(ev)
        try:
            if self.simulate:
                rows = self.simulate_fetch_candles(job)
            else:
                raise NotImplementedError("Real exchange adapter not implemented in worker; run with --simulate")
            if not rows:
                logger.info("No candles fetched for job")
                evc = dict(base_event)
                evc.update({"event": "backfill.completed", "symbol": job.symbol, "timeframe": job.timeframe, "inserted": 0})
                self._publish_event(evc)
                self._mark_status(job_raw, "completed", {"inserted": 0})
                return True

            chunk_size = 1000
            total_inserted = 0
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i : i + chunk_size]
                try:
                    validated = self._validate_rows(chunk)
                except Exception as e:
                    raise RuntimeError(f"validation failed: {e}") from e
                inserted = self.connector.insert_into_staging(validated)
                total_inserted += inserted

            moved = self.connector.flush_staging_to_candles()
            self.connector.update_latest_snapshot(job.symbol, job.timeframe)

            evc = dict(base_event)
            evc.update({"event": "backfill.completed", "symbol": job.symbol, "timeframe": job.timeframe, "inserted": total_inserted, "moved": moved, "duration_seconds": None})
            self._publish_event(evc)
            self._mark_status(job_raw, "completed", {"inserted": total_inserted, "moved": moved})
            logger.info("Job completed: inserted=%d moved=%d", total_inserted, moved)
            return True
        except Exception as e:
            logger.exception("Job processing failed: %s", e)
            eve = dict(base_event)
            eve.update({"event": "backfill.error", "symbol": job.symbol, "timeframe": job.timeframe, "error": str(e), "attempts": int(job_raw.get("_attempt", 0))})
            self._publish_event(eve)
            attempt = int(job_raw.get("_attempt", 0)) + 1
            if attempt <= self.max_retries:
                backoff = self.base_backoff * (2 ** (attempt - 1))
                logger.info("Requeueing job attempt=%d backoff=%.1fs", attempt, backoff)
                self._mark_status(job_raw, "retrying", {"attempt": attempt, "backoff_seconds": backoff})
                time.sleep(min(backoff, 30))
                self._requeue_job(job_raw, attempt=attempt, priority=job.priority)
            else:
                logger.error("Job exceeded max_retries=%d; moving to failed queue", self.max_retries)
                self._mark_status(job_raw, "failed", {"attempts": attempt})
                self._write_failed(job_raw, str(e))
            return False

    def run(self, max_jobs: Optional[int] = None, poll_interval: float = 1.0) -> None:
        if not self.connect_db():
            raise RuntimeError("DB connect failed")
        processed = 0
        while True:
            if max_jobs is not None and processed >= max_jobs:
                logger.info("Reached max_jobs=%d, exiting", max_jobs)
                break
            job = self.fetch_job()
            if not job:
                time.sleep(poll_interval)
                continue
            ok = self.process_job(job)
            processed += 1
            time.sleep(0.1)


def main():
    p = argparse.ArgumentParser(description="Timescale backfill worker")
    p.add_argument("--simulate", action="store_true", help="Use simulator to fetch candles")
    p.add_argument("--use-redis", action="store_true", help="Use Redis queue (timescale:gap_queue) instead of local JSONL")
    p.add_argument("--max-jobs", type=int, default=1, help="Maximum number of jobs to process then exit (default 1)")
    p.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval when queue empty (seconds)")
    args = p.parse_args()

    worker = BackfillWorker(simulate=args.simulate, use_redis=args.use_redis)
    try:
        worker.run(max_jobs=args.max_jobs, poll_interval=args.poll_interval)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Worker failed")


if __name__ == "__main__":
    main()