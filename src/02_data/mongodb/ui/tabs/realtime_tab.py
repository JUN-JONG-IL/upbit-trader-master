# -*- coding: utf-8 -*-
"""MongoDB 실시간 통신 탭 - 최근 oplog/작업 표시."""
from __future__ import annotations
import importlib
import logging
import os
from datetime import datetime
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
        QHeaderView, QLabel, QPushButton, QHBoxLayout
    )
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "realtime_tab.ui")
_MAX_ROWS = 50

if _HAS_QT:
    class RealtimeTab(QWidget):
        """MongoDB 최근 작업 실시간 표시 탭."""

        def __init__(self, parent=None, conn_params: Optional[Dict] = None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            if os.path.isfile(_UI_PATH):
                try:
                    uic.loadUi(_UI_PATH, self)
                except Exception as exc:
                    logger.warning("[RealtimeTab] UI 로드 실패: %s", exc)
                    self._build_fallback_ui()
            else:
                self._build_fallback_ui()

            self._timer = QTimer(self)
            self._timer.setInterval(5_000)
            self._timer.timeout.connect(self._update)
            self._timer.start()
            self._update()

        def _build_fallback_ui(self):
            """폴백 UI 구성."""
            layout = QVBoxLayout(self)
            hl = QHBoxLayout()
            hl.addWidget(QLabel("MongoDB 최근 작업"))
            btn_clear = QPushButton("지우기")
            btn_clear.clicked.connect(self._clear)
            hl.addWidget(btn_clear)
            hl.addStretch()
            layout.addLayout(hl)
            self._table = QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(["시각", "DB.컬렉션", "작업"])
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self._table)

        def _clear(self):
            tbl = getattr(self, "_table", None)
            if tbl:
                tbl.setRowCount(0)

        def _update(self) -> None:
            """MongoDB 서버 상태에서 최근 작업 정보를 조회."""
            tbl = getattr(self, "_table", None)
            if tbl is None:
                return
            params = self._conn_params
            host = params.get("host", "localhost")
            port = int(params.get("port", 27017))
            try:
                pymongo = importlib.import_module("pymongo")
                client = pymongo.MongoClient(
                    host=host, port=port, serverSelectionTimeoutMS=3000
                )
                result = client.admin.command("currentOp", {"$all": True})
                ops = result.get("inprog", [])[:_MAX_ROWS]
                tbl.setRowCount(0)
                for op in ops:
                    row = tbl.rowCount()
                    tbl.insertRow(row)
                    ts = datetime.now().strftime("%H:%M:%S")
                    ns = op.get("ns", "-")
                    op_type = op.get("op", "-")
                    tbl.setItem(row, 0, QTableWidgetItem(ts))
                    tbl.setItem(row, 1, QTableWidgetItem(ns))
                    tbl.setItem(row, 2, QTableWidgetItem(op_type))
                client.close()
            except Exception as exc:
                logger.debug("[RealtimeTab] MongoDB 조회 실패: %s", exc)

        def start_updates(self, interval_ms: int = 5_000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 5_000) -> None: pass
        def stop_updates(self) -> None: pass
