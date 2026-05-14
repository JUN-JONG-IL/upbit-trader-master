#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
이벤트 저장소(CQRS) 탭 모듈.

PostgreSQL에 저장된 도메인 이벤트 목록을 조회하고
``table_events`` 위젯에 표시한다.
"""

import os

# PostgreSQL Primary 기본 포트 (config.yaml POSTGRES_PRIMARY.PORT 또는 POSTGRES_PORT 환경변수로 재정의 가능)
_DEFAULT_POSTGRES_PORT: int = 5433

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


class EventStoreTab(QWidget):
    """이벤트 저장소(CQRS) 탭.

    5초마다 이벤트 테이블을 폴링하여
    ``table_events`` 위젯을 갱신한다.
    """

    # 폴링 주기 (밀리초)
    _POLL_INTERVAL_MS: int = 5_000

    def __init__(self, parent=None, conn_params=None):
        """위젯을 초기화하고 UI 파일을 로드한다."""
        super().__init__(parent)
        self._conn_params = conn_params or {}

        ui_path = os.path.join(os.path.dirname(__file__), "event_store_tab.ui")
        uic.loadUi(ui_path, self)

        self._setup_table()
        self._setup_timer()

    # ------------------------------------------------------------------
    # 초기화 헬퍼
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """테이블 기본 설정을 지정한다."""
        header = self.table_events.horizontalHeader()
        header.setStretchLastSection(True)
        self.table_events.setEditTriggers(self.table_events.NoEditTriggers)
        self.table_events.setSelectionBehavior(self.table_events.SelectRows)

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
        """이벤트 저장소 데이터를 갱신한다."""
        self.table_events.setRowCount(0)
        params = self._conn_params
        host = params.get("host", "localhost")
        db = params.get("database", "upbit_trades")
        user = params.get("user", "postgres")
        password = params.get("password", "")
        try:
            import importlib
            psycopg2 = importlib.import_module("psycopg2")
            port = int(params.get("port", os.getenv("POSTGRES_PORT", str(_DEFAULT_POSTGRES_PORT))))
            conn = psycopg2.connect(
                host=host, port=port, database=db,
                user=user, password=password, connect_timeout=3
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT event_type, aggregate_id, created_at, payload "
                "FROM order_events ORDER BY created_at DESC LIMIT 100"
            )
            rows = cur.fetchall()
            if rows:
                labels = ["이벤트 타입", "집계 ID", "생성 시각", "페이로드"]
                self.table_events.setColumnCount(len(labels))
                self.table_events.setHorizontalHeaderLabels(labels)
                for row in rows:
                    r = self.table_events.rowCount()
                    self.table_events.insertRow(r)
                    for c, val in enumerate(row):
                        from PyQt5.QtWidgets import QTableWidgetItem
                        text = str(val)[:100] if val is not None else "-"
                        self.table_events.setItem(r, c, QTableWidgetItem(text))
            cur.close()
            conn.close()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("이벤트 스토어 조회 실패: %s", exc)

    # ------------------------------------------------------------------
    # 생명주기
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        """위젯이 닫힐 때 타이머를 정지한다."""
        self._timer.stop()
        super().closeEvent(event)
