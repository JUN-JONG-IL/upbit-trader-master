#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
이벤트 저장소 관리 다이얼로그 모듈.

PostgreSQL에 저장된 도메인 이벤트를 조회·표시하는
모달 다이얼로그를 제공한다.
"""

import os

try:
    from PyQt5.QtWidgets import QDialog, QTableWidgetItem, QMessageBox
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


class EventStoreDialog(QDialog):
    """이벤트 저장소 관리 다이얼로그.

    ``btn_refresh`` 클릭 시 이벤트 목록을 다시 조회하고
    ``btn_close`` 클릭 시 다이얼로그를 닫는다.

    Example::

        dlg = EventStoreDialog(parent=self)
        dlg.set_connection(conn)
        dlg.exec_()
    """

    # 한 번에 조회할 최대 이벤트 수
    _MAX_ROWS: int = 10_000

    # 이벤트 조회 SQL
    _QUERY = """
        SELECT event_id, event_type, aggregate_id, occurred_at
        FROM events
        ORDER BY occurred_at DESC
        LIMIT %(limit)s;
    """

    def __init__(self, parent=None) -> None:
        """다이얼로그를 초기화하고 UI 파일을 로드한다."""
        super().__init__(parent)

        ui_path = os.path.join(os.path.dirname(__file__), "event_store_dialog.ui")
        uic.loadUi(ui_path, self)

        self._conn = None
        self._setup_table()
        self._connect_signals()

    # ------------------------------------------------------------------
    # 초기화 헬퍼
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """테이블 기본 설정을 지정한다."""
        header = self.table_events.horizontalHeader()
        header.setStretchLastSection(True)
        self.table_events.setEditTriggers(self.table_events.NoEditTriggers)
        self.table_events.setSelectionBehavior(self.table_events.SelectRows)

    def _connect_signals(self) -> None:
        """버튼 클릭 시그널을 슬롯에 연결한다."""
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        self.btn_close.clicked.connect(self.close)

    # ------------------------------------------------------------------
    # 슬롯
    # ------------------------------------------------------------------

    def _on_refresh_clicked(self) -> None:
        """🔄 새로고침 버튼 클릭 핸들러."""
        if self._conn is None:
            QMessageBox.warning(self, "연결 없음", "PostgreSQL 연결이 설정되지 않았습니다.")
            return

        self._load_events()

    # ------------------------------------------------------------------
    # 데이터 로드
    # ------------------------------------------------------------------

    def _load_events(self) -> None:
        """이벤트 목록을 DB에서 조회하고 테이블을 채운다."""
        self.table_events.setRowCount(0)

        try:
            cur = self._conn.cursor()
            cur.execute(self._QUERY, {"limit": self._MAX_ROWS})
            rows = cur.fetchall()
            for row_idx, row in enumerate(rows):
                self.table_events.insertRow(row_idx)
                for col_idx, value in enumerate(row):
                    self.table_events.setItem(
                        row_idx,
                        col_idx,
                        QTableWidgetItem(str(value) if value is not None else ""),
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "조회 오류", str(exc))

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def set_connection(self, conn) -> None:
        """PostgreSQL 연결 객체를 주입한다.

        Args:
            conn: psycopg2 등의 DB-API 2.0 호환 연결 객체.
        """
        self._conn = conn
