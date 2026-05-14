# -*- coding: utf-8 -*-
"""
모든 DB 모니터링 탭의 기본 클래스

[공통 기능]
- QTimer를 활용한 자동 새로고침 (1초~10초, 설정 가능)
- 탭 활성화 시에만 데이터 갱신 (렉 방지)
- 비동기 DB 조회 (QThread)
- 상태별 색상 표시 (초록/노랑/빨강)

[Author] Copilot Workspace
[Created] 2026-04-15
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QWidget, QLabel
    from PyQt5.QtCore import QTimer
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[BaseMonitorTab] PyQt5 없음 - UI 비활성화")


if _HAS_QT:

    class BaseMonitorTab(QWidget):
        """
        모든 DB 모니터링 탭의 기본 클래스.

        - QTimer를 활용한 자동 새로고침 (기본 2초, 설정 가능)
        - 탭 활성화(showEvent) 시에만 타이머 시작 (렉 방지)
        - 탭 비활성화(hideEvent) 시 타이머 정지
        - 서브클래스에서 refresh_data() 구현 필요
        """

        def __init__(self, parent: Optional[QWidget] = None, refresh_interval: int = 2000) -> None:
            """초기화.

            Args:
                parent: 부모 위젯 (선택)
                refresh_interval: 자동 갱신 간격(밀리초), 기본 2000ms
            """
            super().__init__(parent)
            # 탭 활성화 여부
            self.is_active: bool = False
            # 자동 갱신 간격 (밀리초)
            self.refresh_interval: int = refresh_interval
            # 갱신 타이머
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh_data)

        def showEvent(self, event) -> None:
            """탭 활성화 시 타이머 시작 및 즉시 갱신."""
            self.is_active = True
            self.timer.start(self.refresh_interval)
            self.refresh_data()
            super().showEvent(event)

        def hideEvent(self, event) -> None:
            """탭 비활성화 시 타이머 정지 (렉 방지)."""
            self.is_active = False
            self.timer.stop()
            super().hideEvent(event)

        def refresh_data(self) -> None:
            """비동기 데이터 갱신 (서브클래스에서 구현).

            QThread를 사용하여 비동기로 DB를 조회하고 UI를 업데이트합니다.
            메인 스레드 블로킹을 방지하기 위해 반드시 비동기로 구현해야 합니다.
            """
            raise NotImplementedError(
                f"{self.__class__.__name__}.refresh_data()를 구현해야 합니다."
            )

        def update_status_label(self, label: QLabel, status: str) -> None:
            """상태 라벨 색상 및 텍스트 업데이트.

            Args:
                label: 업데이트할 QLabel 위젯
                status: 상태 문자열
                    - "connected": 연결됨 (초록)
                    - "warning": 경고 (노랑)
                    - "error": 오류 (빨강)
                    - 그 외: 연결 안 됨 (회색)
            """
            if status == "connected":
                label.setStyleSheet(
                    "background-color: #2ECC71; color: #FFFFFF; "
                    "padding: 4px; border-radius: 3px;"
                )
                label.setText("● 연결됨")
            elif status == "warning":
                label.setStyleSheet(
                    "background-color: #F39C12; color: #FFFFFF; "
                    "padding: 4px; border-radius: 3px;"
                )
                label.setText("⚠ 경고")
            elif status == "error":
                label.setStyleSheet(
                    "background-color: #E74C3C; color: #FFFFFF; "
                    "padding: 4px; border-radius: 3px;"
                )
                label.setText("✖ 오류")
            else:
                label.setStyleSheet(
                    "background-color: #BDC3C7; color: #2C3E50; "
                    "padding: 4px; border-radius: 3px;"
                )
                label.setText("○ 연결 안 됨")

        def update_table_incremental(self, table, new_data: list) -> None:
            """변경된 셀만 업데이트하는 최적화된 테이블 갱신.

            Args:
                table: QTableWidget 인스턴스
                new_data: 새로운 행 데이터 목록 (각 행은 값의 리스트)
            """
            from PyQt5.QtWidgets import QTableWidgetItem
            table.setRowCount(len(new_data))
            for row_idx, row_data in enumerate(new_data):
                for col_idx, value in enumerate(row_data):
                    existing_item = table.item(row_idx, col_idx)
                    str_value = str(value)
                    if not existing_item or existing_item.text() != str_value:
                        table.setItem(row_idx, col_idx, QTableWidgetItem(str_value))

else:

    class BaseMonitorTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 기본 클래스."""

        def __init__(self, *args, **kwargs) -> None:
            logger.warning("[BaseMonitorTab] PyQt5 미설치 - 더미 클래스 사용")
            self.is_active = False
            self.refresh_interval = 2000

        def refresh_data(self) -> None:
            """더미 구현."""
            pass

        def update_status_label(self, label, status: str) -> None:
            """더미 구현."""
            pass

        def update_table_incremental(self, table, new_data: list) -> None:
            """더미 구현."""
            pass
