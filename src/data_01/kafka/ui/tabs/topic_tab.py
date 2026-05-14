#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 토픽 관리 탭 모듈

토픽 목록 조회, 생성, 삭제 기능을 제공합니다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class TopicTab(QWidget if _HAS_QT else object):
    """
    Kafka 토픽 관리 탭 위젯

    토픽 목록을 표시하고 생성/삭제 작업을 수행합니다.
    """

    def __init__(self, parent=None, conn_params=None):
        """
        TopicTab 초기화

        Args:
            parent: 부모 위젯 (기본값: None)
            conn_params: DB 연결 파라미터 딕셔너리 (기본값: None)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "topic_tab.ui")
        uic.loadUi(ui_path, self)

        self._topic_manager = None
        self._setup_table()
        self._connect_signals()

    def _setup_table(self):
        """테이블 위젯 초기 설정"""
        header = self.table_topics.horizontalHeader()
        header.setStretchLastSection(True)

    def _connect_signals(self):
        """버튼 시그널 연결"""
        self.btn_refresh.clicked.connect(self.refresh_topics)
        self.btn_create.clicked.connect(self.create_topic)
        self.btn_delete.clicked.connect(self.delete_topic)

    def set_topic_manager(self, manager):
        """
        토픽 매니저 설정

        Args:
            manager: TopicManager 인스턴스
        """
        self._topic_manager = manager

    def refresh_topics(self):
        """
        토픽 목록 갱신

        TopicManager를 통해 토픽 목록을 조회하고 테이블을 갱신합니다.
        """
        if self._topic_manager is None:
            return
        topics = self._topic_manager.list_topics()
        self.load_topics(topics)

    def create_topic(self):
        """
        새 토픽 생성 다이얼로그 표시

        사용자로부터 토픽명을 입력받아 생성을 시도합니다.
        """
        if not _HAS_QT:
            return
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "토픽 생성", "생성할 토픽명을 입력하세요:")
        if ok and name.strip():
            if self._topic_manager:
                success = self._topic_manager.create_topic(name.strip())
                if success:
                    QMessageBox.information(self, "성공", f"토픽 '{name}' 이(가) 생성되었습니다.")
                    self.refresh_topics()
                else:
                    QMessageBox.warning(self, "실패", f"토픽 '{name}' 생성에 실패했습니다.")

    def delete_topic(self):
        """
        선택된 토픽 삭제

        테이블에서 선택된 행의 토픽을 삭제합니다.
        """
        if not _HAS_QT:
            return
        selected_rows = self.table_topics.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "선택 없음", "삭제할 토픽을 선택하세요.")
            return

        row = self.table_topics.currentRow()
        topic_name = self.table_topics.item(row, 0)
        if topic_name is None:
            return
        name = topic_name.text()

        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"토픽 '{name}' 을(를) 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes and self._topic_manager:
            success = self._topic_manager.delete_topic(name)
            if success:
                QMessageBox.information(self, "성공", f"토픽 '{name}' 이(가) 삭제되었습니다.")
                self.refresh_topics()
            else:
                QMessageBox.warning(self, "실패", f"토픽 '{name}' 삭제에 실패했습니다.")

    def load_topics(self, topics: list):
        """
        토픽 목록을 테이블에 로드합니다.

        Args:
            topics (list): 토픽 정보 딕셔너리 리스트.
                각 항목은 'name', 'partitions', 'replicas', 'message_count', 'offset' 키를 포함해야 합니다.
        """
        self.table_topics.setRowCount(0)
        for row_data in topics:
            row = self.table_topics.rowCount()
            self.table_topics.insertRow(row)
            self.table_topics.setItem(row, 0, self._make_item(str(row_data.get("name", ""))))
            self.table_topics.setItem(row, 1, self._make_item(str(row_data.get("partitions", ""))))
            self.table_topics.setItem(row, 2, self._make_item(str(row_data.get("replicas", ""))))
            self.table_topics.setItem(row, 3, self._make_item(str(row_data.get("message_count", ""))))
            self.table_topics.setItem(row, 4, self._make_item(str(row_data.get("offset", ""))))

    @staticmethod
    def _make_item(text: str):
        """QTableWidgetItem 생성 헬퍼"""
        from PyQt5.QtWidgets import QTableWidgetItem

        return QTableWidgetItem(text)
