#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka Consumer Group 탭 모듈

Consumer Group 목록과 각 그룹의 오프셋 및 랙(lag) 정보를 주기적으로 표시합니다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class ConsumerTab(QWidget if _HAS_QT else object):
    """
    Kafka Consumer Group 탭 위젯

    5초 간격으로 Consumer Group 상태와 랙 정보를 갱신합니다.
    """

    def __init__(self, parent=None, conn_params=None):
        """
        ConsumerTab 초기화

        Args:
            parent: 부모 위젯 (기본값: None)
            conn_params: DB 연결 파라미터 딕셔너리 (기본값: None)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "consumer_tab.ui")
        uic.loadUi(ui_path, self)

        self._setup_table()
        self._setup_timer()

    def _setup_table(self):
        """테이블 위젯 초기 설정"""
        header = self.table_consumers.horizontalHeader()
        header.setStretchLastSection(True)

    def _setup_timer(self):
        """5초 갱신 타이머 설정"""
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh_data)
        self._timer.start()

    def refresh_data(self):
        """
        Consumer Group 데이터 갱신

        외부에서 컨트롤러를 통해 데이터를 주입하거나,
        이 메서드를 오버라이드하여 실제 Kafka 조회 로직을 연결합니다.
        """
        pass

    def load_consumers(self, consumers: list):
        """
        Consumer Group 정보를 테이블에 로드합니다.

        Args:
            consumers (list): Consumer Group 정보 딕셔너리 리스트.
                각 항목은 'group_id', 'topic', 'partition',
                'current_offset', 'latest_offset', 'lag' 키를 포함해야 합니다.
        """
        self.table_consumers.setRowCount(0)
        for row_data in consumers:
            row = self.table_consumers.rowCount()
            self.table_consumers.insertRow(row)
            self.table_consumers.setItem(row, 0, self._make_item(str(row_data.get("group_id", ""))))
            self.table_consumers.setItem(row, 1, self._make_item(str(row_data.get("topic", ""))))
            self.table_consumers.setItem(row, 2, self._make_item(str(row_data.get("partition", ""))))
            self.table_consumers.setItem(row, 3, self._make_item(str(row_data.get("current_offset", ""))))
            self.table_consumers.setItem(row, 4, self._make_item(str(row_data.get("latest_offset", ""))))
            self.table_consumers.setItem(row, 5, self._make_item(str(row_data.get("lag", ""))))

    @staticmethod
    def _make_item(text: str):
        """QTableWidgetItem 생성 헬퍼"""
        from PyQt5.QtWidgets import QTableWidgetItem

        return QTableWidgetItem(text)
