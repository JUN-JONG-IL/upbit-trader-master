#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse OLAP 쿼리 실행 탭 위젯"""

import os
import time
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_FILE = os.path.join(os.path.dirname(__file__), "query_tab.ui")


class QueryTab(QWidget if _HAS_QT else object):
    """ClickHouse OLAP 쿼리를 직접 실행하고 결과를 표시하는 탭 위젯.

    사용자가 SQL 쿼리를 입력하고 실행 버튼을 눌러 결과를 표 형태로
    확인할 수 있습니다. 실행 경과 시간도 함께 표시합니다.
    """

    def __init__(self, client=None, parent=None, conn_params=None):
        """초기화.

        Args:
            client: ClickHouse HTTP 클라이언트 인스턴스 (선택)
            parent: 부모 위젯 (선택)
            conn_params: 연결 파라미터 딕셔너리 (선택)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._client = client
        self._conn_params = conn_params or {}
        uic.loadUi(_UI_FILE, self)
        self._setup_connections()

    def _setup_connections(self):
        """버튼 시그널을 슬롯에 연결합니다."""
        self.btn_run.clicked.connect(self._run_query)

    def set_client(self, client):
        """ClickHouse 클라이언트를 교체합니다.

        Args:
            client: 새로운 ClickHouse HTTP 클라이언트 인스턴스
        """
        self._client = client

    def _run_query(self):
        """편집기에 입력된 SQL 쿼리를 실행하고 결과를 테이블에 표시합니다.

        실행 시간을 측정하여 label_elapsed에 표시합니다.
        오류 발생 시 elapsed 레이블에 오류 메시지를 표시합니다.
        """
        query = self.edit_query.toPlainText().strip()
        if not query:
            return
        if self._client is None:
            self.label_elapsed.setText("클라이언트 미연결")
            return

        self.btn_run.setEnabled(False)
        self.label_elapsed.setText("실행 중...")
        self.table_result.clear()
        self.table_result.setRowCount(0)
        self.table_result.setColumnCount(0)

        start = time.perf_counter()
        try:
            rows, columns = self._client.execute_with_columns(query)
            elapsed = time.perf_counter() - start
            self._populate_result(columns, rows)
            self.label_elapsed.setText(f"경과 시간: {elapsed:.3f}초  ({len(rows)}행)")
        except Exception as exc:
            elapsed = time.perf_counter() - start
            self.label_elapsed.setText(f"오류 ({elapsed:.3f}초): {exc}")
            logger.warning("쿼리 실행 실패: %s", exc)
        finally:
            self.btn_run.setEnabled(True)

    def _populate_result(self, columns, rows):
        """쿼리 결과로 결과 테이블 위젯을 채웁니다.

        Args:
            columns: 컬럼 이름 목록
            rows: 데이터 행 목록 (튜플)
        """
        self.table_result.setColumnCount(len(columns))
        self.table_result.setHorizontalHeaderLabels(columns)
        self.table_result.setRowCount(len(rows))

        header = self.table_result.horizontalHeader()
        for col in range(len(columns)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.table_result.setItem(row_idx, col_idx, item)
