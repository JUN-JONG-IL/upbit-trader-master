#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래 원장(복식부기) 탭 모듈.

PostgreSQL에 저장된 복식부기 거래 내역을 조회하고
``table_ledger`` 위젯에 표시한다.
"""

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


class LedgerTab(QWidget):
    """거래 원장(복식부기) 탭.

    10초마다 원장 테이블을 폴링하여
    ``table_ledger`` 위젯을 갱신한다.
    """

    # 폴링 주기 (밀리초)
    _POLL_INTERVAL_MS: int = 10_000

    def __init__(self, parent=None, conn_params=None):
        """위젯을 초기화하고 UI 파일을 로드한다."""
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "ledger_tab.ui")
        uic.loadUi(ui_path, self)

        self._setup_table()
        self._setup_timer()

    # ------------------------------------------------------------------
    # 초기화 헬퍼
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """테이블 기본 설정을 지정한다."""
        header = self.table_ledger.horizontalHeader()
        header.setStretchLastSection(True)
        self.table_ledger.setEditTriggers(self.table_ledger.NoEditTriggers)
        self.table_ledger.setSelectionBehavior(self.table_ledger.SelectRows)

    def _setup_timer(self) -> None:
        """주기적 갱신 타이머를 생성하고 시작한다."""
        self._timer = QTimer(self)
        self._timer.setInterval(self._POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # ------------------------------------------------------------------
    # 데이터 갱신
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """거래 원장 데이터를 갱신한다."""
        self.table_ledger.setRowCount(0)
        params = self._conn_params
        host = params.get("host", "localhost")
        db = params.get("database", "upbit_trades")
        user = params.get("user", "postgres")
        password = params.get("password", "")
        try:
            import importlib
            psycopg2 = importlib.import_module("psycopg2")
            conn = psycopg2.connect(
                host=host, port=5433, database=db,
                user=user, password=password, connect_timeout=3
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT entry_date, account, debit, credit, description "
                "FROM ledger_entries ORDER BY entry_date DESC LIMIT 100"
            )
            rows = cur.fetchall()
            if rows:
                labels = ["날짜", "계정", "차변", "대변", "설명"]
                self.table_ledger.setColumnCount(len(labels))
                self.table_ledger.setHorizontalHeaderLabels(labels)
                for row in rows:
                    r = self.table_ledger.rowCount()
                    self.table_ledger.insertRow(r)
                    for c, val in enumerate(row):
                        from PyQt5.QtWidgets import QTableWidgetItem
                        self.table_ledger.setItem(r, c, QTableWidgetItem(str(val) if val is not None else "-"))
            cur.close()
            conn.close()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("거래 원장 조회 실패: %s", exc)

    # ------------------------------------------------------------------
    # 생명주기
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        """위젯이 닫힐 때 타이머를 정지한다."""
        self._timer.stop()
        super().closeEvent(event)
