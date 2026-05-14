# -*- coding: utf-8 -*-
"""TimescaleDB 데이터 삭제 탭 컨트롤러 (SRP, QThread Worker 패턴)

삭제 가능 테이블: candles, staging_candles, candles_1m, candles_5m, candles_1h,
                 market_ticks, orderbook_snapshots, technical_indicators,
                 gap_fill_queue, gap_queue

안전장치:
 1. 화이트리스트(_ALLOWED_TABLES) 검증 — SQL 인젝션 방지
 2. 1차 확인 다이얼로그 (대상/조건/예상 건수 표시)
 3. 2차 확인 다이얼로그 (테이블명 재입력 요구)

threading.Thread 사용 금지 — 모든 DB 작업은 QThread Worker 내에서만 실행.
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QMessageBox, QApplication
    )
    from PyQt5.QtCore import QTimer, QDate, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .db_worker import TimescaleWorker, TimescaleWriteWorker, TimescaleVacuumWorker
except ImportError:
    from db_worker import TimescaleWorker, TimescaleWriteWorker, TimescaleVacuumWorker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "delete_tab.ui")

# SQL injection 방지용 테이블 화이트리스트
_ALLOWED_TABLES = frozenset({
    "candles",
    "staging_candles",
    "candles_1m",
    "candles_5m",
    "candles_1h",
    "market_ticks",
    "orderbook_snapshots",   # 수정: orderbook_snaps → orderbook_snapshots
    "technical_indicators",
    "gap_fill_queue",        # 추가: gap_queue 대체 (실제 테이블명)
    "gap_queue",             # 호환성 유지
})

# 건수 조회 쿼리 템플릿 (psycopg2.sql.Identifier로 안전하게 처리)
_COUNT_QUERY_TMPL = "SELECT approximate_row_count((%s)::regclass)::bigint"


def _validate_table(name: str) -> bool:
    """테이블명이 화이트리스트에 있는지 검증합니다 (SQL injection 방지)."""
    return name in _ALLOWED_TABLES


if _HAS_QT:
    class DeleteTab(QWidget):
        """데이터 삭제 탭.

        TimescaleDB 하이퍼테이블 데이터를 조건별로 안전하게 삭제합니다.
        모든 DB 작업은 QThread Worker 내에서만 실행됩니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._write_worker: Optional[TimescaleWriteWorker] = None
            self._vacuum_worker: Optional[TimescaleVacuumWorker] = None
            self._count_worker: Optional[TimescaleWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[DeleteTab] UI 로드 실패: %s", exc)
                self._build_fallback_ui()

            self._setup_ui()
            self._bind_signals()

            # 날짜 기본값: 오늘 기준 30일 전 ~ 오늘
            self._reset_dates()

            # 자동 건수 갱신 타이머 (60초)
            self._timer = QTimer(self)
            self._timer.setInterval(60_000)
            self._timer.timeout.connect(self._refresh_count)

        # ------------------------------------------------------------------
        # 초기 설정
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            """UI 파일 로드 실패 시 최소 레이아웃을 생성합니다."""
            from PyQt5.QtWidgets import (
                QVBoxLayout, QGroupBox, QHBoxLayout, QLabel,
                QComboBox, QRadioButton, QLineEdit, QDateEdit,
                QPushButton, QProgressBar
            )
            layout = QVBoxLayout(self)
            self.comboTable = QComboBox()
            # gap_queue는 gap_fill_queue로 대체됨. 단, 화이트리스트에는 하위 호환성을
            # 위해 남겨 두었으므로 (이미 gap_queue 테이블이 있는 환경 지원),
            # UI 드롭다운에는 표시하지 않는다.
            _ui_tables = sorted(_ALLOWED_TABLES - {"gap_queue"})
            for t in _ui_tables:
                self.comboTable.addItem(t)
            self.comboTable.addItem("ALL (전체 테이블)")
            layout.addWidget(self.comboTable)

            self.radioAll         = QRadioButton("전체 삭제")
            self.radioBySymbol    = QRadioButton("심볼별 삭제")
            self.radioByDateRange = QRadioButton("날짜 범위 삭제")
            self.radioAll.setChecked(True)
            for r in (self.radioAll, self.radioBySymbol, self.radioByDateRange):
                layout.addWidget(r)

            self.editSymbol = QLineEdit()
            self.dateFrom   = QDateEdit()
            self.dateTo     = QDateEdit()
            layout.addWidget(self.editSymbol)
            layout.addWidget(self.dateFrom)
            layout.addWidget(self.dateTo)

            self.labelRecordCount = QLabel("레코드 수: -")
            self.btnRefreshCount  = QPushButton("🔄 건수 새로고침")
            self.labelWarning     = QLabel("⚠️ 삭제된 데이터는 복구할 수 없습니다.")
            self.btnDelete        = QPushButton("🗑️ 선택 데이터 삭제")
            self.btnVacuum        = QPushButton("⚡ VACUUM 실행")
            self.progressDelete   = QProgressBar()
            self.labelResult      = QLabel("")

            for w in (self.labelRecordCount, self.btnRefreshCount,
                      self.labelWarning, self.btnDelete, self.btnVacuum,
                      self.progressDelete, self.labelResult):
                layout.addWidget(w)

        def _setup_ui(self) -> None:
            """위젯 초기 상태를 설정합니다."""
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(False)
                pb.setMaximum(0)  # 무한 스피너 모드

            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setText("")

        def _reset_dates(self) -> None:
            """날짜 범위를 오늘 기준 30일 전 ~ 오늘로 초기화합니다."""
            today = QDate.currentDate()
            df = getattr(self, "dateFrom", None)
            dt = getattr(self, "dateTo",   None)
            if df is not None:
                df.setDate(today.addDays(-30))
            if dt is not None:
                dt.setDate(today)

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _bind_signals(self) -> None:
            """버튼 및 라디오 버튼 시그널을 슬롯에 연결합니다."""
            btn_delete = getattr(self, "btnDelete",       None)
            btn_vacuum = getattr(self, "btnVacuum",       None)
            btn_count  = getattr(self, "btnRefreshCount", None)
            combo      = getattr(self, "comboTable",      None)

            if btn_delete is not None:
                btn_delete.clicked.connect(self._on_btn_delete_clicked)
            if btn_vacuum is not None:
                btn_vacuum.clicked.connect(self._on_btn_vacuum_clicked)
            if btn_count is not None:
                btn_count.clicked.connect(self._refresh_count)
            if combo is not None:
                combo.currentTextChanged.connect(self._on_table_changed)

            # 라디오 버튼 → 필드 활성화 토글
            for radio_name, handler in (
                ("radioAll",         self._on_radio_all),
                ("radioBySymbol",    self._on_radio_symbol),
                ("radioByDateRange", self._on_radio_daterange),
            ):
                radio = getattr(self, radio_name, None)
                if radio is not None:
                    radio.toggled.connect(handler)

        # ------------------------------------------------------------------
        # 라디오 버튼 핸들러
        # ------------------------------------------------------------------

        @pyqtSlot(bool)
        def _on_radio_all(self, checked: bool) -> None:
            if not checked:
                return
            self._set_symbol_enabled(False)
            self._set_date_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_symbol(self, checked: bool) -> None:
            if not checked:
                return
            self._set_symbol_enabled(True)
            self._set_date_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_daterange(self, checked: bool) -> None:
            if not checked:
                return
            self._set_symbol_enabled(False)
            self._set_date_enabled(True)

        def _set_symbol_enabled(self, enabled: bool) -> None:
            for name in ("editSymbol", "labelSymbol"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        def _set_date_enabled(self, enabled: bool) -> None:
            for name in ("dateFrom", "dateTo", "labelDateFrom", "labelDateTo"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        # ------------------------------------------------------------------
        # 테이블 변경 핸들러
        # ------------------------------------------------------------------

        @pyqtSlot(str)
        def _on_table_changed(self, table_text: str) -> None:
            """테이블 변경 시 건수를 자동으로 갱신합니다."""
            self._refresh_count()

        # ------------------------------------------------------------------
        # 건수 조회
        # ------------------------------------------------------------------

        def _refresh_count(self) -> None:
            """선택된 테이블의 레코드 수를 백그라운드에서 조회합니다."""
            table_name = self._get_selected_table()
            if table_name is None:
                return  # ALL 선택 시 건수 조회 생략

            if self._count_worker and self._count_worker.isRunning():
                return

            lbl = getattr(self, "labelRecordCount", None)
            if lbl is not None:
                lbl.setText("레코드 수: 조회 중...")

            query = _COUNT_QUERY_TMPL
            self._count_worker = TimescaleWorker(self._conn_params, query, (table_name,))
            self._count_worker.finished.connect(self._on_count_ready)
            self._count_worker.error.connect(self._on_count_error)
            self._count_worker.start()

        @pyqtSlot(object)
        def _on_count_ready(self, rows) -> None:
            lbl = getattr(self, "labelRecordCount", None)
            if lbl is None:
                return
            count = rows[0][0] if rows else 0
            lbl.setText(f"레코드 수: {count:,} 건")

        @pyqtSlot(str)
        def _on_count_error(self, msg: str) -> None:
            lbl = getattr(self, "labelRecordCount", None)
            if lbl is not None:
                lbl.setText("레코드 수: 조회 실패")

        # ------------------------------------------------------------------
        # 삭제 버튼 핸들러
        # ------------------------------------------------------------------

        def _on_btn_delete_clicked(self) -> None:
            """삭제 확인 다이얼로그 표시 후 Worker를 실행합니다.

            안전장치:
            1. 삭제 대상/조건/예상 건수를 먼저 표시합니다.
            2. 첫 번째 확인 → Yes 선택 시 → 두 번째 확인 (테이블명 재입력)을 거칩니다.
            3. 두 번째 확인까지 통과해야만 실제 삭제가 실행됩니다.
            """
            table_name = self._get_selected_table()
            sql, params, desc = self._build_delete_sql(table_name)
            if sql is None:
                return

            # 현재 레코드 수 표시
            lbl = getattr(self, "labelRecordCount", None)
            count_str = lbl.text() if lbl else "?"

            # 1차 확인
            ret = QMessageBox.warning(
                self,
                "⚠️ 삭제 1차 확인",
                (
                    f"아래 데이터를 삭제하려 합니다.\n\n"
                    f"{desc}\n"
                    f"현재 레코드 수: {count_str}\n\n"
                    "❗ 삭제된 데이터는 복구할 수 없습니다!\n\n"
                    "계속 진행하시겠습니까?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return

            # 2차 확인 (테이블명 입력)
            from PyQt5.QtWidgets import QInputDialog
            target_name = table_name or "ALL"
            input_val, ok = QInputDialog.getText(
                self,
                "🔒 삭제 2차 확인 (안전장치)",
                (
                    f"정말로 삭제합니다.\n\n"
                    f"아래 박스에 테이블명 '{target_name}' 을(를) 정확히 입력하세요:"
                ),
            )
            if not ok or input_val.strip() != target_name:
                QMessageBox.information(
                    self,
                    "취소됨",
                    "입력한 테이블명이 일치하지 않습니다. 삭제가 취소되었습니다.",
                )
                return

            self._start_delete(sql, params)

        def _get_selected_table(self) -> Optional[str]:
            """현재 선택된 테이블명을 반환합니다. ALL 선택 시 None."""
            combo = getattr(self, "comboTable", None)
            if combo is None:
                return None
            text = combo.currentText().strip()
            if text.startswith("ALL"):
                return None
            return text if _validate_table(text) else None

        def _build_delete_sql(self, table_name: Optional[str]):
            """선택된 조건에 맞는 DELETE SQL을 생성합니다.

            Returns:
                (sql, params, desc) 또는 (None, None, None) if invalid
            """
            # ALL 선택 시 전체 테이블 순차 삭제 불가능 — 단일 쿼리로만 지원
            if table_name is None:
                # ALL 선택은 전체 테이블 전체 삭제
                return (
                    None, None,
                    "ALL 선택: 개별 테이블을 선택 후 삭제하세요."
                )

            if not _validate_table(table_name):
                QMessageBox.warning(self, "오류", f"허용되지 않는 테이블명: {table_name}")
                return None, None, None

            radio_symbol    = getattr(self, "radioBySymbol",    None)
            radio_daterange = getattr(self, "radioByDateRange", None)

            by_symbol    = radio_symbol    is not None and radio_symbol.isChecked()
            by_daterange = radio_daterange is not None and radio_daterange.isChecked()

            if by_symbol:
                edit = getattr(self, "editSymbol", None)
                symbol = edit.text().strip() if edit is not None else ""
                if not symbol:
                    QMessageBox.warning(self, "입력 오류", "심볼을 입력하세요 (예: KRW-BTC)")
                    return None, None, None
                # psycopg2.sql.Identifier로 테이블명을 안전하게 처리
                from psycopg2 import sql as pgsql
                sql    = pgsql.SQL("DELETE FROM {} WHERE symbol = %s").format(
                    pgsql.Identifier(table_name)
                )
                params = (symbol,)
                desc   = f"테이블: {table_name}\n심볼: {symbol}"
            elif by_daterange:
                df = getattr(self, "dateFrom", None)
                dt = getattr(self, "dateTo",   None)
                if df is None or dt is None:
                    return None, None, None
                date_from = df.date().toString("yyyy-MM-dd")
                date_to   = dt.date().toString("yyyy-MM-dd")
                from psycopg2 import sql as pgsql
                sql    = pgsql.SQL(
                    "DELETE FROM {} "
                    "WHERE time >= %s::date AND time < (%s::date + interval '1 day')"
                ).format(pgsql.Identifier(table_name))
                params = (date_from, date_to)
                desc   = f"테이블: {table_name}\n기간: {date_from} ~ {date_to}"
            else:
                # 전체 삭제
                from psycopg2 import sql as pgsql
                sql    = pgsql.SQL("DELETE FROM {}").format(pgsql.Identifier(table_name))
                params = ()
                desc   = f"테이블: {table_name}\n범위: 전체"

            return sql, params, desc

        def _start_delete(self, sql, params: tuple) -> None:
            """삭제 Worker를 시작합니다. sql은 str 또는 psycopg2.sql.Composable."""
            if self._write_worker and self._write_worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 삭제 작업이 진행 중입니다.")
                return

            self._set_busy(True)
            self._write_worker = TimescaleWriteWorker(
                self._conn_params, sql, params if params else None
            )
            self._write_worker.finished.connect(self._on_delete_finished)
            self._write_worker.error.connect(self._on_delete_error)
            self._write_worker.start()

        # ------------------------------------------------------------------
        # VACUUM 버튼 핸들러
        # ------------------------------------------------------------------

        def _on_btn_vacuum_clicked(self) -> None:
            """VACUUM Worker를 시작합니다."""
            if self._vacuum_worker and self._vacuum_worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 VACUUM 작업이 진행 중입니다.")
                return

            table_name = self._get_selected_table() or ""
            self._set_busy(True)
            self._vacuum_worker = TimescaleVacuumWorker(self._conn_params, table_name)
            self._vacuum_worker.finished.connect(self._on_vacuum_finished)
            self._vacuum_worker.error.connect(self._on_delete_error)
            self._vacuum_worker.start()

        # ------------------------------------------------------------------
        # Worker 완료 슬롯
        # ------------------------------------------------------------------

        @pyqtSlot(int)
        def _on_delete_finished(self, rows: int) -> None:
            """삭제 완료 시 결과를 표시합니다."""
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #27AE60; font-weight: bold;")
                lbl.setText(f"✅ 삭제 완료: {rows:,} 건 삭제됨")
            self._refresh_count()

        @pyqtSlot(str)
        def _on_vacuum_finished(self, msg: str) -> None:
            """VACUUM 완료 시 결과를 표시합니다."""
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #2980B9; font-weight: bold;")
                lbl.setText(f"✅ {msg}")

        @pyqtSlot(str)
        def _on_delete_error(self, msg: str) -> None:
            """오류 발생 시 빨간색으로 메시지를 표시합니다."""
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #E74C3C; font-weight: bold;")
                lbl.setText(f"🔴 오류: {msg[:120]}")
            logger.warning("[DeleteTab] 작업 오류: %s", msg)

        # ------------------------------------------------------------------
        # 진행 표시 유틸리티
        # ------------------------------------------------------------------

        def _set_busy(self, busy: bool) -> None:
            """진행 바 표시 토글 및 버튼 활성화 상태 변경."""
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)

            for btn_name in ("btnDelete", "btnVacuum", "btnRefreshCount"):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.setEnabled(not busy)

            if busy:
                lbl = getattr(self, "labelResult", None)
                if lbl is not None:
                    lbl.setStyleSheet("")
                    lbl.setText("⏳ 작업 진행 중...")

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 60_000) -> None:
            """건수 자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
            self._timer.setInterval(max(10_000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            self._refresh_count()

        def stop_updates(self) -> None:
            """건수 자동 갱신 중지."""
            self._timer.stop()

        def closeEvent(self, event) -> None:
            """위젯 닫힘 시 타이머와 Worker를 정리합니다."""
            self._timer.stop()
            for worker in (self._write_worker, self._vacuum_worker, self._count_worker):
                if worker is not None and worker.isRunning():
                    worker.quit()
                    worker.wait(2000)
            super().closeEvent(event)

else:
    class DeleteTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None):
            pass

        def start_updates(self, interval_ms: int = 60_000) -> None:
            pass

        def stop_updates(self) -> None:
            pass
