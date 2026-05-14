# -*- coding: utf-8 -*-
"""
실시간 로그 테이블 위젯

[책임]
- 1초마다 RealtimeLogHandler에서 로그를 가져와 테이블 갱신
- WebSocket / Pipeline / Gap 필터 지원
- 레벨별 색상 코딩 (ERROR/WARNING/INFO/DEBUG)
- 자동 스크롤 (항상 최신 로그 표시)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QHBoxLayout,
        QHeaderView,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[LogTableWidget] PyQt5 없음 — 더미 클래스 사용")

# 레벨별 전경색 (RGB)
_LEVEL_COLORS: Dict[str, tuple] = {
    "ERROR":   (255, 68,  68),
    "WARNING": (255, 152,  0),
    "INFO":    (52,  199, 89),
    "DEBUG":   (0,   122, 255),
}


if _HAS_QT:
    class LogTableWidget(QWidget):
        """
        실시간 로그 테이블 위젯

        - 1초마다 갱신 (QTimer)
        - 기존 QTableWidgetItem 재사용으로 성능 최적화
        - 필터 딕셔너리를 외부에서 전달 받음
        """

        _REFRESH_INTERVAL_MS = 1000  # 1초

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            log_handler: Any = None,
        ) -> None:
            super().__init__(parent)
            self._log_handler = log_handler

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            # 테이블 위젯
            self.table = QTableWidget(self)
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["시간", "레벨", "모듈", "메시지"])
            self.table.setAlternatingRowColors(True)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
            layout.addWidget(self.table)

            # 1초마다 갱신 타이머
            self._timer = QTimer(self)
            self._timer.setInterval(self._REFRESH_INTERVAL_MS)
            self._timer.timeout.connect(self.refresh)
            self._timer.start()

        # ------------------------------------------------------------------
        # 공개 API
        # ------------------------------------------------------------------

        def set_log_handler(self, log_handler: Any) -> None:
            """로그 핸들러를 교체합니다."""
            self._log_handler = log_handler

        def refresh(
            self,
            filters: Optional[Dict[str, bool]] = None,
        ) -> None:
            """로그 테이블을 즉시 갱신합니다.

            Args:
                filters: {"websocket": True, "pipeline": True, "gap": False}
                         None이면 기본 필터 사용 (websocket+pipeline 활성)
            """
            if self._log_handler is None:
                return

            if filters is None:
                filters = {"websocket": True, "pipeline": True, "gap": False}

            try:
                logs = self._log_handler.get_logs(filters)
                log_count = len(logs)
                current_rows = self.table.rowCount()

                # 행이 부족할 때만 추가 (불필요한 위아래 조정 방지)
                if log_count > current_rows:
                    self.table.setRowCount(log_count)

                for i, log in enumerate(logs):
                    # 시간
                    self._set_text(i, 0, log["time"])

                    # 레벨 (색상 적용)
                    item = self.table.item(i, 1)
                    if item is None:
                        item = QTableWidgetItem()
                        self.table.setItem(i, 1, item)
                    item.setText(log["level"])
                    rgb = _LEVEL_COLORS.get(log["level"], (128, 128, 128))
                    item.setForeground(QColor(*rgb))

                    # 모듈
                    self._set_text(i, 2, log["module"])

                    # 메시지
                    self._set_text(i, 3, log["message"])

                # 잉여 행 제거 (표시 건수가 줄었을 때)
                if log_count < current_rows:
                    self.table.setRowCount(log_count)

                # 자동 스크롤
                self.table.scrollToBottom()
            except Exception as exc:
                logger.debug("[LogTableWidget] 갱신 실패: %s", exc)

        def clear(self) -> None:
            """로그 테이블을 초기화합니다."""
            try:
                if self._log_handler is not None:
                    self._log_handler.logs.clear()
                self.table.setRowCount(0)
            except Exception as exc:
                logger.debug("[LogTableWidget] 초기화 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 헬퍼
        # ------------------------------------------------------------------

        def _set_text(self, row: int, col: int, text: str) -> None:
            """기존 아이템이 있으면 setText, 없으면 새로 생성합니다."""
            item = self.table.item(row, col)
            if item is None:
                self.table.setItem(row, col, QTableWidgetItem(text))
            else:
                item.setText(text)

else:
    class LogTableWidget:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None, log_handler=None) -> None:
            logger.warning("[LogTableWidget] PyQt5 미설치 — 더미 인스턴스 생성")

        def set_log_handler(self, log_handler) -> None:
            """더미 메서드"""

        def refresh(self, filters=None) -> None:
            """더미 메서드"""

        def clear(self) -> None:
            """더미 메서드"""
