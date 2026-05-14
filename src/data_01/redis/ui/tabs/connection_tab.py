# -*- coding: utf-8 -*-
"""Redis 연결 상태 탭"""
from __future__ import annotations
import os
import logging
import datetime
from typing import List, Tuple

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "connection_tab.ui")

try:
    from . import common as _common
except ImportError:
    try:
        import common as _common  # type: ignore[no-redef]
    except ImportError:
        _common = None  # type: ignore[assignment]

if _HAS_QT:
    class ConnectionTab(QWidget):
        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            # 최근 에러 기록 버퍼 (최대 10개)
            self._errors: List[Tuple[str, str, str]] = []
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[ConnectionTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(2000)
            self._timer.timeout.connect(self._update)
            self._connect_signals()
            self._timer.start()

        def _connect_signals(self) -> None:
            try:
                self.btnRefresh.clicked.connect(self._update)
            except AttributeError as exc:
                logger.debug("[ConnectionTab] 시그널 연결 실패: %s", exc)

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
            if _common is None:
                status_label = getattr(self, "labelStatus", None)
                if status_label:
                    status_label.setText("🔴 common 모듈 로드 실패")
                return
            host, port, password, timeout = self._get_redis_params()
            now = datetime.datetime.now().strftime("%H:%M:%S")

            # Redis INFO server/clients 조회
            server_info: dict = {}
            clients_info: dict = {}
            connected = False
            try:
                server_info = _common.info_section(host, port, password, timeout, "server")
                clients_info = _common.info_section(host, port, password, timeout, "clients")
                connected = bool(server_info)
            except Exception as exc:
                err_msg = str(exc)
                self._add_error(now, "ERROR", err_msg)
                logger.debug("[ConnectionTab] Redis 조회 실패: %s", exc)

            # 상태 표시
            status_label = getattr(self, "labelStatus", None)
            if status_label:
                if connected:
                    status_label.setText("🟢 상태: 연결됨")
                else:
                    status_label.setText("🔴 상태: 연결 끊김")

            host_label = getattr(self, "labelHost", None)
            if host_label:
                host_label.setText(f"호스트: {host}:{port}")

            db_label = getattr(self, "labelDB", None)
            if db_label:
                db_label.setText("데이터베이스: 0")

            ver_label = getattr(self, "labelVersion", None)
            if ver_label:
                ver = server_info.get("redis_version", "-")
                ver_label.setText(f"버전: {ver}")

            uptime_label = getattr(self, "labelUptime", None)
            if uptime_label:
                secs = int(server_info.get("uptime_in_seconds", 0) or 0)
                uptime_label.setText(f"업타임: {self._fmt_uptime(secs)}")

            conn_label = getattr(self, "labelConnections", None)
            if conn_label:
                cnt = clients_info.get("connected_clients", "-")
                conn_label.setText(f"활성 연결수: {cnt}")

            self._refresh_error_table()

        @staticmethod
        def _fmt_uptime(secs: int) -> str:
            """초를 일/시/분 포맷으로 변환."""
            if secs <= 0:
                return "-"
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins = rem // 60
            if days > 0:
                return f"{days}일 {hours}시간 {mins}분"
            if hours > 0:
                return f"{hours}시간 {mins}분"
            return f"{mins}분"

        def _add_error(self, ts: str, level: str, msg: str) -> None:
            self._errors.append((ts, level, msg[:200]))
            if len(self._errors) > 10:
                self._errors = self._errors[-10:]

        def _refresh_error_table(self) -> None:
            table = getattr(self, "tableErrors", None)
            if table is None:
                return
            table.setRowCount(len(self._errors))
            for row, (ts, level, msg) in enumerate(self._errors):
                table.setItem(row, 0, QTableWidgetItem(ts))
                table.setItem(row, 1, QTableWidgetItem(level))
                table.setItem(row, 2, QTableWidgetItem(msg))

else:
    class ConnectionTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 2000) -> None: pass
        def stop_updates(self) -> None: pass
