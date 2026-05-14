#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
timescale_utils.py

Utility helpers for the Timescale UI and worker modules.

Responsibilities:
- Build DSN strings from environment/UI inputs.
- Sanitize names (view names, identifiers).
- File-backed failed-insert queue (JSONL) helpers.
- Basic candle validation helper used by UI before bulk insert.
- CSV export helper (model -> CSV).
- Small helpers to keep dialog code concise and testable.

This improved version fixes typing/analysis issues (imports Dict) and hardens
file operations (ensures directory creation even when path dirname is empty).
"""
from __future__ import annotations

import os
import json
import logging
import re
from typing import List, Tuple, Optional, Callable, Any, Dict
from urllib.parse import quote_plus

logger = logging.getLogger("data.timescale.timescale_utils")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [timescale_utils] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.propagate = False

# Default failed-queue location (user home .timescale_failed_inserts.jsonl)
DEFAULT_FAILED_QUEUE = os.path.join(os.path.expanduser("~"), ".timescale_failed_inserts.jsonl")


# ----------------------------
# DSN builder
# ----------------------------
def timescale_build_dsn(
    host: Optional[str] = None,
    port: Optional[str] = None,
    db: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Build a libpq-style DSN string or a postgresql:// URL from parts.
    Uses fallbacks to environment variables.

    Priority:
      1) DATABASE_URL (if present, returned verbatim)
      2) PG*/POSTGRES_* env vars
      3) Function args
      4) Defaults

    Returns:
        str: either a full URL "postgresql://user:pw@host:port/db" or libpq style
             "dbname=... user=... host=... port=... password=..."
    """
    # 1) Direct DATABASE_URL override (most explicit)
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if db_url:
        return db_url

    # 2) gather from env or provided args
    host = host or os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or os.getenv("TIMESCALE_HOST") or os.getenv("POSTGRES_HOST_CONTAINER") or "127.0.0.1"
    port = str(port or os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "58529")
    db = db or os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or "upbit_trader"
    user = user or os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or os.getenv("POSTGRES_APP_USER") or "app_user"
    password = password or os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or os.getenv("POSTGRES_APP_PASSWORD") or ""

    # If we have a user (and optionally password), prefer returning a URL form for psycopg2.connect parsing convenience.
    if user:
        # If password contains special chars, quote it
        if password:
            try:
                user_enc = quote_plus(user)
                pw_enc = quote_plus(password)
                return f"postgresql://{user_enc}:{pw_enc}@{host}:{port}/{db}"
            except Exception:
                # Fallback to libpq style if quoting fails
                pass
        else:
            # No password provided -> still return URL without password
            try:
                user_enc = quote_plus(user)
                return f"postgresql://{user_enc}@{host}:{port}/{db}"
            except Exception:
                pass

    # Last resort: libpq keyword-style DSN
    parts = [f"dbname={db}", f"user={user}", f"host={host}", f"port={port}"]
    if password:
        parts.append(f"password={password}")
    dsn = " ".join(parts)
    return dsn


# ----------------------------
# Identifier sanitizers
# ----------------------------
_re_view_name_safe = re.compile(r"[^a-zA-Z0-9_]+")


def timescale_sanitize_view_name(raw: Optional[str], prefix: str = "cagg_candles_") -> str:
    """
    Convert arbitrary timeframe/spec into a safe view name.
    Example: "5 minutes" -> "cagg_candles_5_minutes"
    """
    if not raw:
        return prefix + "unknown"
    s = str(raw).strip().lower()
    s = s.replace(" ", "_").replace(":", "_").replace("-", "_")
    s = _re_view_name_safe.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return f"{prefix}{s}"


# ----------------------------
# File-backed failed-insert queue (simple JSONL)
# ----------------------------
def _ensure_parent_dir(fn: str) -> None:
    """
    Ensure the parent directory of fn exists.
    If dirname is empty, uses the user's home directory.
    """
    try:
        dirname = os.path.dirname(fn)
        if not dirname:
            dirname = os.path.expanduser("~")
        os.makedirs(dirname, exist_ok=True)
    except Exception:
        logger.exception("_ensure_parent_dir failed for %s", fn)


def timescale_enqueue_failed_insert(rows: List[Tuple[Any, ...]], filename: Optional[str] = None) -> None:
    """
    Append rows to a JSONL file for later retry. Non-fatal on errors.
    """
    fn = filename or DEFAULT_FAILED_QUEUE
    _ensure_parent_dir(fn)
    try:
        with open(fn, "a", encoding="utf-8") as f:
            for r in rows:
                try:
                    # convert tuples to lists for JSON compatibility
                    serial = list(r) if isinstance(r, (list, tuple)) else r
                    f.write(json.dumps(serial, default=str, ensure_ascii=False) + "\n")
                except Exception:
                    logger.exception("timescale_enqueue_failed_insert: row serialization failed")
        logger.info("timescale_enqueue_failed_insert: appended %d rows to %s", len(rows), fn)
    except Exception:
        logger.exception("timescale_enqueue_failed_insert: write failed")


def timescale_read_failed_queue(filename: Optional[str] = None) -> List[Tuple[Any, ...]]:
    """
    Read queued failed rows from the JSONL file.
    Returns list of tuple rows (possibly empty).
    """
    fn = filename or DEFAULT_FAILED_QUEUE
    if not os.path.exists(fn):
        return []
    rows: List[Tuple[Any, ...]] = []
    try:
        with open(fn, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, list):
                        rows.append(tuple(obj))
                    else:
                        rows.append((obj,))
                except Exception:
                    logger.exception("timescale_read_failed_queue: parse error")
        return rows
    except Exception:
        logger.exception("timescale_read_failed_queue: file read failed")
        return []


def timescale_clear_failed_queue(filename: Optional[str] = None) -> None:
    """
    Remove the failed queue file.
    """
    fn = filename or DEFAULT_FAILED_QUEUE
    try:
        if os.path.exists(fn):
            os.remove(fn)
            logger.info("timescale_clear_failed_queue: removed %s", fn)
    except Exception:
        logger.exception("timescale_clear_failed_queue: remove failed")


def timescale_retry_failed_queue(
    insert_callable: Callable[[List[Tuple[Any, ...]], Optional[Dict[str, Any]]], Any],
    filename: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Attempt to replay the failed queue by calling insert_callable(rows, context).
    On success the queue file is removed. Returns result of insert_callable or None.
    """
    fn = filename or DEFAULT_FAILED_QUEUE
    rows = timescale_read_failed_queue(fn)
    if not rows:
        logger.info("timescale_retry_failed_queue: no queued rows")
        return None
    try:
        res = insert_callable(rows, context or {})
        try:
            os.remove(fn)
        except Exception:
            logger.exception("timescale_retry_failed_queue: could not remove queue file after success")
        logger.info("timescale_retry_failed_queue: replayed %d rows", len(rows))
        return res
    except Exception:
        logger.exception("timescale_retry_failed_queue: replay failed")
        return None


# ----------------------------
# Candle validation (UI-level)
# ----------------------------
def timescale_validate_candle_advanced(rows: List[Tuple[Any, ...]], max_issues: int = 500) -> Tuple[bool, List[str]]:
    """
    Validate rows in the UI format:
      (exchange, symbol, tf, time_val, open, high, low, close, volume, trade_count, is_closed, ts)

    Returns:
      (ok: bool, issues: List[str])
    """
    issues: List[str] = []
    for i, r in enumerate(rows):
        try:
            # Defensive indexing -- ensure tuple/list length
            time_val = r[3] if len(r) > 3 else None
            open_v = r[4] if len(r) > 4 else None
            high_v = r[5] if len(r) > 5 else None
            low_v = r[6] if len(r) > 6 else None
            close_v = r[7] if len(r) > 7 else None
            vol_v = r[8] if len(r) > 8 else None

            if not time_val:
                issues.append(f"row {i}: time missing")
            if high_v is not None and low_v is not None:
                try:
                    if float(high_v) < float(low_v):
                        issues.append(f"row {i}: high < low ({high_v} < {low_v})")
                except Exception:
                    issues.append(f"row {i}: high/low type error")
            if open_v is None or close_v is None:
                issues.append(f"row {i}: open/close missing")
            if vol_v is not None:
                try:
                    if float(vol_v) < 0:
                        issues.append(f"row {i}: volume negative")
                except Exception:
                    issues.append(f"row {i}: volume type error")
        except Exception:
            issues.append(f"row {i}: unexpected error in validation")
        if len(issues) >= max_issues:
            break
    return (len(issues) == 0, issues)


# ----------------------------
# CSV helper (model -> CSV)
# ----------------------------
def timescale_save_model_to_csv(model, path: str, encoding: str = "utf-8") -> None:
    """
    Save a Qt model (QStandardItemModel or similar) to CSV.
    model: should implement rowCount(), columnCount(), and item(row,col).text()
    """
    try:
        with open(path, "w", newline="", encoding=encoding) as f:
            import csv as _csv
            writer = _csv.writer(f)
            # headerData signature can vary; attempt robust retrieval
            headers = []
            try:
                for c in range(model.columnCount()):
                    h = model.headerData(c, 1)  # Qt.Horizontal == 1
                    headers.append(str(h) if h is not None else "")
            except Exception:
                # fallback: empty headers
                headers = ["" for _ in range(model.columnCount())]
            writer.writerow(headers)
            for r in range(model.rowCount()):
                row = []
                for c in range(model.columnCount()):
                    try:
                        item = model.item(r, c)
                        row.append(item.text() if item is not None else "")
                    except Exception:
                        row.append("")
                writer.writerow(row)
        logger.info("timescale_save_model_to_csv: saved to %s", path)
    except Exception:
        logger.exception("timescale_save_model_to_csv failed")


# ----------------------------
# Small helpers
# ----------------------------
def timescale_read_env_defaults() -> Dict[str, str]:
    """
    Read common Postgres env vars and return dict for UI defaults.
    """
    return {
        "host": os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or os.getenv("TIMESCALE_HOST") or "127.0.0.1",
        "port": os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "58529",
        "db": os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or "upbit_trader",
        "user": os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or "app_user",
        "password": os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or "",
    }


# End of file