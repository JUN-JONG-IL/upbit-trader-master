#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
쿼리 실행기 탭 모듈.

사용자가 임의의 SQL을 입력하고 ``▶ 실행`` 버튼을 눌러
결과를 ``table_result`` 위젯에서 확인할 수 있다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


class QueryTab(QWidget):
    """SQL 쿼리 실행기 탭.

    ``edit_query`` 에 SQL을 입력한 후 ``btn_run`` 을 클릭하면
    결과가 ``table_result`` 에 표시된다.
    """

    def __init__(self, parent=None, conn_params=None):
        """위젯을 초기화하고 UI 파일을 로드한다."""
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "query_tab.ui")
        uic.loadUi(ui_path, self)

        self._conn = None
        self._setup_table()
        self._connect_signals()

    # ------------------------------------------------------------------
    # 초기화 헬퍼
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """결과 테이블 기본 설정을 지정한다."""
        header = self.table_result.horizontalHeader()
        header.setStretchLastSection(True)
        self.table_result.setEditTriggers(self.table_result.NoEditTriggers)
        self.table_result.setSelectionBehavior(self.table_result.SelectRows)

    def _connect_signals(self) -> None:
        """버튼 클릭 시그널을 슬롯에 연결한다."""
        self.btn_run.clicked.connect(self._on_run_clicked)

    # ------------------------------------------------------------------
    # 슬롯
    # ------------------------------------------------------------------

    def _on_run_clicked(self) -> None:
        """▶ 실행 버튼 클릭 핸들러.

        입력된 SQL을 실행하고 결과를 테이블에 채운다.
        연결 객체가 없으면 경고 메시지를 표시한다.
        """
        sql = self.edit_query.toPlainText().strip()
        if not sql:
            return

        if self._conn is None:
            QMessageBox.warning(self, "연결 없음", "PostgreSQL 연결이 설정되지 않았습니다.")
            return

        self._execute_query(sql)

    def _execute_query(self, sql: str) -> None:
        """SQL을 실행하고 결과를 ``table_result`` 에 채운다.

        Args:
            sql: 실행할 SQL 문자열.
        """
        self.table_result.setRowCount(0)
        self.table_result.setColumnCount(0)

        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            if cursor.description:
                col_names = [desc[0] for desc in cursor.description]
                self.table_result.setColumnCount(len(col_names))
                self.table_result.setHorizontalHeaderLabels(col_names)
                for row_idx, row in enumerate(rows):
                    self.table_result.insertRow(row_idx)
                    for col_idx, value in enumerate(row):
                        self.table_result.setItem(
                            row_idx, col_idx, QTableWidgetItem(str(value) if value is not None else "")
                        )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "쿼리 오류", str(exc))

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def set_connection(self, conn) -> None:
        """PostgreSQL 연결 객체를 주입한다.

        Args:
            conn: psycopg2 등의 DB-API 2.0 호환 연결 객체.
        """
        self._conn = conn
