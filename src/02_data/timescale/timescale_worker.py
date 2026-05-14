#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
timescale_worker.py

Connector worker module for TimescaleDB operations.

This module provides:
- timescale_ConnectorWorker: a QObject-based worker that runs DB operations
  in a background thread and emits Qt signals for results/errors/status.
- Flexible action mapping so the UI can request high-level actions like
  "select_recent", "bulk_insert", "create_cagg", etc.

Design goals:
- Keep DB/IO work off the GUI thread.
- Provide clear signals for result / error / status / finished.
- Be tolerant of different TimescaleConnector implementations (method name fallbacks).
- Minimal external dependencies (only PyQt5).
"""

from __future__ import annotations

import importlib
import threading
import logging
from typing import Any, Tuple, Optional, List

from PyQt5 import QtCore

# Try flexible imports for TimescaleConnector to support multiple package layouts.
_timescale_connector = None
_connector_module_paths = (
    "data.timescale.timescale_db",
    "src.data.timescale.timescale_db",
    "timescale_db",
)
for _p in _connector_module_paths:
    try:
        m = importlib.import_module(_p)
        _timescale_connector = getattr(m, "TimescaleConnector", None)
        if _timescale_connector:
            break
    except Exception:
        _timescale_connector = None

logger = logging.getLogger("data.timescale.timescale_worker")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [timescale_worker] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.propagate = False


class timescale_ConnectorWorker(QtCore.QObject):
    """
    QObject-based worker to run TimescaleConnector operations in a background thread.

    Signals:
      - finished(): emitted when the background task completes (success or error).
      - result(object): emitted with the result of the operation.
      - error(str): emitted when an exception occurs (string message).
      - status(str): emitted to indicate progress/status messages.
    """

    finished = QtCore.pyqtSignal()
    result = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)

    def __init__(self, dsn: str, timeout: int = 10):
        """
        Args:
            dsn: libpq-style DSN string or connector-specific connection string.
            timeout: connect/operation timeout (seconds) — passed to connector if supported.
        """
        super().__init__()
        self.dsn = dsn
        self.timeout = timeout
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ---- internal helpers ----
    def _emit_error_from_exc(self, exc: Exception):
        try:
            msg = f"{type(exc).__name__}: {exc}"
        except Exception:
            msg = repr(exc)
        logger.error(msg)
        self.error.emit(msg)

    def _get_connector(self):
        """
        Instantiate the TimescaleConnector. Raises RuntimeError if not available.
        """
        if _timescale_connector is None:
            raise RuntimeError("TimescaleConnector implementation not found (import failed).")
        try:
            conn = _timescale_connector(self.dsn)
            return conn
        except Exception as e:
            raise RuntimeError(f"TimescaleConnector init failed: {e}")

    # ---- public API ----
    def run_query(self, sql: str, params: Tuple = ()):
        """
        Run an arbitrary SELECT-style query and emit rows via result signal.
        Runs in a background thread.
        """
        def _target():
            conn = None
            try:
                if self._stop_event.is_set():
                    self.status.emit("작업 취소됨")
                    return
                self.status.emit("쿼리 실행...")
                conn = self._get_connector()
                # Some connectors accept connect(timeout=...), others not — try best-effort
                try:
                    conn.connect(timeout=self.timeout)
                except TypeError:
                    conn.connect()
                rows = conn.run_query(sql, params)
                self.result.emit(rows)
            except Exception as e:
                logger.exception("run_query 예외: %s", e)
                self._emit_error_from_exc(e)
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
                self.finished.emit()

        self._stop_event.clear()
        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()

    def run_action(self, action: str, *args, **kwargs):
        """
        Run a named action against the connector. Supported actions (high-level):
          - ensure_extension
          - ensure_candles
          - create_cagg (view_name, bucket_interval, where_clause)
          - refresh_cagg (view_name)
          - add_compression_policy (table_name, interval)
          - bulk_insert (rows_iterable)
          - get_distinct_symbols ()
          - get_timeframes_for_symbol (symbol)
          - select_recent (symbol, tf, limit)
          - select_since (symbol, tf, since, limit)
          - get_last_timestamp (symbol, tf)

        Emits result() with the action's return value, or error() on exception.
        """
        def _target():
            conn = None
            try:
                if self._stop_event.is_set():
                    self.status.emit("작업 취소됨")
                    return
                self.status.emit(f"작업 실행: {action} ...")
                conn = self._get_connector()
                try:
                    conn.connect(timeout=self.timeout)
                except TypeError:
                    conn.connect()

                res = None
                # map actions to connector methods (with graceful fallbacks)
                if action == "ensure_extension":
                    res = getattr(conn, "ensure_timescaledb_extension", lambda: None)()
                elif action == "ensure_candles":
                    if hasattr(conn, "ensure_candles_hypertable"):
                        res = conn.ensure_candles_hypertable()
                    elif hasattr(conn, "ensure_hypertable"):
                        res = conn.ensure_hypertable("candles")
                    else:
                        raise RuntimeError("Connector does not implement ensure_candles")
                elif action == "create_cagg":
                    view_name, bucket_interval, where = args
                    if hasattr(conn, "create_continuous_aggregate"):
                        res = conn.create_continuous_aggregate(view_name, bucket_interval, where)
                    elif hasattr(conn, "create_cagg"):
                        res = conn.create_cagg(view_name, bucket_interval, where)
                    else:
                        raise RuntimeError("Connector create_cagg API not found")
                elif action == "refresh_cagg":
                    view_name, = args
                    if hasattr(conn, "refresh_materialized_view"):
                        res = conn.refresh_materialized_view(view_name, concurrently=kwargs.get("concurrent", True))
                    else:
                        # fallback to generic refresh
                        res = conn.run_query(f"REFRESH MATERIALIZED VIEW {view_name};")
                elif action == "add_compression_policy":
                    table_name, older_than = args
                    if hasattr(conn, "add_compression_policy"):
                        res = conn.add_compression_policy(table_name, older_than)
                    else:
                        # no-op fallback
                        res = None
                elif action == "bulk_insert":
                    rows_iterable, = args
                    if hasattr(conn, "insert_candles_bulk"):
                        res = conn.insert_candles_bulk(rows_iterable)
                    else:
                        raise RuntimeError("Connector bulk insert API not found")
                elif action == "get_distinct_symbols":
                    # prefer connector method if available and normalize to list[str]
                    if hasattr(conn, "get_distinct_symbols"):
                        t = conn.get_distinct_symbols()
                        res = [str(x) for x in (t or [])]
                    else:
                        rows = conn.run_query("SELECT DISTINCT symbol FROM public.candles ORDER BY symbol;")
                        lst: List[str] = []
                        for r in rows or []:
                            if isinstance(r, dict):
                                v = r.get("symbol")
                            elif isinstance(r, (list, tuple)):
                                v = r[0] if r else None
                            else:
                                v = r
                            if v is not None:
                                lst.append(str(v))
                        res = lst
                elif action == "get_timeframes_for_symbol":
                    # NEW: return list[str] of timeframe codes for given symbol
                    symbol, = args
                    if hasattr(conn, "get_distinct_timeframes"):
                        t = conn.get_distinct_timeframes(symbol)
                        res = [str(x) for x in (t or [])]
                    else:
                        rows = conn.run_query("SELECT DISTINCT timeframe FROM public.candles WHERE symbol = %s ORDER BY timeframe;", (symbol,))
                        lst: List[str] = []
                        for r in rows or []:
                            if isinstance(r, dict):
                                v = r.get("timeframe")
                            elif isinstance(r, (list, tuple)):
                                v = r[0] if r else None
                            else:
                                v = r
                            if v is not None:
                                lst.append(str(v))
                        res = lst
                elif action == "select_recent":
                    symbol, tf, limit = args
                    if hasattr(conn, "select_recent"):
                        res = conn.select_recent(symbol, tf, limit)
                    else:
                        # fallback raw SQL attempt (psycopg2 param style)
                        sql = "SELECT time, open, high, low, close, volume FROM public.candles WHERE symbol = %s AND timeframe = %s ORDER BY time DESC LIMIT %s;"
                        res = conn.run_query(sql, (symbol, tf, limit))
                elif action == "select_since":
                    symbol, tf, since, limit = args
                    if hasattr(conn, "select_since"):
                        res = conn.select_since(symbol, tf, since, limit)
                    else:
                        sql = "SELECT time, open, high, low, close, volume FROM public.candles WHERE symbol = %s AND timeframe = %s AND time > %s ORDER BY time ASC LIMIT %s;"
                        res = conn.run_query(sql, (symbol, tf, since, limit))
                elif action == "get_last_timestamp":
                    symbol, tf = args
                    if hasattr(conn, "get_last_timestamp"):
                        res = conn.get_last_timestamp(symbol, tf)
                    else:
                        rows = conn.run_query("SELECT time FROM public.latest_snapshot WHERE symbol = %s AND timeframe = %s;", (symbol, tf))
                        if rows:
                            r = rows[0]
                            if isinstance(r, dict):
                                res = r.get("time")
                            elif isinstance(r, (list, tuple)):
                                res = r[0] if r else None
                            else:
                                res = r
                        else:
                            res = None
                else:
                    raise RuntimeError(f"Unknown action: {action}")

                self.result.emit(res)
            except Exception as e:
                logger.exception("run_action 예외(action=%s): %s", action, e)
                self._emit_error_from_exc(e)
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
                self.finished.emit()

        # start background thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Request worker to stop. This will set the internal stop flag so
        long-running tasks can optionally check it and abort early.
        Note: For DB operations that block inside the DB driver, this cannot
        forcibly kill the operation; it only signals intent.
        """
        try:
            self._stop_event.set()
            self.status.emit("작업 중지 요청됨")
        except Exception:
            pass

# End of file