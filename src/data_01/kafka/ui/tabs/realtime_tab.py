# -*- coding: utf-8 -*-
"""Kafka 실시간 통신 탭"""
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
        """실시간 메시지 흐름 탭 (메시지 수신/전송, 토픽/파티션/오프셋 로그)."""

        _MAX_ROWS = 100

        def __init__(self, parent=None, conn_params=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[RealtimeTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(2_000)
            self._timer.timeout.connect(self._update)
            try:
                self.btnClear.clicked.connect(self._clear_log)
            except AttributeError as exc:
                logger.debug("[RealtimeTab] 시그널 연결 실패: %s", exc)

        def start_updates(self, interval_ms: int = 2_000) -> None:
            self._timer.setInterval(max(500, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _clear_log(self) -> None:
            try:
                self.table_msg_log.setRowCount(0)
            except AttributeError:
                pass

        def _update(self) -> None:
            """Kafka 토픽 목록과 오프셋 정보를 조회하여 테이블에 표시한다."""
            tbl = getattr(self, "table_msg_log", None)
            if tbl is None:
                return
            params = self._conn_params
            host = params.get("host", "localhost")
            port = int(params.get("port", 9092))
            bootstrap = f"{host}:{port}"
            try:
                import importlib
                kafka_consumer = importlib.import_module("kafka")
                consumer = kafka_consumer.KafkaConsumer(
                    bootstrap_servers=bootstrap,
                    request_timeout_ms=3000,
                    consumer_timeout_ms=1000,
                )
                topics = list(consumer.topics())[:self._MAX_ROWS]
                tbl.setRowCount(0)
                for topic in topics:
                    partitions = consumer.partitions_for_topic(topic) or set()
                    r = tbl.rowCount()
                    tbl.insertRow(r)
                    from PyQt5.QtWidgets import QTableWidgetItem
                    tbl.setItem(r, 0, QTableWidgetItem(topic))
                    tbl.setItem(r, 1, QTableWidgetItem(str(len(partitions))))
                consumer.close()
            except Exception as exc:
                logger.debug("[Kafka RealtimeTab] 조회 실패: %s", exc)

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 1_000) -> None: pass
        def stop_updates(self) -> None: pass
