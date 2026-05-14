# -*- coding: utf-8 -*-
"""Kafka 저장 데이터 상세 조회 탭 (토픽 메시지 브라우저)"""
from __future__ import annotations
import sys
import logging
from typing import Optional, Dict, List, Tuple

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

# 잘 알려진 토픽 프리셋
_TOPIC_PRESETS = [
    "market.ticks",
    "market.ohlcv.1m",
    "market.ohlcv.5m",
    "market.ohlcv.1h",
    "market.orderbook",
    "pipeline.events",
    "gap.fill.queue",
]

if _HAS_QT:
    class _KafkaWorker(QThread):
        finished = pyqtSignal(list, list)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, topic: str, limit: int):
            super().__init__()
            self._conn_params = conn_params
            self._topic = topic
            self._limit = limit

        def run(self):
            try:
                from kafka import KafkaConsumer  # type: ignore[import]
                import json as _json
                p = self._conn_params
                servers = p.get("bootstrap_servers") or p.get("brokers") or "localhost:9092"
                if isinstance(servers, str):
                    servers = [s.strip() for s in servers.split(",")]
                consumer = KafkaConsumer(
                    self._topic,
                    bootstrap_servers=servers,
                    auto_offset_reset="earliest",
                    consumer_timeout_ms=5000,
                    value_deserializer=lambda m: m,
                    group_id=None,
                )
                rows = []
                headers_set: set = set()
                for msg in consumer:
                    try:
                        raw = msg.value
                        if isinstance(raw, (bytes, bytearray)):
                            val = _json.loads(raw.decode("utf-8", errors="replace"))
                        else:
                            val = {"raw": str(raw)}
                        if isinstance(val, dict):
                            headers_set.update(val.keys())
                            val["offset"] = msg.offset
                            val["partition"] = msg.partition
                            val["timestamp"] = msg.timestamp
                            rows.append(val)
                        else:
                            rows.append({"value": str(val), "offset": msg.offset,
                                         "partition": msg.partition, "timestamp": msg.timestamp})
                    except Exception:
                        rows.append({"raw": str(msg.value)[:200], "offset": msg.offset,
                                     "partition": msg.partition, "timestamp": msg.timestamp})
                    if len(rows) >= self._limit:
                        break
                consumer.close()
                all_headers = list(dict.fromkeys(["offset", "partition", "timestamp"] + list(headers_set)))
                final_rows = []
                for row_dict in rows:
                    row_list = [row_dict.get(h, "") for h in all_headers]
                    final_rows.append(row_list)
                self.finished.emit(all_headers, final_rows)
            except ImportError:
                self.error.emit("kafka-python 라이브러리가 설치되지 않았습니다. (pip install kafka-python)")
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
            banner = QLabel("📨 Kafka — 저장 메시지 상세 조회")
            banner.setStyleSheet(
                "background:#1A56DB;color:white;padding:8px 12px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)
            ctrl = QHBoxLayout()
            ctrl.addWidget(QLabel("토픽:"))
            self._combo = QComboBox()
            self._combo.setEditable(True)
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._combo.addItems(_TOPIC_PRESETS)
            ctrl.addWidget(self._combo)
            ctrl.addWidget(QLabel("최대 건수:"))
            self._spin = QSpinBox()
            self._spin.setRange(10, 5000)
            self._spin.setValue(200)
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
            self._status = QLabel("⬜ 토픽을 선택하고 [조회] 버튼을 누르세요.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)

        @pyqtSlot()
        def _load_data(self) -> None:
            if self._worker and self._worker.isRunning():
                return
            topic = self._combo.currentText().strip()
            if not topic:
                return
            limit = self._spin.value()
            self._status.setStyleSheet("color:#F59E0B;font-size:8pt;")
            self._status.setText(f"⏳ '{topic}' 메시지 조회 중 (최대 {limit}건)...")
            self._btn_load.setEnabled(False)
            self._worker = _KafkaWorker(self._conn_params, topic, limit)
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
            pass  # Kafka는 자동 갱신 없음 (수동 조회)

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
