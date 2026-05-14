# -*- coding: utf-8 -*-
"""Redis 실시간 통신 탭"""
from __future__ import annotations
import os
import logging
import datetime
import time

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "realtime_tab.ui")

if _HAS_QT:
    class RealtimeTab(QWidget):
        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            # 명령 로그 버퍼 (최대 50개)
            self._cmd_log = []
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[RealtimeTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(2000)
            self._timer.timeout.connect(self._update)
            self._connect_signals()
            self._timer.start()

        def _connect_signals(self) -> None:
            btn_clear = getattr(self, "btnClear", None)
            if btn_clear:
                try:
                    btn_clear.clicked.connect(self._clear_log)
                except Exception:
                    pass

        def start_updates(self, interval_ms: int = 2000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _get_redis_params(self):
            p = self._conn_params
            return (
                p.get("host", "localhost"),
                int(p.get("port", 58530)),
                p.get("password", None),
                3.0,
            )

        def _update(self) -> None:
            from . import common
            host, port, password, timeout = self._get_redis_params()
            now = datetime.datetime.now().strftime("%H:%M:%S")

            # PING으로 지연 측정 + INFO stats 조회
            t0 = time.monotonic()
            stats_info: dict = {}
            clients_info: dict = {}
            result_str = "OK"
            try:
                stats_info = common.info_section(host, port, password, timeout, "stats")
                clients_info = common.info_section(host, port, password, timeout, "clients")
            except Exception as exc:
                result_str = f"실패: {exc}"
                logger.debug("[RealtimeTab] 조회 실패: %s", exc)

            elapsed_ms = int((time.monotonic() - t0) * 1000)

            # 명령 로그에 추가
            self._cmd_log.append((now, "INFO stats", result_str, str(elapsed_ms)))
            if len(self._cmd_log) > 50:
                self._cmd_log = self._cmd_log[-50:]

            # OPS/s 레이블 업데이트
            ops_label = getattr(self, "label_ops_per_sec", None)
            if ops_label:
                ops = stats_info.get("instantaneous_ops_per_sec", "-")
                ops_label.setText(f"OPS/s: {ops}")

            # 연결 클라이언트 레이블 업데이트
            clients_label = getattr(self, "label_connected_clients", None)
            if clients_label:
                cnt = clients_info.get("connected_clients", "-")
                clients_label.setText(f"연결 클라이언트: {cnt}")

            self._refresh_cmd_table()

        def _clear_log(self) -> None:
            self._cmd_log.clear()
            self._refresh_cmd_table()

        def _refresh_cmd_table(self) -> None:
            table = getattr(self, "table_cmd_log", None)
            if table is None:
                return
            table.setRowCount(len(self._cmd_log))
            for row, (ts, cmd, result, delay) in enumerate(self._cmd_log):
                table.setItem(row, 0, QTableWidgetItem(ts))
                table.setItem(row, 1, QTableWidgetItem(cmd))
                table.setItem(row, 2, QTableWidgetItem(result))
                table.setItem(row, 3, QTableWidgetItem(delay))

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 2000) -> None: pass
        def stop_updates(self) -> None: pass
