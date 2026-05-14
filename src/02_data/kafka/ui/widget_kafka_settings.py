#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 설정 위젯 모듈

KafkaSettingsDialog(메인 다이얼로그)와
KafkaBrokersTab(브로커 모니터링 탭)을 하나의 모듈로 통합합니다.

이전에 kafka/ 서브패키지(kafka/tab_brokers.py)에 있던
KafkaBrokersTab 클래스를 이 모듈로 이전하였습니다.
"""
from __future__ import annotations

import logging
import os as _os
from typing import Optional

# 메인 다이얼로그 re-export
from .kafka_settings_dialog import KafkaSettingsDialog  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PyQt5 임포트
# ---------------------------------------------------------------------------
try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import (
        QLabel,
        QSizePolicy,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    _PYQT5_AVAILABLE = True
except ImportError:
    _PYQT5_AVAILABLE = False

try:
    from kafka.admin import KafkaAdminClient  # type: ignore
    from kafka import KafkaConsumer  # type: ignore
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Kafka 연결 설정
# ---------------------------------------------------------------------------
_BOOTSTRAP_SERVERS = [
    s.strip()
    for s in _os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092,localhost:9093,localhost:9094"
    ).split(",")
    if s.strip()
]
_MAIN_TOPIC = _os.getenv("KAFKA_MAIN_TOPIC", "trade_events")
_PARTITION_COUNT = int(_os.getenv("KAFKA_PARTITION_COUNT", "30"))


# ---------------------------------------------------------------------------
# KafkaBrokersTab
# ---------------------------------------------------------------------------
if _PYQT5_AVAILABLE:
    class KafkaBrokersTab(QWidget):
        """Kafka 클러스터 모니터링 탭"""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._setup_ui()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh)
            self._timer.start(10_000)
            self.refresh()

        # ------------------------------------------------------------------
        # UI 구성
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            title = QLabel("<h2>📨 Kafka 클러스터 (Broker 3대)</h2>")
            title.setAlignment(Qt.AlignLeft)
            layout.addWidget(title)

            self._table_brokers = QTableWidget(0, 5)
            self._table_brokers.setHorizontalHeaderLabels(
                ["Broker", "상태", "Leader 수", "처리량/초", "디스크 사용량"]
            )
            self._table_brokers.horizontalHeader().setStretchLastSection(True)
            self._table_brokers.setMinimumHeight(160)
            self._table_brokers.setMaximumHeight(200)
            layout.addWidget(self._table_brokers)

            topic_title = QLabel(
                f"<h3>📬 Topic: {_MAIN_TOPIC} (Partition {_PARTITION_COUNT})</h3>"
            )
            layout.addWidget(topic_title)

            self._table_partitions = QTableWidget(0, 4)
            self._table_partitions.setHorizontalHeaderLabels(
                ["Partition", "Leader", "ISR", "Lag"]
            )
            self._table_partitions.horizontalHeader().setStretchLastSection(True)
            self._table_partitions.setMinimumHeight(300)
            self._table_partitions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._table_partitions)

        # ------------------------------------------------------------------
        # 상태 갱신
        # ------------------------------------------------------------------

        def refresh(self) -> None:
            if not _KAFKA_AVAILABLE:
                self._show_unavailable()
                return
            try:
                admin = KafkaAdminClient(
                    bootstrap_servers=_BOOTSTRAP_SERVERS,
                    request_timeout_ms=3000,
                )

                cluster_meta = admin.describe_cluster()
                brokers = cluster_meta.get("brokers", [])

                self._table_brokers.setRowCount(len(brokers))
                for i, broker in enumerate(brokers):
                    node_id = broker.get("node_id", i + 1)
                    self._table_brokers.setItem(i, 0, _item(f"Broker-{node_id}"))
                    self._table_brokers.setItem(i, 1, _item("🟢 UP"))
                    self._table_brokers.setItem(i, 2, _item("-"))
                    self._table_brokers.setItem(i, 3, _item("-"))
                    self._table_brokers.setItem(i, 4, _item("-"))

                try:
                    topic_meta = admin.describe_topics([_MAIN_TOPIC])
                    partitions = topic_meta[0].get("partitions", []) if topic_meta else []
                    self._table_partitions.setRowCount(len(partitions))
                    for p in partitions:
                        pid = p.get("partition", 0)
                        leader = p.get("leader", -1)
                        isr = p.get("isr", [])
                        self._table_partitions.setItem(pid, 0, _item(str(pid)))
                        self._table_partitions.setItem(pid, 1, _item(f"Broker-{leader}"))
                        self._table_partitions.setItem(pid, 2, _item(str(len(isr))))
                        self._table_partitions.setItem(pid, 3, _item("0"))
                except Exception as exc:
                    logger.debug("Topic 조회 실패: %s", exc)

                admin.close()

            except Exception as exc:
                logger.warning("Kafka 연결 실패: %s", exc)
                self._table_brokers.setRowCount(1)
                self._table_brokers.setItem(0, 0, _item(f"연결 실패: {exc}"))
                for col in range(1, 5):
                    self._table_brokers.setItem(0, col, _item("-"))

        def _show_unavailable(self) -> None:
            self._table_brokers.setRowCount(1)
            self._table_brokers.setItem(0, 0, _item("kafka-python 패키지 미설치"))
            for col in range(1, 5):
                self._table_brokers.setItem(0, col, _item("-"))

else:
    class KafkaBrokersTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 빈 클래스"""
        def __init__(self, parent=None) -> None:
            logger.warning("[KafkaBrokersTab] PyQt5 미설치 - 탭 생성 불가")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _item(text: str) -> "QTableWidgetItem":
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


__all__ = ["KafkaSettingsDialog", "KafkaBrokersTab"]
