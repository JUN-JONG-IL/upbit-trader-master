#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 메시지 조회 탭 모듈

선택한 토픽의 최신 메시지를 조회하여 테이블에 표시합니다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class MessageTab(QWidget if _HAS_QT else object):
    """
    Kafka 메시지 조회 탭 위젯

    토픽을 선택하고 조회 수를 지정하여 메시지를 가져옵니다.
    """

    def __init__(self, parent=None, conn_params=None):
        """
        MessageTab 초기화

        Args:
            parent: 부모 위젯 (기본값: None)
            conn_params: DB 연결 파라미터 딕셔너리 (기본값: None)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "message_tab.ui")
        uic.loadUi(ui_path, self)

        self._message_fetcher = None
        self._setup_table()
        self._connect_signals()

    def _setup_table(self):
        """테이블 위젯 초기 설정"""
        header = self.table_messages.horizontalHeader()
        header.setStretchLastSection(True)

    def _connect_signals(self):
        """버튼 시그널 연결"""
        self.btn_fetch.clicked.connect(self.fetch_messages)

    def set_message_fetcher(self, fetcher):
        """
        메시지 조회 함수 또는 객체를 설정합니다.

        Args:
            fetcher: topic과 count를 인자로 받아 메시지 목록을 반환하는 callable.
        """
        self._message_fetcher = fetcher

    def update_topics(self, topics: list):
        """
        토픽 콤보박스 목록을 갱신합니다.

        Args:
            topics (list): 토픽명 문자열 리스트.
        """
        current = self.combo_topic.currentText()
        self.combo_topic.clear()
        self.combo_topic.addItems(topics)
        idx = self.combo_topic.findText(current)
        if idx >= 0:
            self.combo_topic.setCurrentIndex(idx)

    def fetch_messages(self):
        """
        선택된 토픽의 메시지를 조회합니다.

        combo_topic에서 선택된 토픽과 spin_count에서 지정된 수만큼 메시지를 가져옵니다.
        """
        topic = self.combo_topic.currentText()
        count = self.spin_count.value()
        if not topic or self._message_fetcher is None:
            return
        messages = self._message_fetcher(topic, count)
        self.load_messages(messages)

    def load_messages(self, messages: list):
        """
        메시지 목록을 테이블에 로드합니다.

        Args:
            messages (list): 메시지 정보 딕셔너리 리스트.
                각 항목은 'partition', 'offset', 'key', 'value', 'timestamp' 키를 포함해야 합니다.
        """
        self.table_messages.setRowCount(0)
        for row_data in messages:
            row = self.table_messages.rowCount()
            self.table_messages.insertRow(row)
            self.table_messages.setItem(row, 0, self._make_item(str(row_data.get("partition", ""))))
            self.table_messages.setItem(row, 1, self._make_item(str(row_data.get("offset", ""))))
            self.table_messages.setItem(row, 2, self._make_item(str(row_data.get("key", ""))))
            self.table_messages.setItem(row, 3, self._make_item(str(row_data.get("value", ""))))
            self.table_messages.setItem(row, 4, self._make_item(str(row_data.get("timestamp", ""))))

    @staticmethod
    def _make_item(text: str):
        """QTableWidgetItem 생성 헬퍼"""
        from PyQt5.QtWidgets import QTableWidgetItem

        return QTableWidgetItem(text)
