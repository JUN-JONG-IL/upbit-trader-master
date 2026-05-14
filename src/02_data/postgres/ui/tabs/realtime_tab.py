# -*- coding: utf-8 -*-
"""PostgreSQL 실시간 통신 탭 - TPS/활성 쿼리 표시."""
from __future__ import annotations
import importlib
import logging
import os
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
        QHeaderView, QLabel, QHBoxLayout
    )
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "realtime_tab.ui")

if _HAS_QT:
    class RealtimeTab(QWidget):
        """PostgreSQL TPS 및 활성 쿼리 실시간 탭."""

        def __init__(self, parent=None, conn_params: Optional[Dict] = None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            if os.path.isfile(_UI_PATH):
                try:
                    uic.loadUi(_UI_PATH, self)
                except Exception as exc:
                    logger.warning("[PG RealtimeTab] UI 로드 실패: %s", exc)
                    self._build_fallback_ui()
            else:
                self._build_fallback_ui()

            self._timer = QTimer(self)
            self._timer.setInterval(3_000)
            self._timer.timeout.connect(self._update)
            self._timer.start()
            self._update()

        def _build_fallback_ui(self):
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("PostgreSQL 실시간 쿼리 활동"))
            self._tbl_queries = QTableWidget(0, 4)
            self._tbl_queries.setHorizontalHeaderLabels(["PID", "DB", "상태", "쿼리 (앞 80자)"])
            self._tbl_queries.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            self._tbl_queries.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self._tbl_queries)
            self._lbl_tps = QLabel("TPS: -")
            layout.addWidget(self._lbl_tps)

        def _update(self) -> None:
            tbl = getattr(self, "_tbl_queries", None)
            if tbl is None:
                return
            params = self._conn_params
            host = params.get("host", "localhost")
            db = params.get("database", "upbit_trades")
            user = params.get("user", "postgres")
            password = params.get("password", "")
            try:
                psycopg2 = importlib.import_module("psycopg2")
                conn = psycopg2.connect(
                    host=host, port=5433, database=db,
                    user=user, password=password, connect_timeout=3
                )
                cur = conn.cursor()
                cur.execute(
                    "SELECT pid, datname, state, LEFT(query, 80) "
                    "FROM pg_stat_activity "
                    "WHERE state != 'idle' AND pid != pg_backend_pid() "
                    "LIMIT 50"
                )
                rows = cur.fetchall()
                tbl.setRowCount(0)
                for row in rows:
                    r = tbl.rowCount()
                    tbl.insertRow(r)
                    for c, val in enumerate(row):
                        tbl.setItem(r, c, QTableWidgetItem(str(val) if val else "-"))
                cur.execute(
                    "SELECT sum(xact_commit + xact_rollback) FROM pg_stat_database"
                )
                res = cur.fetchone()
                tps_label = getattr(self, "_lbl_tps", None)
                if tps_label and res:
                    tps_label.setText(f"누적 트랜잭션: {res[0]:,}")
                cur.close()
                conn.close()
            except Exception as exc:
                logger.debug("[PG RealtimeTab] 조회 실패: %s", exc)

        def start_updates(self, interval_ms: int = 3_000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 3_000) -> None: pass
        def stop_updates(self) -> None: pass
