#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Primary/Replica 상태 개요 탭 모듈 (QThread Worker 패턴)

PostgreSQL 기본 상태(연결 수, 업타임, 복제 지연 등)를
Primary/Replica 테이블로 시각화한다. 메인스레드 블로킹 없이 동작.
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer, QThread, pyqtSignal
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_STAT_SQL = (
    "SELECT datname, numbackends, xact_commit, xact_rollback, "
    "blks_hit, blks_read "
    "FROM pg_stat_database WHERE datname = current_database()"
)
_STAT_LABELS = ["DB", "연결수", "커밋", "롤백", "캐시히트", "디스크읽기"]


def _pg_connect(conn_params: dict, port_override: Optional[int] = None):
    """psycopg2 연결 반환. 실패 시 None."""
    try:
        import psycopg2  # type: ignore[import]
        import os as _os
        return psycopg2.connect(
            host=conn_params.get("host") or _os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=port_override or int(conn_params.get("port") or _os.getenv("POSTGRES_PORT", "5432")),
            database=conn_params.get("database") or _os.getenv("POSTGRES_DB", "upbit_trader"),
            user=conn_params.get("user") or _os.getenv("POSTGRES_USER", "admin"),
            password=conn_params.get("password") or _os.getenv("POSTGRES_PASSWORD", ""),
            connect_timeout=3,
        )
    except Exception as exc:
        logger.debug("PG 연결 실패 (port=%s): %s", port_override, exc)
        return None


if _HAS_QT:
    class _PgStatWorker(QThread):
        """백그라운드에서 pg_stat_database를 조회합니다."""
        data_ready = pyqtSignal(list, str)   # (rows, role)  role = "primary" | "replica"
        error      = pyqtSignal(str, str)    # (msg, role)

        def __init__(self, conn_params: dict, role: str, port_override: Optional[int] = None):
            super().__init__()
            self._conn_params  = conn_params
            self._role         = role
            self._port_override = port_override

        def run(self):
            conn = _pg_connect(self._conn_params, self._port_override)
            if conn is None:
                self.error.emit("연결 실패", self._role)
                return
            try:
                cur = conn.cursor()
                cur.execute(_STAT_SQL)
                rows = cur.fetchall()
                cur.close()
                self.data_ready.emit(rows, self._role)
            except Exception as exc:
                self.error.emit(str(exc)[:120], self._role)
            finally:
                conn.close()


class OverviewTab(QWidget if _HAS_QT else object):
    """Primary/Replica 상태 개요 탭.

    QThread Worker를 사용하여 메인스레드 블로킹 없이 15초 주기로 갱신한다.
    """

    _POLL_INTERVAL_MS: int = 15_000   # 렉 완화: 5초 → 15초

    def __init__(self, parent=None, conn_params: Optional[Dict] = None):
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._conn_params: Dict = conn_params or {}
        self._worker_primary: Optional[_PgStatWorker] = None
        self._worker_replica: Optional[_PgStatWorker] = None

        ui_path = os.path.join(os.path.dirname(__file__), "overview_tab.ui")
        try:
            uic.loadUi(ui_path, self)
        except Exception as exc:
            logger.warning("[PG OverviewTab] UI 로드 실패: %s", exc)

        self._setup_tables()
        self._timer = QTimer(self)
        self._timer.setInterval(self._POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._start_refresh)

    def _setup_tables(self) -> None:
        for attr in ("table_primary", "table_replica"):
            table = getattr(self, attr, None)
            if table is None:
                continue
            header = table.horizontalHeader()
            header.setStretchLastSection(True)
            table.setEditTriggers(table.NoEditTriggers)
            table.setSelectionBehavior(table.SelectRows)

    def _start_refresh(self) -> None:
        """두 Worker가 실행 중이 아닐 때만 새 Worker를 시작합니다 (중복 갱신 방지)."""
        if not (self._worker_primary and self._worker_primary.isRunning()):
            # Primary: conn_params에서 port 사용 (기본 5432)
            self._worker_primary = _PgStatWorker(self._conn_params, "primary")
            self._worker_primary.data_ready.connect(self._on_data_ready)
            self._worker_primary.error.connect(self._on_error)
            self._worker_primary.start()

        if not (self._worker_replica and self._worker_replica.isRunning()):
            # Replica: port 5433으로 시도 (없으면 에러 무시)
            replica_params = dict(self._conn_params)
            try:
                replica_port = int(
                    replica_params.get("replica_port")
                    or os.getenv("POSTGRES_REPLICA_PORT", "5433")
                )
            except (ValueError, TypeError):
                replica_port = 5433
            self._worker_replica = _PgStatWorker(replica_params, "replica", replica_port)
            self._worker_replica.data_ready.connect(self._on_data_ready)
            self._worker_replica.error.connect(self._on_error)
            self._worker_replica.start()

    def _on_data_ready(self, rows: List[Tuple], role: str) -> None:
        attr = "table_primary" if role == "primary" else "table_replica"
        tbl = getattr(self, attr, None)
        if tbl is None:
            return
        tbl.setRowCount(0)
        if rows:
            tbl.setColumnCount(len(_STAT_LABELS))
            tbl.setHorizontalHeaderLabels(_STAT_LABELS)
            for row in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                for c, val in enumerate(row):
                    tbl.setItem(r, c, QTableWidgetItem(str(val) if val is not None else "-"))

    def _on_error(self, msg: str, role: str) -> None:
        attr = "table_primary" if role == "primary" else "table_replica"
        tbl = getattr(self, attr, None)
        if tbl is not None:
            tbl.setRowCount(1)
            tbl.setColumnCount(1)
            tbl.setHorizontalHeaderLabels(["상태"])
            tbl.setItem(0, 0, QTableWidgetItem(f"⚠️ {msg}"))
        logger.debug("[PG OverviewTab] %s 조회 실패: %s", role, msg)

    # ------------------------------------------------------------------
    # 생명 주기
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """외부에서 직접 갱신 트리거 (인터페이스 호환)."""
        self._start_refresh()

    def start_updates(self, interval_ms: int = 0) -> None:
        self._start_refresh()
        self._timer.start()

    def stop_updates(self) -> None:
        self._timer.stop()
        for worker in (self._worker_primary, self._worker_replica):
            if worker and worker.isRunning():
                worker.quit()
                worker.wait(2000)

    def closeEvent(self, event) -> None:
        self.stop_updates()
        super().closeEvent(event)
