# -*- coding: utf-8 -*-
"""ClickHouse 데이터 삭제 탭 (QThread Worker 패턴, 메인스레드 블로킹 없음)

지원 작업:
  - TRUNCATE TABLE: 전체 데이터 즉시 삭제
  - DELETE by date range: 날짜 범위별 삭제
  - DROP PARTITION: 파티션 단위 삭제
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox
    from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QDate, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "delete_tab.ui")

# SQL injection 방지용 테이블 화이트리스트
_ALLOWED_TABLES = frozenset({
    "candles_1m", "candles_5m", "candles_1h", "candles_1d",
    "market_ticks", "orderbook_aggregates",
    "backtest_results", "technical_indicators_archive",
})

# 파티션 ID 허용 패턴 (숫자/영문/하이픈만)
_PARTITION_RE = re.compile(r'^[A-Za-z0-9_\-]+$')


def _get_ch_client(conn_params: dict):
    """ClickHouse 클라이언트를 반환합니다. 실패 시 None."""
    try:
        import clickhouse_connect  # type: ignore[import]
        host     = conn_params.get("host") or os.getenv("CLICKHOUSE_HOST", "localhost")
        port     = int(conn_params.get("port") or os.getenv("CLICKHOUSE_PORT", "8123"))
        user     = conn_params.get("user") or os.getenv("CLICKHOUSE_USER", "default")
        password = conn_params.get("password") or os.getenv("CLICKHOUSE_PASSWORD", "")
        database = conn_params.get("database") or os.getenv("CLICKHOUSE_DB", "upbit_trader")
        return clickhouse_connect.get_client(
            host=host, port=port, username=user,
            password=password, database=database, connect_timeout=5,
        )
    except Exception as exc:
        logger.debug("[CH DeleteTab] 연결 실패: %s", exc)
        return None


if _HAS_QT:
    # ------------------------------------------------------------------
    # QThread Worker
    # ------------------------------------------------------------------
    class _ClickHouseWorker(QThread):
        """ClickHouse 명령 실행 Worker."""
        finished = pyqtSignal(str)   # 완료 메시지
        error    = pyqtSignal(str)   # 오류 메시지

        def __init__(self, conn_params: dict, sql: str):
            super().__init__()
            self._conn_params = conn_params
            self._sql = sql

        def run(self):
            try:
                client = _get_ch_client(self._conn_params)
                if client is None:
                    self.error.emit("ClickHouse 연결 실패 — 환경 변수(CLICKHOUSE_HOST 등) 확인")
                    return
                client.command(self._sql)
                self.finished.emit(f"완료: {self._sql[:80]}")
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
                client = _get_ch_client(self._conn_params)
                if client is None:
                    self.error.emit("연결 실패")
                    return
                result = client.query(
                    f"SELECT count() FROM {self._table}"  # noqa: S608 – table is whitelisted
                )
                count = result.result_rows[0][0] if result.result_rows else 0
                self.finished.emit(f"레코드 수: {count:,} 건")
            except Exception as exc:
                self.error.emit(str(exc)[:100])

    # ------------------------------------------------------------------
    # 탭 위젯
    # ------------------------------------------------------------------
    class DeleteTab(QWidget):
        """ClickHouse 데이터 삭제 탭.

        TRUNCATE / 날짜 범위 삭제 / 파티션 DROP 을 QThread Worker로 안전하게 실행합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[_ClickHouseWorker] = None
            self._count_worker: Optional[_CountWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[CH DeleteTab] UI 로드 실패: %s", exc)
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
            self.comboTable        = QComboBox()
            for t in sorted(_ALLOWED_TABLES):
                self.comboTable.addItem(t)
            self.radioTruncate     = QRadioButton("전체 삭제(TRUNCATE)")
            self.radioByDateRange  = QRadioButton("날짜 범위 삭제")
            self.radioDropPartition= QRadioButton("파티션 DROP")
            self.radioTruncate.setChecked(True)
            self.dateFrom          = QDateEdit()
            self.dateTo            = QDateEdit()
            self.editPartition     = QLineEdit()
            self.labelRecordCount  = QLabel("레코드 수: -")
            self.btnRefreshCount   = QPushButton("🔄 건수 새로고침")
            self.btnDelete         = QPushButton("🗑️ 선택 데이터 삭제")
            self.progressDelete    = QProgressBar()
            self.labelResult       = QLabel("")
            for w in (
                self.comboTable, self.radioTruncate, self.radioByDateRange,
                self.radioDropPartition, self.dateFrom, self.dateTo,
                self.editPartition, self.labelRecordCount,
                self.btnRefreshCount, self.btnDelete,
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
                ("btnRefreshCount", self._refresh_count),
            ):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.clicked.connect(slot)

            combo = getattr(self, "comboTable", None)
            if combo is not None:
                combo.currentTextChanged.connect(lambda _: self._refresh_count())

            for radio_name, handler in (
                ("radioTruncate",      self._on_radio_truncate),
                ("radioByDateRange",   self._on_radio_daterange),
                ("radioDropPartition", self._on_radio_partition),
            ):
                radio = getattr(self, radio_name, None)
                if radio is not None:
                    radio.toggled.connect(handler)

        # ------------------------------------------------------------------
        # 라디오 핸들러
        # ------------------------------------------------------------------

        @pyqtSlot(bool)
        def _on_radio_truncate(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(False)
            self._set_partition_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_daterange(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(True)
            self._set_partition_enabled(False)

        @pyqtSlot(bool)
        def _on_radio_partition(self, checked: bool) -> None:
            if not checked:
                return
            self._set_date_enabled(False)
            self._set_partition_enabled(True)

        def _set_date_enabled(self, enabled: bool) -> None:
            for name in ("dateFrom", "dateTo", "labelDateFrom", "labelDateTo"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        def _set_partition_enabled(self, enabled: bool) -> None:
            for name in ("editPartition", "labelPartition"):
                w = getattr(self, name, None)
                if w is not None:
                    w.setEnabled(enabled)

        # ------------------------------------------------------------------
        # 건수 조회
        # ------------------------------------------------------------------

        def _refresh_count(self) -> None:
            table = self._selected_table()
            if table is None:
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
            sql, desc = self._build_sql(table)
            if sql is None:
                return

            ret = QMessageBox.warning(
                self, "⚠️ 삭제 확인",
                f"정말로 아래 데이터를 삭제하시겠습니까?\n\n{desc}\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return

            if self._worker and self._worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 작업이 진행 중입니다.")
                return

            self._set_busy(True)
            self._worker = _ClickHouseWorker(self._conn_params, sql)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        def _selected_table(self) -> Optional[str]:
            combo = getattr(self, "comboTable", None)
            if combo is None:
                return None
            t = combo.currentText().strip()
            return t if t in _ALLOWED_TABLES else None

        def _build_sql(self, table: Optional[str]):
            if table is None:
                QMessageBox.warning(self, "오류", "유효한 테이블을 선택하세요.")
                return None, None

            radio_date = getattr(self, "radioByDateRange", None)
            radio_part = getattr(self, "radioDropPartition", None)

            if radio_part and radio_part.isChecked():
                edit = getattr(self, "editPartition", None)
                pid = edit.text().strip() if edit else ""
                if not pid or not _PARTITION_RE.match(pid):
                    QMessageBox.warning(self, "입력 오류", "올바른 파티션 ID를 입력하세요 (예: 202501).")
                    return None, None
                sql  = f"ALTER TABLE {table} DROP PARTITION '{pid}'"
                desc = f"테이블: {table}\n파티션: {pid}"
            elif radio_date and radio_date.isChecked():
                df  = getattr(self, "dateFrom", None)
                dt  = getattr(self, "dateTo",   None)
                if df is None or dt is None:
                    return None, None
                # QDateEdit.toString("yyyy-MM-dd") 은 항상 유효한 ISO 날짜를 반환
                d_from = df.date().toString("yyyy-MM-dd")
                d_to   = dt.date().toString("yyyy-MM-dd")
                if df.date() > dt.date():
                    QMessageBox.warning(self, "입력 오류", "시작일이 종료일보다 늦을 수 없습니다.")
                    return None, None
                sql  = (
                    f"ALTER TABLE {table} DELETE "
                    f"WHERE toDate(timestamp) >= '{d_from}' "
                    f"AND toDate(timestamp) <= '{d_to}'"
                )
                desc = f"테이블: {table}\n기간: {d_from} ~ {d_to}"
            else:
                sql  = f"TRUNCATE TABLE {table}"
                desc = f"테이블: {table}\n범위: 전체 (TRUNCATE)"

            return sql, desc

        # ------------------------------------------------------------------
        # Worker 완료 슬롯
        # ------------------------------------------------------------------

        @pyqtSlot(str)
        def _on_finished(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #16A34A; font-weight: bold;")
                lbl.setText(f"✅ {msg}")
            self._refresh_count()

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
                lbl.setText(f"🔴 오류: {msg[:180]}")
            logger.warning("[CH DeleteTab] 오류: %s", msg)

        def _set_busy(self, busy: bool) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)
            for name in ("btnDelete", "btnRefreshCount"):
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
            """탭 활성화 시 건수 즉시 조회."""
            self._refresh_count()

        def stop_updates(self) -> None:
            """Worker 정리."""
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
