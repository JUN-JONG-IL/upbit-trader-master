# -*- coding: utf-8 -*-
"""Kafka 연결 상태 탭"""
from __future__ import annotations
import logging
import os
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QSizePolicy
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
        """Kafka 브로커 연결 상태 탭."""

        def __init__(self, parent=None, conn_params: Optional[Dict] = None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            if os.path.isfile(_UI_PATH):
                try:
                    uic.loadUi(_UI_PATH, self)
                except Exception as exc:
                    logger.warning("[Kafka ConnectionTab] UI 로드 실패: %s", exc)
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
                "Kafka는 실시간 이벤트 스트리밍 브로커입니다.\n"
                "가격 이벤트, 주문 이벤트를 토픽으로 처리합니다."
            )
            role_label.setWordWrap(True)
            layout.addWidget(role_label)

            grp = QGroupBox("브로커 연결 정보")
            grp_layout = QVBoxLayout(grp)

            def _make_row(key):
                lbl = QLabel(key + ":")
                val = QLabel("-")
                setattr(self, f"_lbl_{key.lower()}", val)
                row = QHBoxLayout()
                row.addWidget(lbl)
                row.addWidget(val)
                row.addStretch()
                grp_layout.addLayout(row)
                return val

            self._lbl_host = _make_row("Host")
            self._lbl_port = _make_row("Port")
            self._lbl_status = _make_row("Status")
            self._lbl_brokers = _make_row("Brokers")
            layout.addWidget(grp)
            layout.addStretch()

        def _set_label(self, attr: str, text: str):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(text)

        def _update(self) -> None:
            """Kafka AdminClient로 브로커 목록을 조회한다."""
            params = self._conn_params
            host = params.get("host", "localhost")
            port = int(params.get("port", 9092))
            bootstrap = f"{host}:{port}"
            self._set_label("_lbl_host", host)
            self._set_label("_lbl_port", str(port))
            try:
                import importlib
                kafka_admin = importlib.import_module("kafka.admin")
                admin = kafka_admin.KafkaAdminClient(
                    bootstrap_servers=bootstrap,
                    request_timeout_ms=3000,
                )
                brokers = admin.describe_cluster().get("brokers", [])
                self._set_label("_lbl_status", "✅ 연결됨")
                self._set_label("_lbl_brokers", str(len(brokers)))
                admin.close()
            except Exception as exc:
                logger.debug("[Kafka ConnectionTab] 연결 실패: %s", exc)
                self._set_label("_lbl_status", "❌ 연결 실패")
                self._set_label("_lbl_brokers", "-")

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
