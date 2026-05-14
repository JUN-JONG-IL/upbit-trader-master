#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimescaleDB 설정 위젯 모듈

TimescaleSettingsDialog(메인 다이얼로그)와
TimescaleClusterTab(클러스터 모니터링 탭)을 하나의 모듈로 통합합니다.

이전에 timescale/ 서브패키지(timescale/tab_cluster.py)에 있던
TimescaleClusterTab 클래스를 이 모듈로 이전하였습니다.
"""
from __future__ import annotations

import asyncio
import logging
import os as _os
from typing import Optional

# 메인 다이얼로그 re-export
from .timescale_settings_dialog import TimescaleSettingsDialog  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PyQt5 임포트
# ---------------------------------------------------------------------------
try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import (
        QHBoxLayout,
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
    import asyncpg  # type: ignore
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False

# ---------------------------------------------------------------------------
# 클러스터 노드 정의
# ---------------------------------------------------------------------------
_NODES = [
    {"host": "postgres-primary",   "port": 5432, "role": "Primary"},
    {"host": "postgres-replica-1", "port": 5433, "role": "Replica"},
    {"host": "postgres-replica-2", "port": 5434, "role": "Replica"},
]

_DB_USER     = _os.getenv("POSTGRES_USER", "admin")
_DB_PASSWORD = _os.getenv("POSTGRES_PASSWORD", "")
_DB_NAME     = _os.getenv("POSTGRES_DB", "upbit_trader")


# ---------------------------------------------------------------------------
# TimescaleClusterTab
# ---------------------------------------------------------------------------
if _PYQT5_AVAILABLE:
    class TimescaleClusterTab(QWidget):
        """PostgreSQL / TimescaleDB 클러스터 모니터링 탭"""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._setup_ui()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_timer)
            self._timer.start(10_000)  # 10초마다 갱신
            self._on_timer()

        # ------------------------------------------------------------------
        # UI 구성
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            title = QLabel("<h2>📊 PostgreSQL 클러스터 상태 (Primary + Replica 2대)</h2>")
            title.setAlignment(Qt.AlignLeft)
            layout.addWidget(title)

            summary_row = QHBoxLayout()
            self._lbl_primary  = QLabel("Primary: ⏳")
            self._lbl_replica1 = QLabel("Replica-1: ⏳")
            self._lbl_replica2 = QLabel("Replica-2: ⏳")
            self._lbl_haproxy  = QLabel("HAProxy: ⏳")
            for lbl in (
                self._lbl_primary,
                self._lbl_replica1,
                self._lbl_replica2,
                self._lbl_haproxy,
            ):
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                summary_row.addWidget(lbl)
            layout.addLayout(summary_row)

            self._table = QTableWidget(0, 6)
            self._table.setHorizontalHeaderLabels(
                ["노드", "역할", "상태", "Replication Lag", "TPS", "연결 수"]
            )
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.setMinimumHeight(300)
            self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._table)

            haproxy_label = QLabel("<h3>⚖️ HAProxy 로드밸런서 상태</h3>")
            layout.addWidget(haproxy_label)

            self._haproxy_table = QTableWidget(0, 3)
            self._haproxy_table.setHorizontalHeaderLabels(
                ["엔드포인트", "백엔드", "상태"]
            )
            self._haproxy_table.setMinimumHeight(80)
            self._haproxy_table.setMaximumHeight(120)
            layout.addWidget(self._haproxy_table)

        # ------------------------------------------------------------------
        # 타이머 핸들러
        # ------------------------------------------------------------------

        def _on_timer(self) -> None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._fetch_cluster_status())
                else:
                    loop.run_until_complete(self._fetch_cluster_status())
            except Exception as exc:
                logger.warning("클러스터 상태 조회 실패: %s", exc)

        # ------------------------------------------------------------------
        # 비동기 상태 조회
        # ------------------------------------------------------------------

        async def _fetch_cluster_status(self) -> None:
            self._table.setRowCount(len(_NODES))

            summary_labels = [
                self._lbl_primary,
                self._lbl_replica1,
                self._lbl_replica2,
            ]
            role_names = ["Primary", "Replica-1", "Replica-2"]

            for i, node in enumerate(_NODES):
                host = node["host"]
                port = node["port"]
                role = node["role"]

                try:
                    if not _ASYNCPG_AVAILABLE:
                        raise ImportError("asyncpg 미설치")

                    conn = await asyncpg.connect(
                        host=host,
                        port=port,
                        user=_DB_USER,
                        password=_DB_PASSWORD,
                        database=_DB_NAME,
                        timeout=3,
                    )

                    lag_str = "-"
                    if role == "Replica":
                        lag_ms = await conn.fetchval(
                            "SELECT extract(epoch FROM now() - pg_last_xact_replay_timestamp()) * 1000"
                        )
                        lag_str = f"{lag_ms:.0f}ms" if lag_ms is not None else "-"

                    tps = await conn.fetchval(
                        "SELECT sum(xact_commit + xact_rollback) FROM pg_stat_database "
                        "WHERE datname = $1",
                        _DB_NAME,
                    )

                    conns = await conn.fetchval(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = $1",
                        _DB_NAME,
                    )

                    await conn.close()

                    status = "🟢 UP"
                    self._table.setItem(i, 2, _item(status))
                    self._table.setItem(i, 3, _item(lag_str))
                    self._table.setItem(i, 4, _item(f"{tps or 0:,} TPS"))
                    self._table.setItem(i, 5, _item(f"{conns or 0}개"))
                    summary_labels[i].setText(f"{role_names[i]}: 🟢 UP")

                except Exception as exc:
                    status = "🔴 DOWN"
                    self._table.setItem(i, 2, _item(status))
                    self._table.setItem(i, 3, _item("-"))
                    self._table.setItem(i, 4, _item("-"))
                    self._table.setItem(i, 5, _item(str(exc)[:50]))
                    summary_labels[i].setText(f"{role_names[i]}: 🔴 DOWN")
                    logger.debug("노드 %s:%s 연결 실패: %s", host, port, exc)

                self._table.setItem(i, 0, _item(f"{host}:{port}"))
                self._table.setItem(i, 1, _item(role))

            self._haproxy_table.setRowCount(1)
            self._haproxy_table.setItem(0, 0, _item("localhost:5000"))
            self._haproxy_table.setItem(0, 1, _item("postgres_replicas"))
            self._haproxy_table.setItem(0, 2, _item("🟡 구성됨"))
            self._lbl_haproxy.setText("HAProxy: 🟡 확인 필요")

else:
    class TimescaleClusterTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 빈 클래스"""
        def __init__(self, parent=None) -> None:
            logger.warning("[TimescaleClusterTab] PyQt5 미설치 - 탭 생성 불가")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _item(text: str) -> "QTableWidgetItem":
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


__all__ = ["TimescaleSettingsDialog", "TimescaleClusterTab"]
