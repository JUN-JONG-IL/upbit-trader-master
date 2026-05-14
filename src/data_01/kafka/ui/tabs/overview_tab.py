#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 브로커/토픽 통계 개요 탭 모듈

브로커 상태와 토픽 요약 정보를 주기적으로 조회하여 표시합니다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class OverviewTab(QWidget if _HAS_QT else object):
    """
    브로커/토픽 통계 개요 탭 위젯

    5초 간격으로 브로커 상태와 토픽 요약 정보를 갱신합니다.
    """

    def __init__(self, parent=None, conn_params=None):
        """
        OverviewTab 초기화

        Args:
            parent: 부모 위젯 (기본값: None)
            conn_params: DB 연결 파라미터 딕셔너리 (기본값: None)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "overview_tab.ui")
        uic.loadUi(ui_path, self)

        self._setup_tables()
        self._setup_timer()

    def _setup_tables(self):
        """테이블 위젯 초기 설정"""
        # 브로커 테이블: 열 너비 자동 조정
        header = self.table_brokers.horizontalHeader()
        header.setStretchLastSection(True)

        # 토픽 요약 테이블: 열 너비 자동 조정
        summary_header = self.table_topics_summary.horizontalHeader()
        summary_header.setStretchLastSection(True)

    def _setup_timer(self):
        """5초 갱신 타이머 설정"""
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh_data)
        self._timer.start()

    def refresh_data(self):
        """
        브로커 및 토픽 데이터 갱신

        외부에서 컨트롤러를 통해 데이터를 주입하거나,
        이 메서드를 오버라이드하여 실제 Kafka 조회 로직을 연결합니다.
        """
        pass

    def load_broker_data(self, brokers: list):
        """
        브로커 상태 테이블에 데이터를 로드합니다.

        Args:
            brokers (list): 브로커 정보 딕셔너리 리스트.
                각 항목은 'id', 'host', 'port', 'status' 키를 포함해야 합니다.
        """
        self.table_brokers.setRowCount(0)
        for row_data in brokers:
            row = self.table_brokers.rowCount()
            self.table_brokers.insertRow(row)
            self.table_brokers.setItem(row, 0, self._make_item(str(row_data.get("id", ""))))
            self.table_brokers.setItem(row, 1, self._make_item(str(row_data.get("host", ""))))
            self.table_brokers.setItem(row, 2, self._make_item(str(row_data.get("port", ""))))
            self.table_brokers.setItem(row, 3, self._make_item(str(row_data.get("status", ""))))

    def load_topic_summary(self, summary: dict):
        """
        토픽 요약 테이블에 데이터를 로드합니다.

        Args:
            summary (dict): 'topic_count', 'partition_count', 'message_count' 키를 포함하는 딕셔너리.
        """
        self.table_topics_summary.setRowCount(0)
        self.table_topics_summary.insertRow(0)
        self.table_topics_summary.setItem(0, 0, self._make_item(str(summary.get("topic_count", 0))))
        self.table_topics_summary.setItem(0, 1, self._make_item(str(summary.get("partition_count", 0))))
        self.table_topics_summary.setItem(0, 2, self._make_item(str(summary.get("message_count", 0))))

    @staticmethod
    def _make_item(text: str):
        """QTableWidgetItem 생성 헬퍼"""
        from PyQt5.QtWidgets import QTableWidgetItem

        return QTableWidgetItem(text)
