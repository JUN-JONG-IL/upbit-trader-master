# -*- coding: utf-8 -*-
"""ClickHouse 실시간 통신 탭"""
from __future__ import annotations
import os
import logging

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "realtime_tab.ui")

if _HAS_QT:
    class RealtimeTab(QWidget):
        """ClickHouse 실시간 쿼리 로그 탭 - system.query_log 기반."""

        def __init__(self, parent=None, conn_params=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[CH RealtimeTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(2000)
            self._timer.timeout.connect(self._update)

        def start_updates(self, interval_ms: int = 2000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update(self) -> None:
            """system.query_log에서 최근 쿼리를 조회하여 표시한다."""
            params = self._conn_params
            host = params.get("host", "localhost")
            port = int(params.get("port", 8123))
            try:
                import urllib.request
                import urllib.parse
                sql = (
                    "SELECT query_start_time, query_duration_ms, query "
                    "FROM system.query_log "
                    "WHERE type = 'QueryFinish' "
                    "ORDER BY query_start_time DESC LIMIT 20"
                )
                url = f"http://{host}:{port}/?query={urllib.parse.quote(sql)}&default_format=TabSeparated"
                with urllib.request.urlopen(url, timeout=3) as resp:
                    data = resp.read().decode()
                tbl = getattr(self, "table_query_log", None)
                if tbl is None:
                    return
                tbl.setRowCount(0)
                from PyQt5.QtWidgets import QTableWidgetItem
                for line in data.strip().splitlines():
                    parts = line.split("\t", 2)
                    if len(parts) < 3:
                        continue
                    r = tbl.rowCount()
                    tbl.insertRow(r)
                    for c, val in enumerate(parts):
                        tbl.setItem(r, c, QTableWidgetItem(val[:100]))
            except Exception as exc:
                logger.debug("[CH RealtimeTab] 조회 실패: %s", exc)

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 2000) -> None: pass
        def stop_updates(self) -> None: pass
