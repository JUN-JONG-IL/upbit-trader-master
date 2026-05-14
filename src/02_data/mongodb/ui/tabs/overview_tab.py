#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""컬렉션 통계 개요 탭 모듈"""

import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "overview_tab.ui")


class OverviewTab(QWidget if _HAS_QT else object):
    """컬렉션 통계 개요 탭.

    MongoDB의 각 컬렉션에 대한 도큐먼트 수, 크기, 인덱스 수를
    5초 간격으로 자동 갱신하여 표시합니다.
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
        self._timer = None
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        """UI 파일 로드 및 테이블 초기 설정."""
        uic.loadUi(_UI_PATH, self)
        header = self.table_collections.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

    def _setup_timer(self):
        """5초 주기 자동 갱신 타이머 설정."""
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh_collections)
        self._timer.start()

    def set_mongo_client(self, client):
        """MongoDB 클라이언트를 교체합니다.

        Args:
            client: 새 MongoDB 클라이언트.
        """
        self._mongo_client = client
        self._refresh_collections()

    def _refresh_collections(self):
        """MongoDB에서 컬렉션 통계를 읽어 테이블을 갱신합니다."""
        if self._mongo_client is None:
            return
        try:
            db = self._mongo_client.get_default_database()
            collection_names = db.list_collection_names()
            self.table_collections.setRowCount(0)
            for name in sorted(collection_names):
                stats = db.command("collstats", name)
                row = self.table_collections.rowCount()
                self.table_collections.insertRow(row)
                doc_count = stats.get("count", 0)
                size_bytes = stats.get("size", 0)
                index_count = stats.get("nindexes", 0)
                size_str = self._format_bytes(size_bytes)
                self.table_collections.setItem(row, 0, QTableWidgetItem(name))
                self.table_collections.setItem(row, 1, QTableWidgetItem(str(doc_count)))
                self.table_collections.setItem(row, 2, QTableWidgetItem(size_str))
                self.table_collections.setItem(row, 3, QTableWidgetItem(str(index_count)))
        except Exception as exc:
            logger.warning("컬렉션 통계 갱신 실패: %s", exc)

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """바이트 수를 사람이 읽기 쉬운 문자열로 변환합니다.

        Args:
            num_bytes: 바이트 수.

        Returns:
            포맷된 크기 문자열 (예: "1.23 MB").
        """
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if num_bytes < 1024:
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024
        return f"{num_bytes:.1f} PB"

    def closeEvent(self, event):
        """위젯 닫힘 시 타이머를 정지합니다."""
        if self._timer is not None:
            self._timer.stop()
        super().closeEvent(event)
