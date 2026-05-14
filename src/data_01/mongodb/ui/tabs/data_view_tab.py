# -*- coding: utf-8 -*-
"""MongoDB 저장 데이터 상세 조회 탭"""
from __future__ import annotations
import sys
import logging
from typing import Optional, Dict, List

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QSpinBox, QSizePolicy,
    )
    from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_DATA_BROWSER = None
try:
    from pathlib import Path as _Path
    _widget_dir = str(_Path(__file__).resolve().parents[4] / "ui" / "widgets")
    if _widget_dir not in sys.path:
        sys.path.insert(0, _widget_dir)
    from data_browser import DataBrowserWidget
    _DATA_BROWSER = DataBrowserWidget
except Exception:
    pass

logger = logging.getLogger(__name__)

_COLLECTION_PRESETS: List[str] = [
    "ohlcv",
    "symbols",
    "events",
    "orders",
    "trades",
    "ui_settings",
    "gap_queue",
    "performance_metrics",
    "ai_predictions",
]

if _HAS_QT:
    class _MongoWorker(QThread):
        finished = pyqtSignal(list, list)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, collection: str, limit: int):
            super().__init__()
            self._conn_params = conn_params
            self._collection = collection
            self._limit = limit

        def run(self):
            try:
                from pymongo import MongoClient  # type: ignore[import]
                p = self._conn_params
                uri = p.get("uri") or p.get("url") or ""
                if not uri:
                    host = p.get("host", "127.0.0.1") or "127.0.0.1"
                    port = int(p.get("port", 27017) or 27017)
                    uri = f"mongodb://{host}:{port}"
                db_name = p.get("database") or p.get("db") or "upbit_trader"
                client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                db = client[db_name]
                docs = list(db[self._collection].find({}, {"_id": 0}).limit(self._limit))
                client.close()
                if not docs:
                    self.finished.emit(["(결과 없음)"], [["데이터가 없습니다."]])
                    return
                # 모든 도큐먼트 키 합산
                headers = list(dict.fromkeys(k for d in docs for k in d.keys()))
                rows = [[str(d.get(h, "")) for h in headers] for d in docs]
                self.finished.emit(headers, rows)
            except ImportError:
                self.error.emit("pymongo 라이브러리가 설치되지 않았습니다. (pip install pymongo)")
            except Exception as exc:
                self.error.emit(str(exc)[:300])


    class DataViewTab(QWidget):
        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._worker = None
            self._build_ui()
            self._bind_signals()

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)
            banner = QLabel("🍃 MongoDB — 저장 도큐먼트 상세 조회")
            banner.setStyleSheet(
                "background:#14532D;color:white;padding:8px 12px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)
            ctrl = QHBoxLayout()
            ctrl.addWidget(QLabel("컬렉션:"))
            self._combo = QComboBox()
            self._combo.setEditable(True)
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._combo.addItems(_COLLECTION_PRESETS)
            ctrl.addWidget(self._combo)
            ctrl.addWidget(QLabel("최대:"))
            self._spin = QSpinBox()
            self._spin.setRange(10, 10000)
            self._spin.setValue(500)
            self._spin.setFixedWidth(80)
            ctrl.addWidget(self._spin)
            self._btn_load = QPushButton("🔄 조회")
            self._btn_load.setFixedWidth(80)
            ctrl.addWidget(self._btn_load)
            layout.addLayout(ctrl)
            if _DATA_BROWSER is not None:
                self._browser = _DATA_BROWSER()
            else:
                from PyQt5.QtWidgets import QTableWidget
                self._browser = QTableWidget()
            layout.addWidget(self._browser)
            self._status = QLabel("⬜ 컬렉션을 선택하고 [조회] 버튼을 누르세요.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)

        @pyqtSlot()
        def _load_data(self) -> None:
            if self._worker and self._worker.isRunning():
                return
            collection = self._combo.currentText().strip()
            if not collection:
                return
            limit = self._spin.value()
            self._status.setStyleSheet("color:#F59E0B;font-size:8pt;")
            self._status.setText(f"⏳ '{collection}' 조회 중...")
            self._btn_load.setEnabled(False)
            self._worker = _MongoWorker(self._conn_params, collection, limit)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        @pyqtSlot(list, list)
        def _on_finished(self, headers: list, rows: list) -> None:
            self._btn_load.setEnabled(True)
            if hasattr(self._browser, "set_data"):
                self._browser.set_data(headers, rows)
                self._status.setStyleSheet("color:#16A34A;font-size:8pt;")
                self._status.setText(f"✅ {len(rows):,}건 조회 완료 — 더블클릭: 행 상세 보기")
            else:
                self._status.setText(f"✅ {len(rows):,}건")

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._btn_load.setEnabled(True)
            self._status.setStyleSheet("color:#DC2626;font-size:8pt;")
            self._status.setText(f"🔴 오류: {msg[:200]}")

        def start_updates(self, interval_ms: int = 0) -> None:
            self._load_data()

        def stop_updates(self) -> None:
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)

        def closeEvent(self, event) -> None:
            self.stop_updates()
            super().closeEvent(event)

else:
    class DataViewTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass
