#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse 테이블 통계 개요 탭 위젯 (QThread Worker 패턴)

메인스레드 블로킹 없이 백그라운드에서 ClickHouse system.parts 쿼리를 실행합니다.
"""
from __future__ import annotations

import os
import logging
from typing import Optional, List, Tuple, Dict

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_FILE = os.path.join(os.path.dirname(__file__), "overview_tab.ui")

_STATS_SQL = (
    "SELECT table, "
    "sum(rows) AS rows, "
    "formatReadableSize(sum(data_compressed_bytes)) AS compressed, "
    "formatReadableSize(sum(data_uncompressed_bytes)) AS uncompressed, "
    "round(sum(data_compressed_bytes) / "
    "  greatest(sum(data_uncompressed_bytes), 1) * 100, 1) AS ratio "
    "FROM system.parts "
    "WHERE active = 1 "
    "GROUP BY table "
    "ORDER BY sum(rows) DESC"
)


def _get_ch_client(conn_params: dict):
    """ClickHouse 클라이언트를 반환합니다. 실패 시 None."""
    try:
        import clickhouse_connect  # type: ignore[import]
        host     = conn_params.get("host") or os.getenv("CLICKHOUSE_HOST", "localhost")
        port     = int(conn_params.get("port") or os.getenv("CLICKHOUSE_PORT", "8123"))
        user     = conn_params.get("user") or os.getenv("CLICKHOUSE_USER", "default")
        password = conn_params.get("password") or os.getenv("CLICKHOUSE_PASSWORD", "")
        database = conn_params.get("database") or os.getenv("CLICKHOUSE_DB", "upbit_trader")
        return clickhouse_connect.get_client(
            host=host, port=port, username=user,
            password=password, database=database, connect_timeout=5,
        )
    except Exception as exc:
        logger.debug("[CH OverviewTab] 연결 실패: %s", exc)
        return None


if _HAS_QT:
    class _StatsWorker(QThread):
        """백그라운드에서 ClickHouse system.parts 통계를 조회합니다."""
        data_ready = pyqtSignal(list)
        error      = pyqtSignal(str)

        def __init__(self, conn_params: dict, client=None):
            super().__init__()
            self._conn_params = conn_params
            self._client = client

        def run(self):
            try:
                client = self._client or _get_ch_client(self._conn_params)
                if client is None:
                    self.error.emit("ClickHouse 연결 실패")
                    return
                result = client.query(_STATS_SQL)
                self.data_ready.emit(result.result_rows)
            except Exception as exc:
                self.error.emit(str(exc)[:160])


class OverviewTab(QWidget if _HAS_QT else object):
    """ClickHouse 테이블 통계 개요를 표시하는 탭 위젯.

    QThread Worker를 사용하여 메인스레드 블로킹 없이 15초 주기로 갱신합니다.
    """

    def __init__(self, client=None, parent=None, conn_params=None):
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._client = client
        self._conn_params = conn_params or {}
        self._worker: Optional[_StatsWorker] = None
        self._timer = QTimer(self)
        self._timer.setInterval(15_000)   # 15초 주기 (렉 완화)
        self._timer.timeout.connect(self._start_refresh)

        try:
            uic.loadUi(_UI_FILE, self)
        except Exception as exc:
            logger.warning("[CH OverviewTab] UI 로드 실패: %s", exc)

        self._setup_table()

    def _setup_table(self):
        tbl = getattr(self, "table_stats", None)
        if tbl is None:
            return
        header = tbl.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        tbl.setEditTriggers(tbl.NoEditTriggers)

    def set_client(self, client):
        """ClickHouse 클라이언트를 교체하고 즉시 갱신합니다."""
        self._client = client
        self._start_refresh()

    def _start_refresh(self):
        """Worker가 실행 중이 아닐 때만 새 Worker를 시작합니다 (중복 갱신 방지)."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = _StatsWorker(self._conn_params, self._client)
        self._worker.data_ready.connect(self._populate_table)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _populate_table(self, rows):
        tbl = getattr(self, "table_stats", None)
        if tbl is None:
            return
        tbl.setRowCount(len(rows))
        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(row_idx, col_idx, item)

    def _on_error(self, msg: str):
        tbl = getattr(self, "table_stats", None)
        if tbl is not None:
            tbl.setRowCount(1)
            tbl.setItem(0, 0, QTableWidgetItem(f"⚠️ {msg}"))
        logger.warning("[CH OverviewTab] %s", msg)

    # ------------------------------------------------------------------
    # 생명 주기
    # ------------------------------------------------------------------

    def start_updates(self, interval_ms: int = 0) -> None:
        self._start_refresh()
        self._timer.start()

    def stop_updates(self) -> None:
        self._timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

    def closeEvent(self, event) -> None:
        self.stop_updates()
        super().closeEvent(event)
