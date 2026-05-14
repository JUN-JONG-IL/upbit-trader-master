#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""성능 메트릭 탭 컨트롤러 (QThread Worker 패턴)

타이머 주기: 1초 → 10초 (메인스레드 블로킹 근본 수정)
psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
"""

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QProgressBar
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

_UI_PATH = os.path.join(os.path.dirname(__file__), "performance_tab.ui")

# 수집할 pg_stat_database 메트릭 정의: (표시명, 컬럼명, 단위, 목표)
_METRICS = [
    ("캐시 히트 블록",    "blks_hit",     "블록",  ">99%"),
    ("디스크 읽기 블록",  "blks_read",    "블록",  "<1%"),
    ("튜플 페치",         "tup_fetched",  "튜플",  "-"),
    ("튜플 삽입",         "tup_inserted", "튜플",  "-"),
    ("튜플 수정",         "tup_updated",  "튜플",  "-"),
    ("튜플 삭제",         "tup_deleted",  "튜플",  "-"),
    ("데드락",            "deadlocks",    "건",    "0"),
    ("임시 파일",         "temp_files",   "개",    "0"),
    ("임시 바이트",       "temp_bytes",   "bytes", "0"),
]

_COLS = ", ".join(col for _, col, _, _ in _METRICS)
_PERF_QUERY = f"""
    SELECT {_COLS}
    FROM pg_stat_database
    WHERE datname = current_database();
"""


class PerformanceTab(QWidget if _HAS_QT else object):
    """성능 메트릭 탭.

    PostgreSQL/TimescaleDB 데이터베이스 성능 지표를
    10초마다 자동으로 갱신하여 표시합니다 (기존 1초에서 수정).
    psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
    """

    def __init__(self, db_conn=None, conn_params: Optional[Dict] = None,
                 db_name: Optional[str] = None, parent=None):
        """초기화.

        Args:
            db_conn: (레거시) 이미 생성된 psycopg2 연결 객체
            conn_params: DB 연결 파라미터 딕셔너리 (신규 방식)
            db_name: 모니터링 대상 데이터베이스 이름 (None이면 current_database() 사용)
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
            logger.warning("[PerformanceTab] UI 로드 실패: %s", exc)

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
        tbl = getattr(self, "table_performance", None)
        if tbl is None:
            return
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["메트릭", "현재값", "단위", "목표"])
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
        self._worker = TimescaleWorker(self._conn_params, _PERF_QUERY)
        self._worker.finished.connect(self._on_data_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(object)
    def _on_data_ready(self, rows) -> None:
        """Worker 완료 시 메인스레드에서 UI를 갱신합니다."""
        from datetime import datetime
        tbl = getattr(self, "table_performance", None)
        if tbl is None:
            return

        row = rows[0] if rows else None
        table_rows = []
        blks_hit  = 0
        blks_read = 0

        if row:
            for idx, (label, col, unit, target) in enumerate(_METRICS):
                value = row[idx] if idx < len(row) and row[idx] is not None else 0
                table_rows.append((label, str(value), unit, target))
                if col == "blks_hit":
                    blks_hit = int(value)
                elif col == "blks_read":
                    blks_read = int(value)

        tbl.setRowCount(len(table_rows))
        for row_idx, (metric, value, unit, target) in enumerate(table_rows):
            tbl.setItem(row_idx, 0, QTableWidgetItem(metric))
            tbl.setItem(row_idx, 1, QTableWidgetItem(value))
            tbl.setItem(row_idx, 2, QTableWidgetItem(unit))
            tbl.setItem(row_idx, 3, QTableWidgetItem(target))

        # 캐시 히트율 프로그레스바 갱신
        self._update_cache_bar(blks_hit, blks_read)

        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            now = datetime.now().strftime("%H:%M:%S")
            lbl.setText(f"✅ 마지막 갱신: {now}")
            lbl.setStyleSheet("color: #27AE60; font-size: 8pt;")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        """Worker 오류 시 메인스레드에서 상태를 표시합니다."""
        tbl = getattr(self, "table_performance", None)
        if tbl is not None:
            tbl.setRowCount(1)
            tbl.setItem(0, 0, QTableWidgetItem(f"🔴 오류: {msg[:80]}"))
            for col in range(1, tbl.columnCount()):
                tbl.setItem(0, col, QTableWidgetItem(""))
        lbl = getattr(self, "_lbl_status", None)
        if lbl:
            lbl.setText(f"🔴 오류 — {msg[:100]}")
            lbl.setStyleSheet("color: #E74C3C; font-size: 8pt;")
        logger.debug("[PerformanceTab] Worker 오류: %s", msg)

    def _update_cache_bar(self, blks_hit: int, blks_read: int) -> None:
        """캐시 히트율 프로그레스바를 갱신합니다."""
        bar = getattr(self, "progressCache", None)
        if bar is None:
            return
        total = blks_hit + blks_read
        ratio = int(blks_hit / total * 100) if total > 0 else 0
        bar.setValue(ratio)
        if ratio >= 99:
            bar.setStyleSheet("QProgressBar::chunk { background-color: #27AE60; }")
        elif ratio >= 95:
            bar.setStyleSheet("QProgressBar::chunk { background-color: #F39C12; }")
        else:
            bar.setStyleSheet("QProgressBar::chunk { background-color: #E74C3C; }")

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
