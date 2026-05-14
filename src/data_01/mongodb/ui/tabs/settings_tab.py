#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 설정 관리 탭 모듈"""

import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QMessageBox
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "settings_tab.ui")


class SettingsTab(QWidget if _HAS_QT else object):
    """UI 설정 관리 탭.

    MongoDB의 ui_settings 컬렉션에 저장된 설정 키/값 목록을
    조회, 삭제할 수 있는 탭입니다.
    """

    def __init__(self, parent=None, mongo_client=None, conn_params=None):
        """초기화.

        Args:
            parent: 부모 위젯.
            mongo_client: MongoDB 클라이언트 인스턴스 (선택).
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._mongo_client = mongo_client
        self._conn_params = conn_params or {}
        self._setup_ui()

    def _setup_ui(self):
        """UI 파일 로드 및 버튼 시그널 연결."""
        uic.loadUi(_UI_PATH, self)
        self.btn_refresh.clicked.connect(self._load_settings)
        self.btn_delete.clicked.connect(self._delete_selected)
        header = self.table_settings.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

    def set_mongo_client(self, client):
        """MongoDB 클라이언트를 교체합니다.

        Args:
            client: 새 MongoDB 클라이언트.
        """
        self._mongo_client = client
        self._load_settings()

    def _load_settings(self):
        """ui_settings 컬렉션의 전체 문서를 읽어 테이블을 갱신합니다."""
        if self._mongo_client is None:
            logger.warning("MongoDB 클라이언트가 설정되지 않았습니다.")
            return
        try:
            db = self._mongo_client.get_default_database()
            collection = db["ui_settings"]
            cursor = collection.find().sort("key", 1)
            self.table_settings.setRowCount(0)
            for doc in cursor:
                row = self.table_settings.rowCount()
                self.table_settings.insertRow(row)
                key = str(doc.get("key", ""))
                value = str(doc.get("value", ""))
                dtype = type(doc.get("value", "")).__name__
                updated_at = str(doc.get("updated_at", ""))
                self.table_settings.setItem(row, 0, QTableWidgetItem(key))
                self.table_settings.setItem(row, 1, QTableWidgetItem(value))
                self.table_settings.setItem(row, 2, QTableWidgetItem(dtype))
                self.table_settings.setItem(row, 3, QTableWidgetItem(updated_at))
        except Exception as exc:
            logger.warning("설정 로드 실패: %s", exc)

    def _delete_selected(self):
        """선택된 행의 설정 키를 MongoDB에서 삭제합니다."""
        selected = self.table_settings.selectedItems()
        if not selected:
            return
        row = self.table_settings.currentRow()
        key_item = self.table_settings.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"'{key}' 설정을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self._mongo_client is None:
            return
        try:
            db = self._mongo_client.get_default_database()
            db["ui_settings"].delete_one({"key": key})
            self.table_settings.removeRow(row)
            logger.info("설정 삭제 완료: %s", key)
        except Exception as exc:
            logger.warning("설정 삭제 실패: %s", exc)

    def closeEvent(self, event):
        """위젯 닫힘 이벤트 처리."""
        super().closeEvent(event)
