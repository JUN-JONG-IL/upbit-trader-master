# -*- coding: utf-8 -*-
"""TimescaleDB 저장 데이터 탭 - SQL 편집기 + 하이퍼테이블 저장 현황 (QThread Worker 패턴)

psycopg2.connect() 는 TimescaleQueryWorker(QThread) 내부에서만 실행됩니다.
커서 description에서 컬럼명을 자동 추출하므로 하드코딩 없이 동적 매핑됩니다.
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .db_worker import TimescaleQueryWorker
except ImportError:
    from db_worker import TimescaleQueryWorker  # type: ignore[no-redef]

# DataBrowserWidget 로드 시도 (필터/정렬/페이지네이션)
_DATA_BROWSER = None
try:
    _widget_dir = str(Path(__file__).resolve().parents[3] / "ui" / "widgets")
    if _widget_dir not in sys.path:
        sys.path.insert(0, _widget_dir)
    from data_browser import DataBrowserWidget
    _DATA_BROWSER = DataBrowserWidget
except Exception as _e:
    logging.getLogger(__name__).debug(
        "[StorageTab] DataBrowserWidget 로드 실패 (폴백 QTableWidget 사용): %s", _e
    )

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "storage_tab.ui")

# 기본 저장 현황 쿼리 (하이퍼테이블별 행 수·크기)
_DEFAULT_QUERY = """\
SELECT
    hypertable_name                                          AS "테이블",
    approximate_row_count(
        format('%I', hypertable_name)::regclass
    )::bigint                                               AS "행수(근사)",
    pg_size_pretty(
        hypertable_size(format('%I', hypertable_name)::regclass)
    )                                                       AS "총크기"
FROM timescaledb_information.hypertables
ORDER BY hypertable_name;
"""


if _HAS_QT:
    class StorageTab(QWidget):
        """저장 데이터 탭.

        하이퍼테이블 저장 현황과 SQL 편집기를 제공합니다.
        TimescaleQueryWorker(QThread) 내부에서만 psycopg2.connect()가 실행됩니다.
        DataBrowserWidget이 로드되면 필터/정렬/페이지네이션/드릴다운을 제공합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[TimescaleQueryWorker] = None
            self._has_browser: bool = _DATA_BROWSER is not None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[StorageTab] UI 로드 실패: %s", exc)

            self._setup_widgets()

            # btnExecute 클릭 → 편집기 SQL 실행
            btn = getattr(self, "btnExecute", None)
            if btn is not None:
                btn.clicked.connect(self._run_custom_query)

            # 자동 갱신 타이머 (30초) — __init__에서 자동 시작 안 함
            self._timer = QTimer(self)
            self._timer.setInterval(30_000)
            self._timer.timeout.connect(self._update)

        # ------------------------------------------------------------------
        # 내부 설정
        # ------------------------------------------------------------------

        def _setup_widgets(self) -> None:
            """기본 쿼리 텍스트 및 결과 위젯 초기 설정."""
            editor = getattr(self, "sqlEditor", None)
            if editor is not None:
                editor.setPlainText(_DEFAULT_QUERY)

            # DataBrowserWidget 사용 가능 시 tableResult를 교체
            if self._has_browser:
                result_gb = getattr(self, "groupBox_result", None)
                if result_gb is not None:
                    # groupBox_result 레이아웃에서 tableResult를 DataBrowserWidget으로 교체
                    from PyQt5.QtWidgets import QVBoxLayout
                    layout = result_gb.layout()
                    # 기존 tableResult 제거
                    tbl_old = getattr(self, "tableResult", None)
                    if tbl_old is not None and layout is not None:
                        layout.removeWidget(tbl_old)
                        tbl_old.setVisible(False)
                    # DataBrowserWidget 삽입
                    self._browser = _DATA_BROWSER()
                    if layout is not None:
                        layout.insertWidget(0, self._browser)
                    self.tableResult = None  # 더 이상 직접 사용 안 함
                else:
                    self._browser = None
            else:
                self._browser = None
                tbl = getattr(self, "tableResult", None)
                if tbl is not None:
                    tbl.setAlternatingRowColors(True)
                    hdr = tbl.horizontalHeader()
                    hdr.setSectionResizeMode(QHeaderView.Stretch)

        # ------------------------------------------------------------------
        # 갱신 로직 (Worker 패턴)
        # ------------------------------------------------------------------

        def _update(self) -> None:
            """기본 저장 현황 쿼리를 자동 실행합니다."""
            self._start_worker(_DEFAULT_QUERY)

        def _run_custom_query(self) -> None:
            """SQL 편집기의 내용을 Worker로 실행합니다."""
            editor = getattr(self, "sqlEditor", None)
            if editor is None:
                return
            sql = editor.toPlainText().strip()
            if sql:
                self._start_worker(sql)

        def _start_worker(self, sql: str) -> None:
            """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
            if self._worker and self._worker.isRunning():
                return
            lbl = getattr(self, "labelRowCount", None)
            if lbl:
                lbl.setStyleSheet("color: #F59E0B;")
                lbl.setText("⏳ 조회 중...")
            self._worker = TimescaleQueryWorker(self._conn_params, sql)
            self._worker.finished.connect(self._on_data_ready)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        @pyqtSlot(list, list)
        def _on_data_ready(self, headers: list, rows: list) -> None:
            """Worker 완료 시 메인스레드에서 UI를 갱신합니다.

            cursor.description에서 추출한 헤더를 그대로 사용하므로
            컬럼 수 불일치로 인한 tuple index out of range가 발생하지 않습니다.
            """
            from datetime import datetime
            lbl = getattr(self, "labelRowCount", None)

            if self._has_browser and self._browser is not None and hasattr(self._browser, "set_data"):
                self._browser.set_data(headers, rows)
                if lbl:
                    now = datetime.now().strftime("%H:%M:%S")
                    lbl.setStyleSheet("color: #27AE60;")
                    lbl.setText(
                        f"✅ {len(rows):,}행 ({len(headers)}컬럼)  |  갱신: {now}"
                        " — 더블클릭: 행 상세 보기"
                    )
            else:
                # 폴백: 단순 QTableWidget
                tbl = getattr(self, "tableResult", None)
                if tbl is None:
                    return
                n_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
                tbl.setColumnCount(n_cols)
                # cursor.description 기반 동적 헤더 (tuple index out of range 방지)
                if headers:
                    tbl.setHorizontalHeaderLabels(headers)
                else:
                    tbl.setHorizontalHeaderLabels([f"열{i+1}" for i in range(n_cols)])
                tbl.setRowCount(len(rows))

                for r, row in enumerate(rows):
                    for c, val in enumerate(row):
                        tbl.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

                if lbl:
                    now = datetime.now().strftime("%H:%M:%S")
                    lbl.setStyleSheet("color: #27AE60;")
                    lbl.setText(f"✅ 결과: {len(rows):,}행  |  갱신: {now}")

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            """Worker 오류 시 메인스레드에서 상태를 표시합니다."""
            lbl = getattr(self, "labelRowCount", None)
            if lbl:
                lbl.setStyleSheet("color: #E74C3C;")
                hint = ""
                if "does not exist" in msg.lower():
                    hint = " → 테이블/함수가 없습니다. TimescaleDB 버전 확인 필요."
                lbl.setText(f"🔴 오류: {msg[:80]}{hint}")
            logger.debug("[StorageTab] Worker 오류: %s", msg)

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 30_000) -> None:
            """자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
            self._timer.setInterval(max(5000, int(interval_ms)))
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
    class StorageTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 30_000) -> None: pass
        def stop_updates(self) -> None: pass
