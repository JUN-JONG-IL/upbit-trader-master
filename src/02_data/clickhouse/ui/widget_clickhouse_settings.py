#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClickHouse 설정 위젯 모듈

ClickHouseSettingsDialog(메인 다이얼로그)와
ClickHouseShardsTab(샤드 모니터링 탭)을 하나의 모듈로 통합합니다.

이전에 clickhouse/ 서브패키지(clickhouse/tab_shards.py)에 있던
ClickHouseShardsTab 클래스를 이 모듈로 이전하였습니다.
"""
from __future__ import annotations

import logging
import os as _os
from typing import Optional

# 메인 다이얼로그 re-export
from .clickhouse_settings_dialog import ClickHouseSettingsDialog  # noqa: F401

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
    from clickhouse_driver import Client as ClickHouseClient  # type: ignore
    _CH_AVAILABLE = True
except ImportError:
    _CH_AVAILABLE = False

# ---------------------------------------------------------------------------
# ClickHouse 연결 설정
# ---------------------------------------------------------------------------
_CH_USER     = _os.getenv("CLICKHOUSE_USER", "admin")
_CH_PASSWORD = _os.getenv("CLICKHOUSE_PASSWORD", "")

# Shard 구성: (shard_no, replica_name, host, port)
_SHARDS = [
    (1, "shard-1-replica-1", "localhost", 9000),
    (1, "shard-1-replica-2", "localhost", 9001),
    (2, "shard-2-replica-1", "localhost", 9002),
    (2, "shard-2-replica-2", "localhost", 9003),
    (3, "shard-3-replica-1", "localhost", 9004),
    (3, "shard-3-replica-2", "localhost", 9005),
]


# ---------------------------------------------------------------------------
# ClickHouseShardsTab
# ---------------------------------------------------------------------------
if _PYQT5_AVAILABLE:
    class ClickHouseShardsTab(QWidget):
        """ClickHouse 클러스터 모니터링 탭"""

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

            title = QLabel("<h2>⚡ ClickHouse 클러스터 (Shard 3 × Replica 2)</h2>")
            title.setAlignment(Qt.AlignLeft)
            layout.addWidget(title)

            self._table_shards = QTableWidget(len(_SHARDS), 6)
            self._table_shards.setHorizontalHeaderLabels(
                ["Shard", "Replica", "상태", "행 수", "디스크 크기", "응답시간"]
            )
            self._table_shards.horizontalHeader().setStretchLastSection(True)
            self._table_shards.setMinimumHeight(300)
            self._table_shards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._table_shards)

            dist_title = QLabel("<h3>📋 Distributed Table 현황</h3>")
            layout.addWidget(dist_title)

            self._table_dist = QTableWidget(0, 3)
            self._table_dist.setHorizontalHeaderLabels(
                ["테이블", "총 행 수", "총 크기"]
            )
            self._table_dist.setMinimumHeight(100)
            self._table_dist.setMaximumHeight(140)
            layout.addWidget(self._table_dist)

        # ------------------------------------------------------------------
        # 상태 갱신
        # ------------------------------------------------------------------

        def refresh(self) -> None:
            self._table_shards.setRowCount(len(_SHARDS))

            for row, (shard_no, replica_name, host, port) in enumerate(_SHARDS):
                self._table_shards.setItem(row, 0, _item(f"Shard-{shard_no}"))
                self._table_shards.setItem(row, 1, _item(replica_name))

                if not _CH_AVAILABLE:
                    self._table_shards.setItem(row, 2, _item("clickhouse-driver 미설치"))
                    for col in range(3, 6):
                        self._table_shards.setItem(row, col, _item("-"))
                    continue

                try:
                    client = ClickHouseClient(
                        host=host,
                        port=port,
                        user=_CH_USER,
                        password=_CH_PASSWORD,
                        connect_timeout=2,
                        send_receive_timeout=3,
                    )

                    try:
                        rows_result = client.execute("SELECT count() FROM trade_events")
                        row_count = rows_result[0][0] if rows_result else 0
                    except Exception:
                        row_count = None

                    try:
                        size_result = client.execute(
                            "SELECT formatReadableSize(sum(bytes_on_disk)) "
                            "FROM system.parts WHERE active"
                        )
                        disk_size = size_result[0][0] if size_result else "N/A"
                    except Exception:
                        disk_size = "N/A"

                    self._table_shards.setItem(row, 2, _item("🟢 UP"))
                    self._table_shards.setItem(
                        row, 3, _item(f"{row_count:,}" if row_count is not None else "N/A")
                    )
                    self._table_shards.setItem(row, 4, _item(disk_size))
                    self._table_shards.setItem(row, 5, _item("< 10ms"))

                except Exception as exc:
                    self._table_shards.setItem(row, 2, _item("🔴 DOWN"))
                    self._table_shards.setItem(row, 3, _item("-"))
                    self._table_shards.setItem(row, 4, _item("-"))
                    self._table_shards.setItem(row, 5, _item(str(exc)[:40]))
                    logger.debug("ClickHouse %s:%s 연결 실패: %s", host, port, exc)

            self._table_dist.setRowCount(1)
            self._table_dist.setItem(0, 0, _item("trade_events_distributed"))
            self._table_dist.setItem(0, 1, _item("-"))
            self._table_dist.setItem(0, 2, _item("-"))

else:
    class ClickHouseShardsTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 빈 클래스"""
        def __init__(self, parent=None) -> None:
            logger.warning("[ClickHouseShardsTab] PyQt5 미설치 - 탭 생성 불가")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _item(text: str) -> "QTableWidgetItem":
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


__all__ = ["ClickHouseSettingsDialog", "ClickHouseShardsTab"]
