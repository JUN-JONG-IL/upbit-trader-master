#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿼리 실행기 탭 모듈"""

import json
import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "query_tab.ui")


class QueryTab(QWidget if _HAS_QT else object):
    """쿼리 실행기 탭.

    사용자가 JSON 형식의 쿼리를 입력하면 MongoDB에서 실행하고
    결과를 테이블로 표시합니다.

    쿼리 형식 예시::

        {
            "collection": "ohlcv",
            "filter": {"symbol": "KRW-BTC"},
            "limit": 50
        }
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
        self.btn_run.clicked.connect(self._run_query)

    def set_mongo_client(self, client):
        """MongoDB 클라이언트를 교체합니다.

        Args:
            client: 새 MongoDB 클라이언트.
        """
        self._mongo_client = client

    def _run_query(self):
        """edit_query의 JSON을 파싱하여 MongoDB 쿼리를 실행합니다.

        결과 도큐먼트의 필드를 컬럼으로 사용하여 table_result를 채웁니다.
        쿼리 파싱 오류 또는 DB 오류 발생 시 로그에 기록합니다.
        """
        raw_text = self.edit_query.toPlainText().strip()
        if not raw_text:
            return
        try:
            params = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning("JSON 파싱 오류: %s", exc)
            return
        if self._mongo_client is None:
            logger.warning("MongoDB 클라이언트가 설정되지 않았습니다.")
            return
        collection_name = params.get("collection", "")
        query_filter = params.get("filter", {})
        limit = int(params.get("limit", 100))
        projection = params.get("projection", None)
        if not collection_name:
            logger.warning("쿼리에 'collection' 필드가 없습니다.")
            return
        try:
            db = self._mongo_client.get_default_database()
            cursor = db[collection_name].find(query_filter, projection).limit(limit)
            docs = list(cursor)
            if not docs:
                self.table_result.setRowCount(0)
                self.table_result.setColumnCount(0)
                return
            # 모든 도큐먼트의 키를 합산하여 컬럼 구성
            columns = list(dict.fromkeys(
                key for doc in docs for key in doc.keys() if key != "_id"
            ))
            self.table_result.setColumnCount(len(columns))
            self.table_result.setHorizontalHeaderLabels(columns)
            self.table_result.setRowCount(0)
            header = self.table_result.horizontalHeader()
            for col in range(len(columns)):
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
            for doc in docs:
                row = self.table_result.rowCount()
                self.table_result.insertRow(row)
                for col, key in enumerate(columns):
                    value = doc.get(key, "")
                    self.table_result.setItem(row, col, QTableWidgetItem(str(value)))
        except Exception as exc:
            logger.warning("쿼리 실행 실패: %s", exc)

    def closeEvent(self, event):
        """위젯 닫힘 이벤트 처리."""
        super().closeEvent(event)
