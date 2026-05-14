# -*- coding: utf-8 -*-
"""PostgreSQL 저장 데이터 상세 조회 탭"""
from __future__ import annotations
import sys
import logging
from typing import Optional, Dict, List, Tuple

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QSizePolicy,
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

_PRESETS: List[Tuple[str, str]] = [
    ("이벤트 스토어 — 최신 1,000행", "SELECT * FROM events ORDER BY created_at DESC LIMIT 1000"),
    ("거래 원장 — 최신 1,000행", "SELECT * FROM trades ORDER BY executed_at DESC LIMIT 1000"),
    ("주문 기록 — 최신 1,000행", "SELECT * FROM orders ORDER BY created_at DESC LIMIT 1000"),
    ("감사 로그 — 최신 1,000행", "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 1000"),
    ("테이블 목록", "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"),
    ("테이블 크기", "SELECT relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS size, n_live_tup AS rows FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC"),
    ("활성 쿼리", "SELECT pid, now() - query_start AS duration, query, state FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC"),
]

if _HAS_QT:
    class _PGQueryWorker(QThread):
        finished = pyqtSignal(list, list)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, sql: str):
            super().__init__()
            self._conn_params = conn_params
            self._sql = sql

        def run(self):
            try:
                import psycopg2
                p = self._conn_params
                host = p.get("host", "127.0.0.1") or "127.0.0.1"
                if str(host).lower() in ("localhost", ""):
                    host = "127.0.0.1"
                port = int(p.get("port", 5432) or 5432)
                db   = p.get("database") or p.get("db") or p.get("dbname") or "postgres"
                user = p.get("user", "postgres") or "postgres"
                pw   = p.get("password") or p.get("pass") or ""
                conn = psycopg2.connect(host=host, port=port, database=db,
                                        user=user, password=pw, connect_timeout=5)
                try:
                    with conn.cursor() as cur:
                        cur.execute(self._sql)
                        headers = [d[0] for d in (cur.description or [])]
                        rows = cur.fetchall()
                    self.finished.emit(headers, [list(r) for r in rows])
                finally:
                    conn.close()
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
            banner = QLabel("🐘 PostgreSQL — 저장 데이터 상세 조회")
            banner.setStyleSheet(
                "background:#1E3A5F;color:white;padding:8px 12px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)
            ctrl = QHBoxLayout()
            ctrl.addWidget(QLabel("프리셋:"))
            self._combo = QComboBox()
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for label, _ in _PRESETS:
                self._combo.addItem(label)
            ctrl.addWidget(self._combo)
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
            self._status = QLabel("⬜ 프리셋을 선택하고 [조회] 버튼을 누르세요.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)

        @pyqtSlot()
        def _load_data(self) -> None:
            if self._worker and self._worker.isRunning():
                return
            idx = self._combo.currentIndex()
            if idx < 0 or idx >= len(_PRESETS):
                return
            _, sql = _PRESETS[idx]
            self._status.setStyleSheet("color:#F59E0B;font-size:8pt;")
            self._status.setText("⏳ 조회 중...")
            self._btn_load.setEnabled(False)
            self._worker = _PGQueryWorker(self._conn_params, sql)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        @pyqtSlot(list, list)
        def _on_finished(self, headers: list, rows: list) -> None:
            self._btn_load.setEnabled(True)
            if hasattr(self._browser, "set_data"):
                self._browser.set_data(headers, rows)
                self._status.setStyleSheet("color:#16A34A;font-size:8pt;")
                self._status.setText(f"✅ {len(rows):,}행 조회 완료 — 더블클릭: 행 상세 보기")
            else:
                self._status.setText(f"✅ {len(rows):,}행")

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
