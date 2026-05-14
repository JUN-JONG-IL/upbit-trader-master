# -*- coding: utf-8 -*-
"""
TimescaleSettingsDialog 컨트롤러 (Gap 모니터 연동 포함)
- 변경 요지:
  * 외부/로컬 모듈 로드를 안전한 런타임 로더로 수행하여
    'src.data_01' 형태의 식별자 때문에 발생하는 SyntaxError를 회피합니다.
  * UI 바인딩, 백그라운드 스레드 조회 등 기존 동작 유지.
- 모든 주석은 한글입니다.
"""
from __future__ import annotations

import logging
import os
import threading
import math
import csv
import importlib
import importlib.util
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

# 안전한 런타임 모듈 로더 유틸리티
def _load_module_by_path(path: Path, name: str):
    """
    파일 경로로부터 모듈을 로드하여 반환합니다.
    실패하면 None을 반환합니다.
    """
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception:
        logging.getLogger(__name__).debug("파일 경로로 모듈 로드 실패: %s", path, exc_info=True)
    return None

def _try_import_pkg_or_path(pkg_name: str, attr: Optional[str], relative_file: Path, candidate_paths: List[Path]):
    """
    1) pkg_name으로 import 시도 (패키지로 설치/모듈 경로가 유효할 때)
    2) 실패하면 candidate_paths 리스트에 있는 파일 경로들로 시도
    """
    try:
        mod = importlib.import_module(pkg_name)
        return getattr(mod, attr) if attr else mod
    except Exception:
        # 파일 경로 폴백
        for p in candidate_paths:
            if p.exists():
                m = _load_module_by_path(p, p.stem)
                if m:
                    return getattr(m, attr) if attr and hasattr(m, attr) else (m if attr is None else None)
    return None

# timescale helper 불러오기 (가능하면 패키지 import, 아니면 파일 경로)
_timescale_helpers = None
try:
    # package import 시도 (정상 패키지 환경일 때)
    _timescale_helpers = importlib.import_module("timescale_db")
except Exception:
    # 프로젝트 내 파일 경로로 시도: src/data_01/timescale/ui/timescale_db.py 또는 src/data_01/timescale/timescale_db.py
    base = Path(__file__).resolve().parents[3]  # .../src/data_01/timescale/ui -> go up to repo/src
    candidates = [
        base / "data_01" / "timescale" / "ui" / "timescale_db.py",
        base / "data_01" / "timescale" / "timescale_db.py",
    ]
    for cp in candidates:
        if cp.exists():
            _timescale_helpers = _load_module_by_path(cp, "timescale_db")
            break

# convenience bindings (None-safe)
fetch_conn_status = getattr(_timescale_helpers, "fetch_conn_status", None) if _timescale_helpers else None
fetch_hypertables = getattr(_timescale_helpers, "fetch_hypertables", None) if _timescale_helpers else None
fetch_compression_policies = getattr(_timescale_helpers, "fetch_compression_policies", None) if _timescale_helpers else None
fetch_continuous_aggs = getattr(_timescale_helpers, "fetch_continuous_aggs", None) if _timescale_helpers else None
fetch_gaps = getattr(_timescale_helpers, "fetch_gaps", None) if _timescale_helpers else None
fetch_backfills = getattr(_timescale_helpers, "fetch_backfills", None) if _timescale_helpers else None

# enqueue_tasks (Redis push) — 패키지 또는 timescale_redis 파일에서 시도
enqueue_tasks = None
try:
    enqueue_tasks = importlib.import_module("timescale_redis").enqueue_tasks
except Exception:
    # fallback to project path
    base = Path(__file__).resolve().parents[3]
    candidate = base / "data_01" / "timescale" / "timescale_redis.py"
    if candidate.exists():
        m = _load_module_by_path(candidate, "timescale_redis")
        enqueue_tasks = getattr(m, "enqueue_tasks", None)

# PyQt 로드
try:
    from PyQt5 import uic
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5.QtWidgets import (
        QDialog,
        QTableWidget,
        QTableWidgetItem,
        QLineEdit,
        QDialogButtonBox,
        QFormLayout,
        QMessageBox,
        QFileDialog,
        QLabel,
        QHeaderView,
        QSpinBox,
        QTextEdit,
    )
    PYQT5_AVAILABLE = True
except Exception:
    PYQT5_AVAILABLE = False

logger = logging.getLogger("timescale.dialog")
if logger.level == 0:
    logger.setLevel(logging.INFO)
_UI_PATH = Path(__file__).parent / "timescale_settings.ui"

# GapMonitor 다이얼로그 로드: 안전 로더 사용 (패키지 import 아니라 파일 경로 로드)
GapMonitorDialog = None
try:
    # 1) 일반 import 시도 (가능성 낮음)
    gm = importlib.import_module("src.data_01.pipeline.ui.gap_monitor_dialog")
    GapMonitorDialog = getattr(gm, "GapMonitorDialog", None)
except Exception:
    # 2) 파일 경로로 로드: ../pipeline/ui/gap_monitor_dialog.py
    base = Path(__file__).resolve().parents[3]
    candidate = base / "data_01" / "pipeline" / "ui" / "gap_monitor_dialog.py"
    if candidate.exists():
        mod = _load_module_by_path(candidate, "gap_monitor_dialog")
        GapMonitorDialog = getattr(mod, "GapMonitorDialog", None)

if PYQT5_AVAILABLE:
    # 삭제 기능 믹스인 로드 (파일 경로 기반, SyntaxError 안전)
    _TimescaleDeleteMixin = None
    try:
        _del_path = Path(__file__).parent / "timescale_delete_operations.py"
        if _del_path.exists():
            _del_mod = _load_module_by_path(_del_path, "timescale_delete_operations")
            if _del_mod:
                _TimescaleDeleteMixin = getattr(_del_mod, "TimescaleDeleteMixin", None)
    except Exception:
        pass
    if _TimescaleDeleteMixin is None:
        class _TimescaleDeleteMixin:  # type: ignore[no-redef]
            """TimescaleDeleteMixin 로드 실패 시 사용하는 빈 믹스인"""
            def _bind_delete_signals(self): pass
            def _refresh_delete_counts(self): pass

    class TimescaleSettingsDialog(QDialog, _TimescaleDeleteMixin):
        """
        TimescaleSettingsDialog:
        - UI 이벤트 바인딩
        - 기존 기능(연결상태/Hypertable/Compression/ContAggs/Gaps/Backfills/Raw) 유지
        - Gap 모니터 다이얼로그를 안전하게 열도록 구현
        - 데이터 삭제 탭 (TimescaleDeleteMixin)
        """
        _sig_conn_status_ready = pyqtSignal(dict)
        _sig_hypertables_ready = pyqtSignal(list)
        _sig_compression_ready = pyqtSignal(list)
        _sig_aggs_ready = pyqtSignal(list)
        _sig_gaps_ready = pyqtSignal(list)
        _sig_backfills_ready = pyqtSignal(list)
        _sig_raw_ready = pyqtSignal(list)

        def __init__(self, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            # UI 로드
            if _UI_PATH.exists():
                uic.loadUi(str(_UI_PATH), self)
            else:
                raise FileNotFoundError("timescale_settings.ui 파일을 찾을 수 없습니다.")

            # DB 접속 기본 설정 (환경변수 기반)
            self._config = {
                "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
                "port": int(os.getenv("POSTGRES_PORT", "5432")),
                "dbname": os.getenv("POSTGRES_DB", "upbit_trader"),
                "user": os.getenv("POSTGRES_USER", "admin"),
                "password": os.getenv("POSTGRES_PASSWORD", ""),
            }

            self._last_gaps_rows: List[List[str]] = []
            self._recent_log_msgs: List[str] = []
            self._auto_scan_timer = None

            # DSN 표시
            try:
                if hasattr(self, "editDSN") and self.editDSN is not None:
                    libpq = f"host={self._config['host']} port={self._config['port']} dbname={self._config['dbname']} user={self._config['user']}"
                    self.editDSN.setText(libpq)
            except Exception:
                pass

            # 바인딩
            self._bind_signals()

            # 삭제 탭 버튼 바인딩 (TimescaleDeleteMixin)
            self._bind_delete_signals()
            self._refresh_delete_counts()

            # 시그널 연결
            self._sig_conn_status_ready.connect(self._update_conn_status_ui)
            self._sig_hypertables_ready.connect(self._update_hypertables_ui)
            self._sig_compression_ready.connect(self._update_compression_ui)
            self._sig_aggs_ready.connect(self._update_aggs_ui)
            self._sig_gaps_ready.connect(self._update_gaps_ui)
            self._sig_backfills_ready.connect(self._update_backfills_ui)
            self._sig_raw_ready.connect(self._update_raw_table_ui)

            # 주기적 전체 새로고침
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(lambda: threading.Thread(target=self._refresh_all, daemon=True).start())
            self._timer.start()

            # 초기 로드 (백그라운드)
            threading.Thread(target=self._refresh_all, daemon=True).start()

            # raw table 헤더 설정
            try:
                if hasattr(self, "tableRawData") and isinstance(self.tableRawData, QTableWidget):
                    self.tableRawData.setColumnCount(6)
                    self.tableRawData.setHorizontalHeaderLabels(["trade_id", "exchange_ts", "symbol", "price", "qty", "side"])
                    self.tableRawData.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            except Exception:
                pass

            # 비모달 팝업 설정
            self.setWindowModality(Qt.NonModal)
            self.setAttribute(Qt.WA_DeleteOnClose, False)

            # 페이지네이션 상태
            self._current_page: int = 1
            self._total_pages: int = 1
            self._page_size: int = 100

            # 실시간 갱신 타이머 (1초)
            self._realtime_timer = QTimer(self)
            self._realtime_timer.setInterval(1000)
            self._realtime_timer.timeout.connect(self._on_refresh_realtime)
            self._realtime_timer.start()

            # PyQtGraph 차트 초기화 (Tab 2: 실시간 통신 모니터)
            self._init_live_monitor()

            # 창 위치 복원
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _geometry = _settings.value("timescale_geometry")
                if _geometry:
                    self.restoreGeometry(_geometry)
            except Exception:
                pass

            # 다크 모드 스타일
            self.setStyleSheet("""
                QDialog { background-color: #2b2b2b; color: #ffffff; }
                QTableWidget { background-color: #1e1e1e; gridline-color: #444; color: #ffffff; }
                QTableWidget QHeaderView::section { background-color: #3c3c3c; color: #ffffff; }
                QPushButton { background-color: #0078d4; color: white; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #1084d8; }
                QGroupBox { color: #ffffff; border: 1px solid #555; margin-top: 6px; }
                QGroupBox::title { color: #aaaaaa; }
                QLabel { color: #ffffff; }
                QComboBox { background-color: #3c3c3c; color: #ffffff; }
                QLineEdit { background-color: #3c3c3c; color: #ffffff; }
                QTabWidget::pane { border: 1px solid #555; }
                QTabBar::tab { background-color: #3c3c3c; color: #ffffff; padding: 6px 12px; }
                QTabBar::tab:selected { background-color: #0078d4; }
            """)

        def _bind_signals(self) -> None:
            btn_map = [
                ("btnConnect", self.load_conn_status),
                ("btnRefreshHypertable", self.load_hypertables),
                ("btnRefreshCompression", self.load_compression_policies),
                ("btnRefreshAggs", self.load_continuous_aggs),
                ("btnDetectGaps", self.load_gaps),
                ("btnAddToQueue", self._on_add_gaps_to_queue),
                ("btnExportGaps", self._on_export_gaps),
                ("btnStartBackfill", self._on_start_backfill),
                ("btnCancelBackfill", self._on_cancel_backfill),
                ("btnEditConn", self._on_open_settings_editor),
                ("btnLoadRaw", self._on_load_raw),
                ("btnExportRawCSV", self._on_export_raw_csv),
                ("btnOpenGapMonitor", self._on_open_gap_monitor),
                ("btnSearch", self._on_search_data),
                ("btnPrevPage", self._on_prev_page),
                ("btnNextPage", self._on_next_page),
                ("btnExportCSV", self._on_export_csv),
            ]
            for attr, func in btn_map:
                if hasattr(self, attr):
                    try:
                        getattr(self, attr).clicked.connect(func)
                    except Exception:
                        logger.debug("버튼 바인딩 실패: %s", attr, exc_info=True)

            try:
                if hasattr(self, "chkAutoScan"):
                    self.chkAutoScan.stateChanged.connect(self._on_toggle_gap_autoscan)
                if hasattr(self, "spinScanInterval"):
                    self.spinScanInterval.valueChanged.connect(self._on_change_scan_interval)
            except Exception:
                pass

        def _refresh_all(self) -> None:
            threading.Thread(target=self.load_conn_status, daemon=True).start()
            threading.Thread(target=self.load_hypertables, daemon=True).start()
            threading.Thread(target=self.load_compression_policies, daemon=True).start()
            threading.Thread(target=self.load_continuous_aggs, daemon=True).start()
            threading.Thread(target=self.load_gaps, daemon=True).start()
            threading.Thread(target=self.load_backfills, daemon=True).start()

        def load_conn_status(self) -> None:
            try:
                if fetch_conn_status is None:
                    return
                res = fetch_conn_status(self._config)
                self._sig_conn_status_ready.emit(res)
            except Exception:
                logger.debug("load_conn_status 예외", exc_info=True)

        def _update_conn_status_ui(self, data: Dict[str, Any]) -> None:
            try:
                if hasattr(self, "labelConnStatus"):
                    status = data.get("status", "disconnected")
                    color = "#2ECC40" if status == "connected" else "#FF4136"
                    text = "● 연결됨" if status == "connected" else "● 연결 실패"
                    self.labelConnStatus.setText(text)
                    self.labelConnStatus.setStyleSheet(f"color:{color}; font-weight:bold;")
                if hasattr(self, "labelHost"):
                    self.labelHost.setText(data.get("host", "-"))
                if hasattr(self, "labelDBName"):
                    self.labelDBName.setText(data.get("dbname", "-"))
                if hasattr(self, "labelVersion"):
                    self.labelVersion.setText(f"{data.get('version','-')} / {data.get('ts_version','-')}")
                if hasattr(self, "labelUptime"):
                    self.labelUptime.setText(data.get("uptime", "-"))
                if hasattr(self, "labelConnCount"):
                    self.labelConnCount.setText(str(data.get("conn_count", "-")))
                if data.get("error") and hasattr(self, "labelConnStatus"):
                    self.labelConnStatus.setToolTip(str(data.get("error")))
            except Exception:
                logger.debug("_update_conn_status_ui 예외", exc_info=True)

        def load_hypertables(self) -> None:
            try:
                if fetch_hypertables is None:
                    return
                rows, err = fetch_hypertables(self._config)
                self._sig_hypertables_ready.emit(rows)
            except Exception:
                logger.debug("load_hypertables 예외", exc_info=True)

        def _update_hypertables_ui(self, rows: List[List[str]]) -> None:
            try:
                self.tableHypertables.setRowCount(0)
                for row_data in rows:
                    r = self.tableHypertables.rowCount()
                    self.tableHypertables.insertRow(r)
                    for c, v in enumerate(row_data):
                        item = QTableWidgetItem(str(v))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.tableHypertables.setItem(r, c, item)
            except Exception:
                logger.debug("_update_hypertables_ui 예외", exc_info=True)

        def load_compression_policies(self) -> None:
            try:
                if fetch_compression_policies is None:
                    return
                rows, err = fetch_compression_policies(self._config)
                self._sig_compression_ready.emit(rows)
            except Exception:
                logger.debug("load_compression_policies 예외", exc_info=True)

        def _update_compression_ui(self, rows: List[List[str]]) -> None:
            try:
                self.tableCompressionPolicies.setRowCount(0)
                for row_data in rows:
                    r = self.tableCompressionPolicies.rowCount()
                    self.tableCompressionPolicies.insertRow(r)
                    for c, v in enumerate(row_data):
                        item = QTableWidgetItem(str(v))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.tableCompressionPolicies.setItem(r, c, item)
            except Exception:
                logger.debug("_update_compression_ui 예외", exc_info=True)

        def load_continuous_aggs(self) -> None:
            try:
                if fetch_continuous_aggs is None:
                    return
                rows, err = fetch_continuous_aggs(self._config)
                self._sig_aggs_ready.emit(rows)
            except Exception:
                logger.debug("load_continuous_aggs 예외", exc_info=True)

        def _update_aggs_ui(self, rows: List[List[str]]) -> None:
            try:
                self.tableContinuousAggs.setRowCount(0)
                for row_data in rows:
                    r = self.tableContinuousAggs.rowCount()
                    self.tableContinuousAggs.insertRow(r)
                    for c, v in enumerate(row_data):
                        item = QTableWidgetItem(str(v))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.tableContinuousAggs.setItem(r, c, item)
            except Exception:
                logger.debug("_update_aggs_ui 예외", exc_info=True)

        def _on_load_raw(self) -> None:
            try:
                limit = 100
                if hasattr(self, "spinRawLimit") and isinstance(self.spinRawLimit, QSpinBox):
                    try:
                        limit = int(self.spinRawLimit.value())
                    except Exception:
                        limit = 100
                limit = max(1, min(1000, limit))

                symbol_filter = ""
                if hasattr(self, "editRawFilter"):
                    symbol_filter = str(self.editRawFilter.text()).strip()

                if hasattr(self, "labelRawStatus"):
                    try:
                        self.labelRawStatus.setText("조회 중...")
                    except Exception:
                        pass

                threading.Thread(target=self._load_raw_worker, args=(symbol_filter, limit), daemon=True).start()
            except Exception:
                logger.debug("_on_load_raw 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "원시 데이터 조회를 시작하는 중 오류가 발생했습니다.")

        def _load_raw_worker(self, symbol_filter: str, limit: int) -> None:
            try:
                try:
                    import psycopg2  # type: ignore
                except Exception:
                    self._append_log("psycopg2 미설치: pip install psycopg2-binary")
                    self._update_label_raw_status("의존성 부족: psycopg2 미설치")
                    return

                if symbol_filter:
                    q = """
                        SELECT trade_id, exchange_ts, symbol, price, qty, side
                        FROM public.market_ticks
                        WHERE symbol ILIKE %s
                        ORDER BY exchange_ts DESC
                        LIMIT %s;
                    """
                    params = (f"%{symbol_filter}%", limit)
                else:
                    q = """
                        SELECT trade_id, exchange_ts, symbol, price, qty, side
                        FROM public.market_ticks
                        ORDER BY exchange_ts DESC
                        LIMIT %s;
                    """
                    params = (limit,)

                conn = None
                try:
                    conn = psycopg2.connect(
                        host=self._config.get("host", "127.0.0.1"),
                        port=int(self._config.get("port", 5432)),
                        dbname=self._config.get("dbname", ""),
                        user=self._config.get("user", ""),
                        password=self._config.get("password", ""),
                        connect_timeout=5,
                    )
                except Exception as e:
                    msg = f"DB 연결 실패: {e}"
                    self._append_log(msg)
                    self._update_label_raw_status("DB 연결 실패")
                    return

                try:
                    cur = conn.cursor()
                    cur.execute(q, params)
                    rows = cur.fetchall()
                    cur.close()
                except Exception as e:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    msg = f"쿼리 실패: {e}"
                    self._append_log(msg)
                    self._update_label_raw_status("쿼리 실패")
                    return
                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

                self._sig_raw_ready.emit(rows)
                self._update_label_raw_status(f"조회 완료: {len(rows)}건")
            except Exception:
                logger.debug("_load_raw_worker 예외", exc_info=True)
                self._update_label_raw_status("조회 중 예외 발생")

        def _update_label_raw_status(self, txt: str) -> None:
            try:
                if hasattr(self, "labelRawStatus"):
                    self.labelRawStatus.setText(txt)
                self._append_log(f"[Raw] {txt}")
            except Exception:
                logger.debug("_update_label_raw_status 예외", exc_info=True)

        def _update_raw_table_ui(self, rows: List[tuple]) -> None:
            try:
                if not hasattr(self, "tableRawData"):
                    return
                table = self.tableRawData
                table.setRowCount(0)
                for r_idx, row in enumerate(rows):
                    table.insertRow(r_idx)
                    for c_idx, val in enumerate(row):
                        item = QTableWidgetItem(str(val) if val is not None else "-")
                        item.setTextAlignment(Qt.AlignCenter)
                        table.setItem(r_idx, c_idx, item)
                try:
                    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                except Exception:
                    pass
            except Exception:
                logger.debug("_update_raw_table_ui 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "원시 데이터 테이블 업데이트 중 오류가 발생했습니다.")

        def _on_export_raw_csv(self) -> None:
            try:
                if not hasattr(self, "tableRawData"):
                    QMessageBox.information(self, "내보내기", "내보낼 원시 데이터가 없습니다.")
                    return
                row_count = self.tableRawData.rowCount()
                if row_count == 0:
                    QMessageBox.information(self, "내보내기", "내보낼 원시 데이터가 없습니다.")
                    return

                path, _ = QFileDialog.getSaveFileName(self, "Raw 데이터 CSV 저장", "market_ticks.csv", "CSV Files (*.csv)")
                if not path:
                    return

                headers = [self.tableRawData.horizontalHeaderItem(i).text() if self.tableRawData.horizontalHeaderItem(i) else f"col{i}" for i in range(self.tableRawData.columnCount())]
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in range(row_count):
                        row_vals = []
                        for c in range(self.tableRawData.columnCount()):
                            item = self.tableRawData.item(r, c)
                            row_vals.append(item.text() if item else "")
                        writer.writerow(row_vals)
                QMessageBox.information(self, "내보내기", f"CSV 저장 완료: {path}")
                self._append_log(f"Raw CSV 저장: {path}")
            except Exception:
                logger.debug("_on_export_raw_csv 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "CSV 저장 중 오류가 발생했습니다.")

        def load_gaps(self) -> None:
            try:
                if fetch_gaps is None:
                    return
                symbol_filter = ""
                if hasattr(self, "editSymbolFilter"):
                    symbol_filter = str(self.editSymbolFilter.text()).strip()
                rows, err = fetch_gaps(self._config, symbol_filter, int(os.getenv("GAP_THRESHOLD_SECONDS", "300")))
                if rows is None:
                    rows = [["(오류)","-","-","-","-","-","-"]]
                self._sig_gaps_ready.emit(rows)
            except Exception:
                logger.debug("load_gaps 예외", exc_info=True)

        def _update_gaps_ui(self, rows: List[List[str]]) -> None:
            try:
                self.tableGaps.setRowCount(0)
                self._last_gaps_rows = rows
                for row_data in rows:
                    r = self.tableGaps.rowCount()
                    self.tableGaps.insertRow(r)
                    for c, v in enumerate(row_data):
                        item = QTableWidgetItem(str(v))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.tableGaps.setItem(r, c, item)
                try:
                    if hasattr(self, "progressGaps"):
                        self.progressGaps.setValue(100)
                except Exception:
                    pass
            except Exception:
                logger.debug("_update_gaps_ui 예외", exc_info=True)

        def load_backfills(self) -> None:
            try:
                if fetch_backfills is None:
                    return
                rows, err = fetch_backfills(self._config)
                self._sig_backfills_ready.emit(rows)
            except Exception:
                logger.debug("load_backfills 예외", exc_info=True)

        def _update_backfills_ui(self, rows: List[List[str]]) -> None:
            try:
                self.tableBackfills.setRowCount(0)
                for row_data in rows:
                    r = self.tableBackfills.rowCount()
                    self.tableBackfills.insertRow(r)
                    for c, v in enumerate(row_data):
                        item = QTableWidgetItem(str(v))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.tableBackfills.setItem(r, c, item)
            except Exception:
                logger.debug("_update_backfills_ui 예외", exc_info=True)

        def _on_add_gaps_to_queue(self) -> None:
            try:
                sel = self.tableGaps.selectionModel().selectedRows()
                if not sel:
                    QMessageBox.information(self, "선택 필요", "Redis에 추가할 Gap을 선택하세요.")
                    return
                tasks = []
                for idx in sel:
                    row = idx.row()
                    symbol = self.tableGaps.item(row, 0).text() if self.tableGaps.item(row, 0) else ""
                    start_ts = self.tableGaps.item(row, 2).text() if self.tableGaps.item(row, 2) else None
                    end_ts = self.tableGaps.item(row, 3).text() if self.tableGaps.item(row, 3) else None
                    gap_seconds_raw = self.tableGaps.item(row, 4).text() if self.tableGaps.item(row, 4) else ""
                    priority_raw = self.tableGaps.item(row, 5).text() if self.tableGaps.item(row, 5) else "3"
                    try:
                        gap_seconds = float(gap_seconds_raw) if gap_seconds_raw not in ("-", "(갭 없음)", "(오류)", "") else 0.0
                    except Exception:
                        gap_seconds = 0.0
                    try:
                        priority = int(priority_raw)
                    except Exception:
                        priority = 3
                    ev = {
                        "symbol": symbol,
                        "start": start_ts,
                        "end": end_ts,
                        "gap_seconds": gap_seconds,
                        "user_priority": priority,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "source": "ui",
                    }
                    try:
                        score = (6 - max(1, min(5, priority))) * math.log1p(max(0.0, gap_seconds)) + 1.0
                    except Exception:
                        score = max(1.0, gap_seconds or 1.0)
                    tasks.append((ev, float(score)))
                if enqueue_tasks is None:
                    QMessageBox.warning(self, "Redis 오류", "Redis 모듈 미설치 또는 로드 실패")
                    return
                added, errors = enqueue_tasks(tasks)
                QMessageBox.information(self, "Redis Push", f"추가 성공: {added}건\n오류: {len(errors)}건")
            except Exception:
                logger.debug("_on_add_gaps_to_queue 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "Redis 큐 추가 중 오류가 발생했습니다.")

        def _on_export_gaps(self) -> None:
            try:
                if not getattr(self, "_last_gaps_rows", None):
                    QMessageBox.information(self, "내보내기", "내보낼 Gap 데이터가 없습니다.")
                    return
                path, _ = QFileDialog.getSaveFileName(self, "Gap 목록 CSV로 저장", "gaps.csv", "CSV Files (*.csv)")
                if not path:
                    return
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["symbol","timeframe","gap_start","gap_end","missing_seconds","priority","backfill_state"])
                    for row in self._last_gaps_rows:
                        writer.writerow([str(c) for c in row])
                QMessageBox.information(self, "내보내기", f"CSV 저장 완료: {path}")
            except Exception:
                logger.debug("_on_export_gaps 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "CSV 저장 중 오류가 발생했습니다.")

        def _on_start_backfill(self) -> None:
            try:
                tbl = getattr(self, "tableGaps", None)
                if tbl is None:
                    QMessageBox.information(self, "백필", "Gap 테이블이 없습니다.")
                    return
                sel = tbl.selectionModel().selectedRows()
                if not sel:
                    QMessageBox.information(self, "백필", "시작할 Gap을 선택하세요.")
                    return
                count = len(sel)
                QMessageBox.information(self, "백필", f"백필 시작 요청: {count}건 (UI 스텁)")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] _on_start_backfill 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "백필 시작 중 오류가 발생했습니다.")

        def _on_cancel_backfill(self) -> None:
            try:
                tbl = getattr(self, "tableBackfills", None)
                if tbl is None:
                    QMessageBox.information(self, "백필 취소", "백필 테이블이 없습니다.")
                    return
                items = tbl.selectedItems()
                if not items:
                    QMessageBox.information(self, "백필 취소", "취소할 백필 항목을 선택하세요.")
                    return
                rows_selected = {it.row() for it in items}
                QMessageBox.information(self, "백필 취소", f"백필 취소 요청: {len(rows_selected)}건 (UI 스텁)")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] _on_cancel_backfill 예외", exc_info=True)
                QMessageBox.warning(self, "오류", "백필 취소 중 오류가 발생했습니다.")

        def _on_open_settings_editor(self) -> None:
            try:
                dlg = QDialog(self)
                dlg.setWindowTitle("Timescale 연결 설정 편집")
                form = QFormLayout(dlg)

                host = str(self._config.get("host") or "")
                port = str(self._config.get("port") or "5432")
                db = str(self._config.get("dbname") or self._config.get("db") or "")
                user = str(self._config.get("user") or "")
                passwd = str(self._config.get("password") or "")

                le_host = QLineEdit(host, dlg)
                le_port = QLineEdit(port, dlg)
                le_db = QLineEdit(db, dlg)
                le_user = QLineEdit(user, dlg)
                le_pass = QLineEdit(passwd, dlg)
                le_pass.setEchoMode(QLineEdit.Password)

                form.addRow("호스트:", le_host)
                form.addRow("포트:", le_port)
                form.addRow("데이터베이스:", le_db)
                form.addRow("사용자:", le_user)
                form.addRow("비밀번호:", le_pass)

                buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dlg)
                form.addRow(buttons)

                def _on_save():
                    new_host = le_host.text().strip()
                    new_port = le_port.text().strip()
                    new_db = le_db.text().strip()
                    new_user = le_user.text().strip()
                    new_pass = le_pass.text()

                    if not new_host or not new_db:
                        QMessageBox.warning(self, "입력 오류", "호스트와 데이터베이스명은 필수입니다.")
                        return

                    try:
                        self._config.update({
                            "host": new_host,
                            "port": int(new_port) if new_port else 5432,
                            "dbname": new_db,
                            "user": new_user,
                            "password": new_pass,
                        })
                    except Exception:
                        self._config.update({
                            "host": new_host,
                            "port": new_port,
                            "dbname": new_db,
                            "user": new_user,
                            "password": new_pass,
                        })

                    try:
                        if hasattr(self, "editDSN"):
                            libpq = f"host={self._config['host']} port={self._config['port']} dbname={self._config['dbname']} user={self._config['user']}"
                            self.editDSN.setText(libpq)
                    except Exception:
                        pass

                    dlg.accept()
                    threading.Thread(target=self._refresh_all, daemon=True).start()

                buttons.accepted.connect(_on_save)
                buttons.rejected.connect(dlg.reject)
                dlg.exec_()
            except Exception:
                logger.debug("[TimescaleSettingsDialog] _on_open_settings_editor 예외", exc_info=True)

        def _on_toggle_gap_autoscan(self, state: int) -> None:
            try:
                checked = bool(state)
                interval = int(os.getenv("GAP_SCAN_INTERVAL", "60"))
                if hasattr(self, "spinScanInterval"):
                    try:
                        interval = int(self.spinScanInterval.value())
                    except Exception:
                        interval = int(os.getenv("GAP_SCAN_INTERVAL", "60"))
                if checked:
                    if self._auto_scan_timer is None:
                        self._auto_scan_timer = QTimer(self)
                        self._auto_scan_timer.timeout.connect(lambda: threading.Thread(target=self.load_gaps, daemon=True).start())
                    self._auto_scan_timer.start(max(5, interval) * 1000)
                    self._append_log(f"🔁 Gap 자동 스캔 시작 (간격 {interval}s)")
                else:
                    if self._auto_scan_timer:
                        self._auto_scan_timer.stop()
                    self._append_log("🔁 Gap 자동 스캔 중지")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] 자동스캔 토글 예외", exc_info=True)

        def _on_change_scan_interval(self, value: int) -> None:
            try:
                if self._auto_scan_timer and self._auto_scan_timer.isActive():
                    self._auto_scan_timer.setInterval(max(5, int(value)) * 1000)
                    self._append_log(f"🔁 Gap 자동 스캔 간격 변경: {int(value)}s")
            except Exception:
                pass

        def _append_log(self, msg: str) -> None:
            try:
                now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                full = f"[{now}] {msg}"
                if self._recent_log_msgs and self._recent_log_msgs[-1] == msg:
                    return
                self._recent_log_msgs.append(msg)
                if len(self._recent_log_msgs) > 200:
                    self._recent_log_msgs.pop(0)
                if hasattr(self, "textLogGaps"):
                    try:
                        self.textLogGaps.append(full)
                        self.textLogGaps.verticalScrollBar().setValue(self.textLogGaps.verticalScrollBar().maximum())
                    except Exception:
                        pass
                else:
                    if hasattr(self, "labelConnStatus"):
                        self.labelConnStatus.setText(msg[:200])
            except Exception:
                logger.debug("[TimescaleSettingsDialog] 로그 추가 예외", exc_info=True)

        def _on_open_gap_monitor(self) -> None:
            """Gap 모니터 다이얼로그를 모달로 엽니다 (관리자용)."""
            if GapMonitorDialog is None:
                QMessageBox.warning(self, "Gap 모니터", "Gap 모니터 모듈을 찾을 수 없습니다. 파일이 존재하는지 확인하세요.")
                return
            try:
                dlg = GapMonitorDialog(self)
                dlg.exec_()
            except Exception as e:
                logger.exception("Gap 모니터 실행 중 오류: %s", e)
                QMessageBox.warning(self, "오류", f"Gap 모니터를 여는 중 오류가 발생했습니다: {e}")

        _MAX_REALTIME_LOG_ROWS = 100  # 실시간 로그 최대 표시 행 수

        # ------------------------------------------------------------------
        # DB설계.md 요구 메서드 — 실시간 통신 모니터 (Tab 2)
        # ------------------------------------------------------------------

        def _init_live_monitor(self) -> None:
            """Tab 2: 실시간 통신 모니터 초기화.

            widget_live_chart_container 에 PyQtGraph Dual Y-Axis 차트를 삽입합니다.
            """
            try:
                import pyqtgraph as pg
                from PyQt5.QtWidgets import QVBoxLayout as _QVBoxLayout

                container = getattr(self, "widget_live_chart_container", None)
                if container is None:
                    # 기존 chartContainer 폴백 (이전 UI 버전 호환)
                    container = getattr(self, "chartContainer", None)

                if container is None:
                    return

                layout = container.layout()
                if layout is None:
                    layout = _QVBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)

                self.plot_widget = pg.PlotWidget()
                self.plot_widget.setBackground("w")  # 라이트 모드 배경
                self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
                self.plot_widget.setLabel("left", "QPS", color="#000000")
                self.plot_widget.setLabel("bottom", "Time (s)", color="#000000")
                layout.addWidget(self.plot_widget)

                self.curve_qps = self.plot_widget.plot(
                    pen=pg.mkPen(color="#007AFF", width=2), name="QPS"
                )
                self.curve_p95 = self.plot_widget.plot(
                    pen=pg.mkPen(color="#FF3B30", width=2), name="P95 (ms)"
                )
                self._live_chart_data_qps: list = []
                self._live_chart_data_p95: list = []
                logger.info("[TimescaleSettingsDialog] 실시간 통신 모니터 차트 초기화 완료")

            except ImportError:
                logger.debug("[TimescaleSettingsDialog] pyqtgraph 미설치 — 차트 비활성화")
            except Exception as exc:
                logger.warning("[TimescaleSettingsDialog] _init_live_monitor 실패: %s", exc)

        def _on_tick(self) -> None:
            """1초마다 호출 — 실시간 통신 모니터 갱신."""
            try:
                self._update_live_log()
                self._update_live_chart()
            except Exception as exc:
                logger.debug("[TimescaleSettingsDialog] _on_tick 실패: %s", exc)

        def _update_live_log(self) -> None:
            """Live Query Log 테이블 갱신.

            table_live_log (신규) 및 tableRealtimeQueries (기존) 모두 갱신합니다.
            """
            try:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

                for table_attr in ("table_live_log", "tableRealtimeQueries"):
                    tbl = getattr(self, table_attr, None)
                    if tbl is None:
                        continue
                    max_rows = getattr(self, "_MAX_REALTIME_LOG_ROWS", 100)
                    row = tbl.rowCount()
                    if row >= max_rows:
                        tbl.removeRow(0)
                        row = tbl.rowCount()
                    tbl.insertRow(row)
                    tbl.setItem(row, 0, QTableWidgetItem(ts))
                    tbl.setItem(row, 1, QTableWidgetItem("heartbeat"))
                    tbl.setItem(row, 2, QTableWidgetItem("-"))
                    tbl.setItem(row, 3, QTableWidgetItem("-"))
                    tbl.setItem(row, 4, QTableWidgetItem("OK"))
                    tbl.scrollToBottom()
            except Exception as exc:
                logger.debug("[TimescaleSettingsDialog] _update_live_log 실패: %s", exc)

        def _update_live_chart(self) -> None:
            """PyQtGraph 실시간 차트 데이터 갱신 (60초 롤링 윈도우).

            QPS 데이터를 curve_qps 에 반영하고, P95 레이턴시를 curve_p95 에 반영합니다.
            실제 DB 계측 데이터가 없는 경우 0으로 플레이스홀더를 표시합니다.
            """
            try:
                if not hasattr(self, "curve_qps"):
                    return
                import time as _time_mod

                now = _time_mod.time()
                cutoff = now - 60.0

                # QPS 데이터 (실제 계측 전 플레이스홀더 = 0)
                self._live_chart_data_qps.append((now, 0))
                self._live_chart_data_qps = [p for p in self._live_chart_data_qps if p[0] >= cutoff]

                # P95 레이턴시 데이터 (실제 계측 전 플레이스홀더 = 0)
                if not hasattr(self, "_live_chart_data_p95"):
                    self._live_chart_data_p95 = []
                self._live_chart_data_p95.append((now, 0))
                self._live_chart_data_p95 = [p for p in self._live_chart_data_p95 if p[0] >= cutoff]

                if self._live_chart_data_qps:
                    t0 = self._live_chart_data_qps[0][0]
                    xs_qps = [p[0] - t0 for p in self._live_chart_data_qps]
                    ys_qps = [p[1] for p in self._live_chart_data_qps]
                    self.curve_qps.setData(xs_qps, ys_qps)

                if hasattr(self, "curve_p95") and self._live_chart_data_p95:
                    t0 = self._live_chart_data_p95[0][0]
                    xs_p95 = [p[0] - t0 for p in self._live_chart_data_p95]
                    ys_p95 = [p[1] for p in self._live_chart_data_p95]
                    self.curve_p95.setData(xs_p95, ys_p95)

            except Exception as exc:
                logger.debug("[TimescaleSettingsDialog] _update_live_chart 실패: %s", exc)

        def _on_refresh_realtime(self) -> None:
            """실시간 통신 로그 갱신 (1초마다 호출) — _on_tick() 위임."""
            self._on_tick()

        def _on_search_data(self) -> None:
            """저장된 데이터 검색."""
            try:
                table_name = ""
                if hasattr(self, "comboTable"):
                    table_name = self.comboTable.currentText().strip()
                keyword = ""
                if hasattr(self, "lineFilter"):
                    keyword = self.lineFilter.text().strip()
                logger.debug("[TimescaleSettingsDialog] 검색: table=%s keyword=%s", table_name, keyword)
                # 실제 DB 검색은 백그라운드 스레드에서 수행
                threading.Thread(target=self._do_search_data, args=(table_name, keyword, 1), daemon=True).start()
            except Exception:
                logger.debug("[TimescaleSettingsDialog] on_search_data 예외", exc_info=True)

        def _do_search_data(self, table_name: str, keyword: str, page: int) -> None:
            """백그라운드에서 데이터 검색 후 테이블 갱신 (TODO: DB 연동 구현 예정)."""
            # 실제 DB 연결 후 쿼리 실행 및 tableData 업데이트 구현 예정
            pass

        def _on_prev_page(self) -> None:
            """이전 페이지로 이동."""
            try:
                if self._current_page > 1:
                    self._current_page -= 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_next_page(self) -> None:
            """다음 페이지로 이동."""
            try:
                if self._current_page < self._total_pages:
                    self._current_page += 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"페이지: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_export_csv(self) -> None:
            """저장된 데이터 CSV 내보내기."""
            try:
                if not hasattr(self, "tableData"):
                    return
                filename, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "", "CSV Files (*.csv)")
                if not filename:
                    return
                with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    # 헤더 행
                    headers = []
                    for col in range(self.tableData.columnCount()):
                        item = self.tableData.horizontalHeaderItem(col)
                        headers.append(item.text() if item else str(col))
                    writer.writerow(headers)
                    # 데이터 행
                    for row in range(self.tableData.rowCount()):
                        row_data = []
                        for col in range(self.tableData.columnCount()):
                            item = self.tableData.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)
                QMessageBox.information(self, "CSV 저장", f"저장 완료: {filename}")
            except Exception as e:
                logger.debug("[TimescaleSettingsDialog] CSV 내보내기 예외: %s", e, exc_info=True)
                QMessageBox.warning(self, "오류", f"CSV 저장 실패: {e}")

        def closeEvent(self, event) -> None:
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _settings.setValue("timescale_geometry", self.saveGeometry())
            except Exception:
                pass
            try:
                if getattr(self, "_timer", None) and self._timer.isActive():
                    self._timer.stop()
                if getattr(self, "_auto_scan_timer", None) and self._auto_scan_timer.isActive():
                    self._auto_scan_timer.stop()
                if getattr(self, "_realtime_timer", None) and self._realtime_timer.isActive():
                    self._realtime_timer.stop()
            except Exception:
                pass
            super().closeEvent(event)

else:
    class TimescaleSettingsDialog:
        def __init__(self, parent=None):
            logger.warning("PyQt5 미설치 - TimescaleSettingsDialog 생성 불가")