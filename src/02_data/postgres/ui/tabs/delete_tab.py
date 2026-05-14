# -*- coding: utf-8 -*-
"""PostgreSQL 데이터 삭제 탭 (QThread Worker 패턴, 메인스레드 블로킹 없음)

지원 작업:
  - 전체 삭제 (DELETE FROM ... WHERE TRUE)
  - 날짜 범위 삭제
  - 이벤트 타입별 삭제 (events 테이블 전용)
  - VACUUM ANALYZE
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox
    from PyQt5.QtCore import QThread, pyqtSignal, QDate, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "delete_tab.ui")

# SQL injection 방지용 테이블 화이트리스트
_ALLOWED_TABLES = frozenset({
    "events", "executions", "positions",
    "account_ledger", "audit_log", "risk_violations",
})

# 날짜 컬럼 매핑 (테이블별 시간 컬럼명)
_TIME_COLUMN = {
    "events":          "created_at",
    "executions":      "executed_at",
    "positions":       "opened_at",
    "account_ledger":  "created_at",
    "audit_log":       "created_at",
    "risk_violations": "detected_at",
}


def _get_pg_conn(conn_params: dict):
    """psycopg2 연결을 반환합니다. 실패 시 None."""
    try:
        import psycopg2  # type: ignore[import]
        return psycopg2.connect(
            host=conn_params.get("host") or os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(conn_params.get("port") or os.getenv("POSTGRES_PORT", "5432")),
            dbname=conn_params.get("database") or os.getenv("POSTGRES_DB", "upbit_trader"),
            user=conn_params.get("user") or os.getenv("POSTGRES_USER", "admin"),
            password=conn_params.get("password") or os.getenv("POSTGRES_PASSWORD", ""),
            connect_timeout=5,
        )
    except Exception as exc:
        logger.debug("[PG DeleteTab] 연결 실패: %s", exc)
        return None


if _HAS_QT:
    # ------------------------------------------------------------------
    # QThread Worker
    # ------------------------------------------------------------------
    class _PgWriteWorker(QThread):
        """PostgreSQL DELETE/VACUUM Worker."""
        finished = pyqtSignal(int)   # 삭제된 행 수 (VACUUM은 0)
        error    = pyqtSignal(str)

        def __init__(self, conn_params: dict, sql: str, params: tuple = ()):
            super().__init__()
            self._conn_params = conn_params
            self._sql    = sql
            self._params = params

        def run(self):
            try:
                conn = _get_pg_conn(self._conn_params)
                if conn is None:
                    self.error.emit("PostgreSQL 연결 실패 — 환경 변수(POSTGRES_HOST 등) 확인")
                    return
                # VACUUM은 autocommit 필요
                is_vacuum = self._sql.strip().upper().startswith("VACUUM")
                if is_vacuum:
                    conn.autocommit = True
                cur = conn.cursor()
                try:
                    cur.execute(self._sql, self._params or None)
                    if not is_vacuum:
                        conn.commit()
                    self.finished.emit(cur.rowcount if not is_vacuum else 0)
                finally:
                    cur.close()
                    conn.close()
            except Exception as exc:
                self.error.emit(str(exc)[:200])

    class _CountWorker(QThread):
        """레코드 수 조회 Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        def __init__(self, conn_params: dict, table: str):
            super().__init__()
            # 화이트리스트 검증을 __init__에서 수행 (SQL injection 방지)
            if table not in _ALLOWED_TABLES:
                raise ValueError(f"허용되지 않는 테이블: {table!r}")
            self._conn_params = conn_params
            self._table = table

        def run(self):
            try:
                conn = _get_pg_conn(self._conn_params)
                if conn is None:
                    self.error.emit("연결 실패")
                    return
                cur = conn.cursor()
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {self._table}")  # noqa: S608
                    count = cur.fetchone()[0]
                    self.finished.emit(f"레코드 수: {count:,} 건")
                finally:
                    cur.close()
                    conn.close()
            except Exception as exc:
                self.error.emit(str(exc)[:100])

    # ------------------------------------------------------------------
    # 탭 위젯
    # ------------------------------------------------------------------
    class DeleteTab(QWidget):
        """PostgreSQL 데이터 삭제 탭.

        전체 삭제 / 날짜 범위 삭제 / 이벤트 타입별 삭제를 QThread Worker로 실행합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[_PgWriteWorker] = None
            self._count_worker: Optional[_CountWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[PG DeleteTab] UI 로드 실패: %s", exc)
                self._build_fallback_ui()

            self._setup_ui()
            self._bind_signals()
            self._reset_dates()

        # ------------------------------------------------------------------
        # UI 초기화
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            from PyQt5.QtWidgets import (
                QVBoxLayout, QLabel, QComboBox, QRadioButton,
                QLineEdit, QDateEdit, QPushButton, QProgressBar,
            )
            layout = QVBoxLayout(self)
            self.comboTable      = QComboBox()
            for t in sorted(_ALLOWED_TABLES):
                self.comboTable.addItem(t)
            self.radioAll        = QRadioButton("전체 삭제")
            self.radioByDateRange= QRadioButton("날짜 범위 삭제")
            self.radioByEventType= QRadioButton("이벤트 타입별 삭제")
            self.radioAll.setChecked(True)
            self.dateFrom        = QDateEdit()
            self.dateTo          = QDateEdit()
            self.editEventType   = QLineEdit()
            self.labelRecordCount= QLabel("레코드 수: -")
            self.btnRefreshCount = QPushButton("🔄 건수 새로고침")
            self.btnDelete       = QPushButton("🗑️ 선택 데이터 삭제")
            self.btnVacuum       = QPushButton("⚡ VACUUM ANALYZE")
            self.progressDelete  = QProgressBar()
            self.labelResult     = QLabel("")
            for w in (
                self.comboTable, self.radioAll, self.radioByDateRange,
                self.radioByEventType, self.dateFrom, self.dateTo,
                self.editEventType, self.labelRecordCount, self.btnRefreshCount,
                self.btnDelete, self.btnVacuum,
                self.progressDelete, self.labelResult,
            ):
                layout.addWidget(w)

        def _setup_ui(self) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(False)
                pb.setMaximum(0)

        def _reset_dates(self) -> None:
            today = QDate.currentDate()
            for name, offset in (("dateFrom", -90), ("dateTo", 0)):
                w = getattr(self, name, None)
                if w is not None:
                    w.setDate(today.addDays(offset))

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _bind_signals(self) -> None:
            for btn_name, slot in (
                ("btnDelete",       self._on_btn_delete_clicked),
                ("btnVacuum",       self._on_btn_vacuum_clicked),
                ("btnRefreshCount", self._refresh_count),
            ):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.clicked.connect(slot)

            combo = getattr(self, "comboTable", None)
            if combo is not None:
                combo.currentTextChanged.connect(lambda _: self._refresh_count())

            for radio_name, handler in (
                ("radioAll",          self._on_radio_all),
                ("radioByDateRange",  self._on_radio_daterange),
                ("radioByEventType",  self._on_radio_eventtype),
            ):
                radio = getattr(self, radio_name, None)
                if radio is not None:
                    radio.toggled.connect(handler)

        @pyqtSlot(bool)
        def _on_radio_all(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(False)
            self._set_eventtype_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_daterange(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(True)
            self._set_eventtype_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_eventtype(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(False)
            self._set_eventtype_enabled(True)

        def _set_date_enabled(self, enabled: bool) -> None:
            for name in ("dateFrom", "dateTo", "labelDateFrom", "labelDateTo"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        def _set_eventtype_enabled(self, enabled: bool) -> None:
            for name in ("editEventType", "labelEventType"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        # ------------------------------------------------------------------
        # 건수 조회
        # ------------------------------------------------------------------

        def _refresh_count(self) -> None:
            table = self._selected_table()
            if not table:
                return
            if self._count_worker and self._count_worker.isRunning():
                return
            lbl = getattr(self, "labelRecordCount", None)
            if lbl is not None:
                lbl.setText("레코드 수: 조회 중...")
            try:
                self._count_worker = _CountWorker(self._conn_params, table)
            except ValueError:
                if lbl is not None:
                    lbl.setText("레코드 수: 유효하지 않은 테이블")
                return
            self._count_worker.finished.connect(
                lambda msg: lbl.setText(msg) if lbl else None
            )
            self._count_worker.error.connect(
                lambda _: lbl.setText("레코드 수: 조회 실패") if lbl else None
            )
            self._count_worker.start()

        # ------------------------------------------------------------------
        # 삭제 버튼
        # ------------------------------------------------------------------

        def _on_btn_delete_clicked(self) -> None:
            table = self._selected_table()
            sql, params, desc = self._build_delete_sql(table)
            if sql is None:
                return

            ret = QMessageBox.warning(
                self, "⚠️ 삭제 확인",
                f"정말로 아래 데이터를 삭제하시겠습니까?\n\n{desc}\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._run_write_worker(sql, params)

        def _on_btn_vacuum_clicked(self) -> None:
            table = self._selected_table() or ""
            sql = f"VACUUM ANALYZE {table}" if table else "VACUUM ANALYZE"
            self._run_write_worker(sql, ())

        def _selected_table(self) -> Optional[str]:
            combo = getattr(self, "comboTable", None)
            if combo is None:
                return None
            t = combo.currentText().strip()
            return t if t in _ALLOWED_TABLES else None

        def _build_delete_sql(self, table: Optional[str]):
            if table is None:
                QMessageBox.warning(self, "오류", "유효한 테이블을 선택하세요.")
                return None, None, None

            radio_date  = getattr(self, "radioByDateRange", None)
            radio_event = getattr(self, "radioByEventType", None)
            time_col    = _TIME_COLUMN.get(table, "created_at")

            if radio_date and radio_date.isChecked():
                df = getattr(self, "dateFrom", None)
                dt = getattr(self, "dateTo",   None)
                if df is None or dt is None:
                    return None, None, None
                d_from = df.date().toString("yyyy-MM-dd")
                d_to   = dt.date().toString("yyyy-MM-dd")
                sql    = (
                    f"DELETE FROM {table} "  # noqa: S608 – table is whitelisted
                    f"WHERE {time_col} >= %s::date "
                    f"AND {time_col} < (%s::date + interval '1 day')"
                )
                params = (d_from, d_to)
                desc   = f"테이블: {table}\n기간: {d_from} ~ {d_to}"
            elif radio_event and radio_event.isChecked():
                edit = getattr(self, "editEventType", None)
                ev_type = edit.text().strip() if edit else ""
                if not ev_type:
                    QMessageBox.warning(self, "입력 오류", "이벤트 타입을 입력하세요.")
                    return None, None, None
                sql    = f"DELETE FROM {table} WHERE event_type = %s"  # noqa: S608
                params = (ev_type,)
                desc   = f"테이블: {table}\n이벤트 타입: {ev_type}"
            else:
                sql    = f"DELETE FROM {table}"  # noqa: S608
                params = ()
                desc   = f"테이블: {table}\n범위: 전체"

            return sql, params, desc

        def _run_write_worker(self, sql: str, params: tuple) -> None:
            if self._worker and self._worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 작업이 진행 중입니다.")
                return
            self._set_busy(True)
            self._worker = _PgWriteWorker(self._conn_params, sql, params)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        # ------------------------------------------------------------------
        # Worker 완료 슬롯
        # ------------------------------------------------------------------

        @pyqtSlot(int)
        def _on_finished(self, rows: int) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #16A34A; font-weight: bold;")
                lbl.setText(f"✅ 완료: {rows:,} 건 처리됨" if rows > 0 else "✅ 완료")
            self._refresh_count()

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
                lbl.setText(f"🔴 오류: {msg[:180]}")
            logger.warning("[PG DeleteTab] 오류: %s", msg)

        def _set_busy(self, busy: bool) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)
            for name in ("btnDelete", "btnVacuum", "btnRefreshCount"):
                btn = getattr(self, name, None)
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

        def start_updates(self, interval_ms: int = 0) -> None:
            self._refresh_count()

        def stop_updates(self) -> None:
            for worker in (self._worker, self._count_worker):
                if worker is not None and worker.isRunning():
                    worker.quit()
                    worker.wait(2000)

        def closeEvent(self, event) -> None:
            self.stop_updates()
            super().closeEvent(event)

else:
    class DeleteTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass
