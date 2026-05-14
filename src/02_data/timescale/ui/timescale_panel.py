# -*- coding: utf-8 -*-
"""
TimescaleDB 모니터링 패널 (개별 DB UI)

기능:
- Gap 현황 표시 (pending/total)
- 심볼별 최신 캔들 시간 테이블
- 수동 Gap 검사 버튼
- 1초 주기 자동 갱신 (QTimer + asyncio)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTableView, QLabel,
        QPushButton, QProgressBar,
    )
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtGui import QStandardItemModel, QStandardItem
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class TimescalePanel(QWidget):
        """TimescaleDB 모니터링 패널 (개별 DB UI)"""

        def __init__(self, timescale_pool=None, redis_client=None, parent=None):
            super().__init__(parent)
            self._pool = timescale_pool
            self._redis = redis_client
            self._init_ui()
            self._start_timer()

        def _init_ui(self):
            layout = QVBoxLayout(self)

            # 제목
            title = QLabel("TimescaleDB 모니터링")
            title.setStyleSheet("font-size: 16pt; font-weight: bold;")
            layout.addWidget(title)

            # Gap 현황
            gap_layout = QHBoxLayout()
            self._gap_count_label = QLabel("Gap 수: 0")
            self._gap_progress = QProgressBar()
            gap_layout.addWidget(self._gap_count_label)
            gap_layout.addWidget(self._gap_progress)
            layout.addLayout(gap_layout)

            # 데이터 테이블
            self._table = QTableView()
            self._model = QStandardItemModel(0, 3)
            self._model.setHorizontalHeaderLabels(["심볼", "타임프레임", "최신 시간"])
            self._table.setModel(self._model)
            layout.addWidget(self._table)

            # 액션 버튼
            self._btn_gap_check = QPushButton("Gap 검사 실행")
            self._btn_gap_check.clicked.connect(self._on_gap_check)
            layout.addWidget(self._btn_gap_check)

        def _start_timer(self):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_ui)
            self._timer.start(1000)  # 1초마다

        def _update_ui(self):
            """UI 데이터 갱신 (동기 조회)"""
            if self._pool is None:
                return
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._update_ui_async())
            except Exception as exc:
                logger.debug("[TimescalePanel] UI 업데이트 스케줄 실패: %s", exc)

        async def _update_ui_async(self):
            """비동기 UI 데이터 갱신"""
            try:
                async with self._pool.acquire() as conn:
                    gap_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM gaps WHERE status = 'pending'"
                    )
                    total_gap = await conn.fetchval("SELECT COUNT(*) FROM gaps")

                self._gap_count_label.setText(f"Gap 수: {gap_count} / {total_gap}")

                if total_gap > 0:
                    progress = int((total_gap - gap_count) / total_gap * 100)
                    self._gap_progress.setValue(progress)
            except Exception as exc:
                logger.error("[TimescalePanel] UI 업데이트 실패: %s", exc)

        def _on_gap_check(self):
            logger.info("[TimescalePanel] 수동 Gap 검사 실행")

        def stop_refresh(self):
            """타이머 중단"""
            if hasattr(self, "_timer"):
                self._timer.stop()

else:
    class TimescalePanel:  # type: ignore
        """PyQt5 미설치 시 폴백 스텁"""

        def __init__(self, *args, **kwargs):
            logger.warning("[TimescalePanel] PyQt5 미설치 - 폴백 스텁")

        def stop_refresh(self):
            pass
