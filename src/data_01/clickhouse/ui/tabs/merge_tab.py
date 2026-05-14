#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse MergeTree 관리 탭 위젯"""

import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_FILE = os.path.join(os.path.dirname(__file__), "merge_tab.ui")


class MergeTab(QWidget if _HAS_QT else object):
    """ClickHouse MergeTree 엔진의 활성 병합 및 파트 통계를 표시하는 탭 위젯.

    5초마다 자동으로 갱신하며, 현재 진행 중인 병합 작업과
    각 테이블의 파트 수, 행 수, 디스크 크기를 표시합니다.
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
        self._setup_tables()
        self._setup_timer()

    def _setup_tables(self):
        """두 테이블 위젯의 헤더 크기 조정 모드를 설정합니다."""
        for tbl in (self.table_merges, self.table_parts):
            header = tbl.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for col in range(1, tbl.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
            tbl.setEditTriggers(tbl.NoEditTriggers)

    def _setup_timer(self):
        """5초 주기 자동 갱신 타이머를 설정합니다."""
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def set_client(self, client):
        """ClickHouse 클라이언트를 교체합니다.

        Args:
            client: 새로운 ClickHouse HTTP 클라이언트 인스턴스
        """
        self._client = client
        self._refresh()

    def _refresh(self):
        """활성 병합 및 파트 통계를 조회하여 테이블을 갱신합니다."""
        self._refresh_merges()
        self._refresh_parts()

    def _refresh_merges(self):
        """system.merges 테이블에서 활성 병합 정보를 조회합니다."""
        if self._client is None:
            return
        try:
            query = (
                "SELECT table, "
                "num_parts, "
                "round(progress * 100, 1) AS progress_pct, "
                "round(elapsed, 1) AS elapsed_sec "
                "FROM system.merges "
                "ORDER BY elapsed DESC"
            )
            rows = self._client.execute(query)
            self._populate(self.table_merges, rows)
        except Exception as exc:
            logger.warning("활성 병합 조회 실패: %s", exc)

    def _refresh_parts(self):
        """system.parts 테이블에서 파트 통계를 조회합니다."""
        if self._client is None:
            return
        try:
            query = (
                "SELECT table, "
                "count() AS parts, "
                "sum(rows) AS rows, "
                "formatReadableSize(sum(bytes_on_disk)) AS size "
                "FROM system.parts "
                "WHERE active = 1 "
                "GROUP BY table "
                "ORDER BY sum(bytes_on_disk) DESC"
            )
            rows = self._client.execute(query)
            self._populate(self.table_parts, rows)
        except Exception as exc:
            logger.warning("파트 통계 조회 실패: %s", exc)

    def _populate(self, table_widget, rows):
        """조회된 데이터로 지정한 테이블 위젯을 채웁니다.

        Args:
            table_widget: 데이터를 채울 QTableWidget
            rows: 행 데이터 튜플 목록
        """
        table_widget.setRowCount(len(rows))
        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                table_widget.setItem(row_idx, col_idx, item)
