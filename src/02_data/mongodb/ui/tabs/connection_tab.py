# -*- coding: utf-8 -*-
"""MongoDB 연결 상태 탭"""
from __future__ import annotations
import importlib
import logging
import os
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "connection_tab.ui")

if _HAS_QT:
    class ConnectionTab(QWidget):
        """MongoDB 연결 상태 탭 - 호스트/포트/버전/상태 표시."""

        def __init__(self, parent=None, conn_params: Optional[Dict] = None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            # UI 파일이 있으면 로드, 없으면 간단한 레이아웃 생성
            if os.path.isfile(_UI_PATH):
                try:
                    uic.loadUi(_UI_PATH, self)
                except Exception as exc:
                    logger.warning("[ConnectionTab] UI 로드 실패: %s", exc)
                    self._build_fallback_ui()
            else:
                self._build_fallback_ui()

            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._update)
            self._timer.start()
            self._update()

        def _build_fallback_ui(self):
            """UI 파일 없을 때 기본 레이아웃 구성."""
            layout = QVBoxLayout(self)
            role_label = QLabel(
                "MongoDB는 메타데이터 저장소입니다.\n"
                "종목 정보, UI설정, 전략, AI모델 메타데이터를 저장합니다."
            )
            role_label.setWordWrap(True)
            layout.addWidget(role_label)

            grp = QGroupBox("연결 정보")
            grp_layout = QVBoxLayout(grp)

            def _make_row(key):
                lbl = QLabel(key + ":")
                val = QLabel("-")
                val.setObjectName(f"lbl_{key}")
                row = QHBoxLayout()
                row.addWidget(lbl)
                row.addWidget(val)
                row.addStretch()
                grp_layout.addLayout(row)
                return val

            self._lbl_host = _make_row("Host")
            self._lbl_port = _make_row("Port")
            self._lbl_status = _make_row("Status")
            self._lbl_version = _make_row("Version")
            layout.addWidget(grp)
            layout.addStretch()

        def _set_label(self, attr: str, text: str):
            """레이블 텍스트 안전 설정."""
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(text)

        def _update(self) -> None:
            """MongoDB 연결 정보를 조회하여 레이블 갱신."""
            params = self._conn_params
            host = params.get("host", "localhost")
            port = int(params.get("port", 27017))
            self._set_label("_lbl_host", host)
            self._set_label("_lbl_port", str(port))
            try:
                pymongo = importlib.import_module("pymongo")
                client = pymongo.MongoClient(
                    host=host, port=port, serverSelectionTimeoutMS=3000
                )
                info = client.server_info()
                version = info.get("version", "-")
                self._set_label("_lbl_status", "✅ 연결됨")
                self._set_label("_lbl_version", version)
                client.close()
            except Exception as exc:
                logger.debug("[ConnectionTab] MongoDB 연결 실패: %s", exc)
                self._set_label("_lbl_status", "❌ 연결 실패")
                self._set_label("_lbl_version", "-")

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
