# -*- coding: utf-8 -*-
"""Redis 저장 데이터 상세 조회 탭 (키 브라우저)"""
from __future__ import annotations
import sys
import logging
from typing import Optional, Dict, List

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QSpinBox, QSizePolicy, QLineEdit,
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

try:
    from . import common as _common
except ImportError:
    try:
        import common as _common  # type: ignore[no-redef]
    except ImportError:
        _common = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_PATTERN_PRESETS: List[str] = [
    "candles:*",
    "ticker:*",
    "feature:*",
    "orderbook:*",
    "gap:*",
    "*",
]

if _HAS_QT:
    class _RedisKeyWorker(QThread):
        finished = pyqtSignal(list, list)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, pattern: str, limit: int):
            super().__init__()
            self._conn_params = conn_params
            self._pattern = pattern
            self._limit = limit

        def run(self):
            try:
                import redis as redis_mod  # type: ignore[import]
                p = self._conn_params
                host = p.get("host", "127.0.0.1") or "127.0.0.1"
                port = int(p.get("port", 6379) or 6379)
                pw   = p.get("password") or None
                db_n = int(p.get("db", 0) or 0)
                r = redis_mod.Redis(host=host, port=port, password=pw, db=db_n,
                                    socket_connect_timeout=5, decode_responses=False)
                headers = ["키", "타입", "TTL(초)", "값(앞200자)"]
                rows = []
                count = 0
                for key in r.scan_iter(match=self._pattern, count=500):
                    if count >= self._limit:
                        break
                    k = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)
                    try:
                        ktype = r.type(key).decode("utf-8", errors="replace")
                    except Exception:
                        ktype = "?"
                    try:
                        ttl_val = r.ttl(key)
                    except Exception:
                        ttl_val = -1
                    try:
                        if ktype == "string":
                            raw = r.get(key)
                            val = raw.decode("utf-8", errors="replace")[:200] if isinstance(raw, bytes) else str(raw)[:200]
                        elif ktype == "hash":
                            d = r.hgetall(key)
                            val = str({k2.decode(errors="replace"): v2.decode(errors="replace") for k2, v2 in list(d.items())[:5]})[:200]
                        elif ktype == "list":
                            items = r.lrange(key, 0, 4)
                            val = str([i.decode(errors="replace") for i in items])[:200]
                        elif ktype == "zset":
                            items = r.zrange(key, 0, 4, withscores=True)
                            val = str([(m.decode(errors="replace"), s) for m, s in items])[:200]
                        elif ktype == "set":
                            items = r.srandmember(key, 5)
                            val = str([i.decode(errors="replace") for i in items])[:200]
                        else:
                            val = f"[{ktype}]"
                    except Exception:
                        val = "조회 오류"
                    rows.append([k, ktype, str(ttl_val), val])
                    count += 1
                r.close()
                self.finished.emit(headers, rows)
            except ImportError:
                # redis-py 없으면 common 모듈 폴백
                try:
                    if _common is None:
                        raise RuntimeError("common 모듈 없음")
                    p = self._conn_params
                    host = p.get("host", "127.0.0.1") or "127.0.0.1"
                    port = int(p.get("port", 6379) or 6379)
                    pw   = p.get("password") or None
                    keys_list = _common.keys(host, port, pw, 5.0, self._pattern)[:self._limit]
                    headers = ["키"]
                    rows = [[k] for k in keys_list]
                    self.finished.emit(headers, rows)
                except Exception as exc2:
                    self.error.emit(str(exc2)[:300])
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
            banner = QLabel("🔴 Redis — 저장 키/값 상세 조회")
            banner.setStyleSheet(
                "background:#7F1D1D;color:white;padding:8px 12px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)
            ctrl = QHBoxLayout()
            ctrl.addWidget(QLabel("패턴:"))
            self._combo = QComboBox()
            self._combo.setEditable(True)
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._combo.addItems(_PATTERN_PRESETS)
            ctrl.addWidget(self._combo)
            ctrl.addWidget(QLabel("최대:"))
            self._spin = QSpinBox()
            self._spin.setRange(10, 5000)
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
            self._status = QLabel("⬜ 패턴을 선택하고 [조회] 버튼을 누르세요.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)

        @pyqtSlot()
        def _load_data(self) -> None:
            if self._worker and self._worker.isRunning():
                return
            pattern = self._combo.currentText().strip() or "*"
            limit = self._spin.value()
            self._status.setStyleSheet("color:#F59E0B;font-size:8pt;")
            self._status.setText(f"⏳ '{pattern}' 키 조회 중...")
            self._btn_load.setEnabled(False)
            self._worker = _RedisKeyWorker(self._conn_params, pattern, limit)
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
            pass  # Redis는 자동 갱신 없음 (수동 조회)

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
