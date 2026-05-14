#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""압축 정책 탭 컨트롤러 (QThread Worker 패턴)

psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
"""

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    def pyqtSlot(*args, **kwargs):  # no-op 폴백
        def decorator(f): return f
        return decorator

try:
    from .db_worker import TimescaleWorker
except ImportError:
    from db_worker import TimescaleWorker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "compression_tab.ui")

_COMPRESSION_QUERY = """
    SELECT
        h.hypertable_name,
        COALESCE(p.config->>'compress_after', '정책 없음') AS policy,
        COUNT(c.chunk_name) FILTER (WHERE c.is_compressed) ::text AS compressed,
        COUNT(c.chunk_name) FILTER (WHERE NOT c.is_compressed) ::text AS uncompressed
    FROM timescaledb_information.hypertables h
    LEFT JOIN timescaledb_information.chunks c
           ON c.hypertable_name = h.hypertable_name
    LEFT JOIN (
        SELECT hypertable_name, config
          FROM timescaledb_information.jobs
         WHERE proc_name = 'policy_compression'
    ) p ON p.hypertable_name = h.hypertable_name
    GROUP BY h.hypertable_name, p.config
    ORDER BY h.hypertable_name;
"""


class CompressionTab(QWidget if _HAS_QT else object):
    """압축 정책 탭.

    각 하이퍼테이블의 압축 정책, 압축된 청크 수, 미압축 청크 수를
    10초마다 자동으로 갱신하여 표시합니다.
    psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
    """

    def __init__(self, db_conn=None, conn_params: Optional[Dict] = None, parent=None):
        """초기화.

        Args:
            db_conn: (레거시) 이미 생성된 psycopg2 연결 객체
            conn_params: DB 연결 파라미터 딕셔너리 (신규 방식)
            parent: 부모 위젯
        """
        if not _HAS_QT:
            raise RuntimeError("PyQt5가 설치되지 않았습니다.")
        super().__init__(parent)
        self._conn_params: Dict = conn_params or {}
        self._worker: Optional[TimescaleWorker] = None

        try:
            uic.loadUi(_UI_PATH, self)
        except Exception as exc:
            logger.warning("[CompressionTab] UI 로드 실패: %s", exc)

        self._setup_table()
        self._add_status_label()

        # 자동 갱신 타이머 (10초) — __init__에서 자동 시작 안 함
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)

    # ------------------------------------------------------------------
    # 내부 설정
    # ------------------------------------------------------------------

    def _setup_table(self):
        """테이블 위젯 초기 설정."""
        tbl = getattr(self, "table_compression", None)
        if tbl is None:
            return
        header = tbl.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        tbl.setAlternatingRowColors(True)

    def _add_status_label(self) -> None:
        """마지막 갱신 시각/오류를 표시하는 상태 라벨을 레이아웃 하단에 추가합니다."""
        from PyQt5.QtWidgets import QLabel, QHBoxLayout
        layout = self.layout()
        if layout is None:
            return
        row = QHBoxLayout()
        self._lbl_status = QLabel("상태: 대기 중")
        self._lbl_status.setStyleSheet("color: #7F8C8D; font-size: 8pt;")
        row.addWidget(self._lbl_status)
        row.addStretch()
        layout.addLayout(row)

    # ------------------------------------------------------------------
    # 갱신 로직 (Worker 패턴)
    # ------------------------------------------------------------------

    def _update(self):
        """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
        if self._worker and self._worker.isRunning():
            return
        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            lbl.setText("상태: 조회 중...")
        self._worker = TimescaleWorker(self._conn_params, _COMPRESSION_QUERY)
        self._worker.finished.connect(self._on_data_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(object)
    def _on_data_ready(self, rows) -> None:
        """Worker 완료 시 메인스레드에서 UI를 갱신합니다."""
        from datetime import datetime
        tbl = getattr(self, "table_compression", None)
        if tbl is None:
            return
        rows = rows or []
        if not rows:
            tbl.setRowCount(1)
            tbl.setItem(0, 0, QTableWidgetItem("(압축 정책 없음)"))
            for col in range(1, tbl.columnCount()):
                tbl.setItem(0, col, QTableWidgetItem(""))
        else:
            tbl.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                for col_idx, value in enumerate(row):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    tbl.setItem(row_idx, col_idx, item)
        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            now = datetime.now().strftime("%H:%M:%S")
            lbl.setText(f"✅ 마지막 갱신: {now}  |  {len(rows)} 개 테이블")
            lbl.setStyleSheet("color: #27AE60; font-size: 8pt;")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        """Worker 오류 시 메인스레드에서 상태를 표시합니다."""
        tbl = getattr(self, "table_compression", None)
        if tbl is not None:
            tbl.setRowCount(1)
            tbl.setItem(0, 0, QTableWidgetItem(f"🔴 오류: {msg[:80]}"))
            for col in range(1, tbl.columnCount()):
                tbl.setItem(0, col, QTableWidgetItem(""))
        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            lbl.setText(f"🔴 오류 — {msg[:100]}")
            lbl.setStyleSheet("color: #E74C3C; font-size: 8pt;")
        logger.debug("[CompressionTab] Worker 오류: %s", msg)

    # ------------------------------------------------------------------
    # 생명 주기
    # ------------------------------------------------------------------

    def start_updates(self, interval_ms: int = 10_000) -> None:
        """자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
        self._timer.setInterval(max(1000, int(interval_ms)))
        if not self._timer.isActive():
            self._timer.start()
        self._update()

    def stop_updates(self) -> None:
        """자동 갱신 중지."""
        self._timer.stop()

    def closeEvent(self, event):
        """위젯 닫힘 시 타이머와 Worker를 정리합니다."""
        self._timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)
