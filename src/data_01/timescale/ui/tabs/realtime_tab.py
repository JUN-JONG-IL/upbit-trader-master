# -*- coding: utf-8 -*-
"""TimescaleDB 실시간 통신 탭 - 데이터 유입 현황 모니터링 (QThread Worker 패턴)"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .db_worker import TimescaleWorker
except ImportError:
    from db_worker import TimescaleWorker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "realtime_tab.ui")

_INGESTION_QUERY = """
    SELECT
        s.relname,
        GREATEST(
            s.last_autoanalyze, s.last_analyze,
            s.last_autovacuum, s.last_vacuum
        )::text,
        s.n_tup_ins
    FROM pg_stat_user_tables s
    WHERE s.schemaname = 'public'
    ORDER BY s.n_tup_ins DESC
    LIMIT 20;
"""


if _HAS_QT:
    class RealtimeTab(QWidget):
        """실시간 데이터 유입 탭.

        pg_stat_user_tables 기반 삽입 통계를 10초마다 표시합니다.
        psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
        메인스레드 블로킹이 전혀 없습니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            # 이전 삽입 수 저장 (분당 삽입 속도 계산용)
            self._prev_inserts: Dict[str, int] = {}
            self._prev_time: float = time.monotonic()
            self._worker: Optional[TimescaleWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[RealtimeTab] UI 로드 실패: %s", exc)

            self._setup_table()

            # btnClear 클릭 → 테이블 초기화
            btn = getattr(self, "btnClear", None)
            if btn is not None:
                btn.clicked.connect(self._clear_table)

            # 자동 갱신 타이머 (10초) — __init__에서 자동 시작 안 함
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._update)

        # ------------------------------------------------------------------
        # 내부 설정
        # ------------------------------------------------------------------

        def _setup_table(self) -> None:
            """테이블 헤더 설정."""
            tbl = getattr(self, "table_query_log", None)
            if tbl is None:
                return
            tbl.setColumnCount(4)
            tbl.setHorizontalHeaderLabels(["테이블", "최근 변경 시각", "누적 삽입 수", "삽입/분"])
            hdr = tbl.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.Stretch)
            tbl.setAlternatingRowColors(True)

        def _clear_table(self) -> None:
            """테이블 행 전체 삭제."""
            tbl = getattr(self, "table_query_log", None)
            if tbl is not None:
                tbl.setRowCount(0)
            self._prev_inserts.clear()

        # ------------------------------------------------------------------
        # 갱신 로직 (Worker 패턴)
        # ------------------------------------------------------------------

        def _update(self) -> None:
            """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
            if self._worker and self._worker.isRunning():
                return
            self._worker = TimescaleWorker(self._conn_params, _INGESTION_QUERY)
            self._worker.finished.connect(self._on_data_ready)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        @pyqtSlot(object)
        def _on_data_ready(self, rows) -> None:
            """Worker 완료 시 메인스레드에서 UI를 갱신합니다."""
            lbl_qps = getattr(self, "label_qps",     None)
            lbl_lat = getattr(self, "label_latency", None)

            now = time.monotonic()
            dt  = max(now - self._prev_time, 1.0)
            self._prev_time = now

            tbl = getattr(self, "table_query_log", None)
            if tbl is None:
                return

            rows = rows or []
            total_rpm = 0.0
            # 방어적 인덱싱 — tuple index out of range / ValueError 방지
            # 쿼리 반환 컬럼: (relname, last_activity::text, n_tup_ins)
            valid_rows = [r for r in rows if r and len(r) >= 3]
            if len(valid_rows) != len(rows):
                logger.debug(
                    "[RealtimeTab] %d/%d 행이 예상 컬럼 수 미충족 — 건너뜀",
                    len(rows) - len(valid_rows), len(rows)
                )
            tbl.setRowCount(len(valid_rows))

            for i, row in enumerate(valid_rows):
                tname     = row[0] if row[0] is not None else ""
                last_act  = row[1]
                total_ins = int(row[2]) if row[2] is not None else 0
                prev      = self._prev_inserts.get(tname, total_ins)
                delta     = max(0, total_ins - prev)
                rpm       = delta / dt * 60.0
                total_rpm += rpm
                self._prev_inserts[tname] = total_ins

                tbl.setItem(i, 0, QTableWidgetItem(str(tname)))
                tbl.setItem(i, 1, QTableWidgetItem(str(last_act or "-")))
                tbl.setItem(i, 2, QTableWidgetItem(str(total_ins)))
                tbl.setItem(i, 3, QTableWidgetItem(f"{rpm:.1f}"))

            if lbl_qps:
                lbl_qps.setText(f"분당 삽입 합계: {total_rpm:.1f} 행/분")
            if lbl_lat:
                lbl_lat.setText(f"마지막 갱신: {datetime.now().strftime('%H:%M:%S')}")

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            """Worker 오류 시 메인스레드에서 상태를 표시합니다."""
            lbl_qps = getattr(self, "label_qps",     None)
            lbl_lat = getattr(self, "label_latency", None)
            if lbl_qps:
                lbl_qps.setText("🔴 연결 실패")
            if lbl_lat:
                lbl_lat.setText(f"오류: {msg[:80]}")
            tbl = getattr(self, "table_query_log", None)
            if tbl is not None:
                tbl.setRowCount(1)
                tbl.setItem(0, 0, QTableWidgetItem(f"🔴 오류: {msg[:80]}"))
                for col in range(1, tbl.columnCount()):
                    tbl.setItem(0, col, QTableWidgetItem(""))
            logger.debug("[RealtimeTab] Worker 오류: %s", msg)

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

        def closeEvent(self, event) -> None:
            self._timer.stop()
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)
            super().closeEvent(event)

else:
    class RealtimeTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 10_000) -> None: pass
        def stop_updates(self) -> None: pass
