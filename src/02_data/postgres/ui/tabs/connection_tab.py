# -*- coding: utf-8 -*-
"""PostgreSQL 연결 상태 탭"""
from __future__ import annotations
import logging
import os
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton, QSizePolicy
    )
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "connection_tab.ui")

if _HAS_QT:
    class ConnectionTab(QWidget):
        """PostgreSQL 연결 상태 탭 - Primary/Replica 연결 확인."""

        def __init__(self, parent=None, conn_params: Optional[Dict] = None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            if os.path.isfile(_UI_PATH):
                try:
                    uic.loadUi(_UI_PATH, self)
                except Exception as exc:
                    logger.warning("[PG ConnectionTab] UI 로드 실패: %s", exc)
                    self._build_fallback_ui()
            else:
                self._build_fallback_ui()

            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._update)
            self._timer.start()
            self._update()

        def _build_fallback_ui(self):
            layout = QVBoxLayout(self)
            role_label = QLabel(
                "PostgreSQL은 Core Tier CQRS 이벤트 스토어입니다.\n"
                "Primary(쓰기전용 5433) + Replica(읽기전용 5434)"
            )
            role_label.setWordWrap(True)
            layout.addWidget(role_label)

            for name, attr_prefix in [("Primary (5433)", "primary"), ("Replica (5434)", "replica")]:
                grp = QGroupBox(name)
                grp_layout = QVBoxLayout(grp)

                def _row(key, prefix=attr_prefix):
                    lbl_key = QLabel(key + ":")
                    lbl_val = QLabel("-")
                    setattr(self, f"_lbl_{prefix}_{key.lower()}", lbl_val)
                    row = QHBoxLayout()
                    row.addWidget(lbl_key)
                    row.addWidget(lbl_val)
                    row.addStretch()
                    grp_layout.addLayout(row)

                _row("Host")
                _row("Port")
                _row("Status")
                _row("Version")
                layout.addWidget(grp)
            layout.addStretch()

        def _set_label(self, attr: str, text: str):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(text)

        def _check_pg(self, port: int, prefix: str):
            """지정 포트의 PostgreSQL 연결을 확인한다."""
            import importlib
            params = self._conn_params
            host = params.get("host", "localhost")
            db = params.get("database", "upbit_trades")
            user = params.get("user", "postgres")
            password = params.get("password", "")
            try:
                psycopg2 = importlib.import_module("psycopg2")
                conn = psycopg2.connect(
                    host=host, port=port, database=db,
                    user=user, password=password, connect_timeout=3
                )
                cur = conn.cursor()
                cur.execute("SELECT version()")
                row = cur.fetchone()
                version = row[0].split(" ")[1] if row else "-"
                cur.close()
                conn.close()
                self._set_label(f"_lbl_{prefix}_host", host)
                self._set_label(f"_lbl_{prefix}_port", str(port))
                self._set_label(f"_lbl_{prefix}_status", "✅ 연결됨")
                self._set_label(f"_lbl_{prefix}_version", version)
            except Exception as exc:
                logger.debug("[PG ConnectionTab] %s:%d 연결 실패: %s", host, port, exc)
                self._set_label(f"_lbl_{prefix}_host", host)
                self._set_label(f"_lbl_{prefix}_port", str(port))
                self._set_label(f"_lbl_{prefix}_status", "❌ 연결 실패")
                self._set_label(f"_lbl_{prefix}_version", "-")

        def _update(self) -> None:
            self._check_pg(5433, "primary")
            self._check_pg(5434, "replica")

        def start_updates(self, interval_ms: int = 10_000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

else:
    class ConnectionTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 10_000) -> None: pass
        def stop_updates(self) -> None: pass
