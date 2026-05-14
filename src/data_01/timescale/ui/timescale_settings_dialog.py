# -*- coding: utf-8 -*-
"""
TimescaleSettingsDialog 而⑦듃濡ㅻ윭 (Gap 紐⑤땲???곕룞 ?ы븿)
- 蹂寃??붿?:
  * ?몃?/濡쒖뺄 紐⑤뱢 濡쒕뱶瑜??덉쟾???고???濡쒕뜑濡??섑뻾?섏뿬
    'src.data_01' ?뺥깭???앸퀎???뚮Ц??諛쒖깮?섎뒗 SyntaxError瑜??뚰뵾?⑸땲??
  * UI 諛붿씤?? 諛깃렇?쇱슫???ㅻ젅??議고쉶 ??湲곗〈 ?숈옉 ?좎?.
- 紐⑤뱺 二쇱꽍? ?쒓??낅땲??
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

# ?덉쟾???고???紐⑤뱢 濡쒕뜑 ?좏떥由ы떚
def _load_module_by_path(path: Path, name: str):
    """
    ?뚯씪 寃쎈줈濡쒕???紐⑤뱢??濡쒕뱶?섏뿬 諛섑솚?⑸땲??
    ?ㅽ뙣?섎㈃ None??諛섑솚?⑸땲??
    """
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception:
        logging.getLogger(__name__).debug("?뚯씪 寃쎈줈濡?紐⑤뱢 濡쒕뱶 ?ㅽ뙣: %s", path, exc_info=True)
    return None

def _try_import_pkg_or_path(pkg_name: str, attr: Optional[str], relative_file: Path, candidate_paths: List[Path]):
    """
    1) pkg_name?쇰줈 import ?쒕룄 (?⑦궎吏濡??ㅼ튂/紐⑤뱢 寃쎈줈媛 ?좏슚????
    2) ?ㅽ뙣?섎㈃ candidate_paths 由ъ뒪?몄뿉 ?덈뒗 ?뚯씪 寃쎈줈?ㅻ줈 ?쒕룄
    """
    try:
        mod = importlib.import_module(pkg_name)
        return getattr(mod, attr) if attr else mod
    except Exception:
        # ?뚯씪 寃쎈줈 ?대갚
        for p in candidate_paths:
            if p.exists():
                m = _load_module_by_path(p, p.stem)
                if m:
                    return getattr(m, attr) if attr and hasattr(m, attr) else (m if attr is None else None)
    return None

# timescale helper 遺덈윭?ㅺ린 (媛?ν븯硫??⑦궎吏 import, ?꾨땲硫??뚯씪 寃쎈줈)
_timescale_helpers = None
try:
    # package import ?쒕룄 (?뺤긽 ?⑦궎吏 ?섍꼍????
    _timescale_helpers = importlib.import_module("timescale_db")
except Exception:
    # ?꾨줈?앺듃 ???뚯씪 寃쎈줈濡??쒕룄: src/data_01/timescale/ui/timescale_db.py ?먮뒗 src/data_01/timescale/timescale_db.py
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

# enqueue_tasks (Redis push) ???⑦궎吏 ?먮뒗 timescale_redis ?뚯씪?먯꽌 ?쒕룄
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

# PyQt 濡쒕뱶
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

# GapMonitor ?ㅼ씠?쇰줈洹?濡쒕뱶: ?덉쟾 濡쒕뜑 ?ъ슜 (?⑦궎吏 import ?꾨땲???뚯씪 寃쎈줈 濡쒕뱶)
GapMonitorDialog = None
try:
    # 1) ?쇰컲 import ?쒕룄 (媛?μ꽦 ??쓬)
    gm = importlib.import_module("src.data_01.pipeline.ui.gap_monitor_dialog")
    GapMonitorDialog = getattr(gm, "GapMonitorDialog", None)
except Exception:
    # 2) ?뚯씪 寃쎈줈濡?濡쒕뱶: ../pipeline/ui/gap_monitor_dialog.py
    base = Path(__file__).resolve().parents[3]
    candidate = base / "data_01" / "pipeline" / "ui" / "gap_monitor_dialog.py"
    if candidate.exists():
        mod = _load_module_by_path(candidate, "gap_monitor_dialog")
        GapMonitorDialog = getattr(mod, "GapMonitorDialog", None)

if PYQT5_AVAILABLE:
    # ??젣 湲곕뒫 誘뱀뒪??濡쒕뱶 (?뚯씪 寃쎈줈 湲곕컲, SyntaxError ?덉쟾)
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
            """TimescaleDeleteMixin 濡쒕뱶 ?ㅽ뙣 ???ъ슜?섎뒗 鍮?誘뱀뒪??""
            def _bind_delete_signals(self): pass
            def _refresh_delete_counts(self): pass

    class TimescaleSettingsDialog(QDialog, _TimescaleDeleteMixin):
        """
        TimescaleSettingsDialog:
        - UI ?대깽??諛붿씤??
        - 湲곗〈 湲곕뒫(?곌껐?곹깭/Hypertable/Compression/ContAggs/Gaps/Backfills/Raw) ?좎?
        - Gap 紐⑤땲???ㅼ씠?쇰줈洹몃? ?덉쟾?섍쾶 ?대룄濡?援ы쁽
        - ?곗씠????젣 ??(TimescaleDeleteMixin)
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
            # UI 濡쒕뱶
            if _UI_PATH.exists():
                uic.loadUi(str(_UI_PATH), self)
            else:
                raise FileNotFoundError("timescale_settings.ui ?뚯씪??李얠쓣 ???놁뒿?덈떎.")

            # DB ?묒냽 湲곕낯 ?ㅼ젙 (?섍꼍蹂??湲곕컲)
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

            # DSN ?쒖떆
            try:
                if hasattr(self, "editDSN") and self.editDSN is not None:
                    libpq = f"host={self._config['host']} port={self._config['port']} dbname={self._config['dbname']} user={self._config['user']}"
                    self.editDSN.setText(libpq)
            except Exception:
                pass

            # 諛붿씤??
            self._bind_signals()

            # ??젣 ??踰꾪듉 諛붿씤??(TimescaleDeleteMixin)
            self._bind_delete_signals()
            self._refresh_delete_counts()

            # ?쒓렇???곌껐
            self._sig_conn_status_ready.connect(self._update_conn_status_ui)
            self._sig_hypertables_ready.connect(self._update_hypertables_ui)
            self._sig_compression_ready.connect(self._update_compression_ui)
            self._sig_aggs_ready.connect(self._update_aggs_ui)
            self._sig_gaps_ready.connect(self._update_gaps_ui)
            self._sig_backfills_ready.connect(self._update_backfills_ui)
            self._sig_raw_ready.connect(self._update_raw_table_ui)

            # 二쇨린???꾩껜 ?덈줈怨좎묠
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(lambda: threading.Thread(target=self._refresh_all, daemon=True).start())
            self._timer.start()

            # 珥덇린 濡쒕뱶 (諛깃렇?쇱슫??
            threading.Thread(target=self._refresh_all, daemon=True).start()

            # raw table ?ㅻ뜑 ?ㅼ젙
            try:
                if hasattr(self, "tableRawData") and isinstance(self.tableRawData, QTableWidget):
                    self.tableRawData.setColumnCount(6)
                    self.tableRawData.setHorizontalHeaderLabels(["trade_id", "exchange_ts", "symbol", "price", "qty", "side"])
                    self.tableRawData.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            except Exception:
                pass

            # 鍮꾨え???앹뾽 ?ㅼ젙
            self.setWindowModality(Qt.NonModal)
            self.setAttribute(Qt.WA_DeleteOnClose, False)

            # ?섏씠吏?ㅼ씠???곹깭
            self._current_page: int = 1
            self._total_pages: int = 1
            self._page_size: int = 100

            # ?ㅼ떆媛?媛깆떊 ??대㉧ (1珥?
            self._realtime_timer = QTimer(self)
            self._realtime_timer.setInterval(1000)
            self._realtime_timer.timeout.connect(self._on_refresh_realtime)
            self._realtime_timer.start()

            # PyQtGraph 李⑦듃 珥덇린??(Tab 2: ?ㅼ떆媛??듭떊 紐⑤땲??
            self._init_live_monitor()

            # 李??꾩튂 蹂듭썝
            try:
                from PyQt5.QtCore import QSettings
                _settings = QSettings("UpbitTrader", "DBMonitor")
                _geometry = _settings.value("timescale_geometry")
                if _geometry:
                    self.restoreGeometry(_geometry)
            except Exception:
                pass

            # ?ㅽ겕 紐⑤뱶 ?ㅽ???
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
                        logger.debug("踰꾪듉 諛붿씤???ㅽ뙣: %s", attr, exc_info=True)

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
                logger.debug("load_conn_status ?덉쇅", exc_info=True)

        def _update_conn_status_ui(self, data: Dict[str, Any]) -> None:
            try:
                if hasattr(self, "labelConnStatus"):
                    status = data.get("status", "disconnected")
                    color = "#2ECC40" if status == "connected" else "#FF4136"
                    text = "???곌껐?? if status == "connected" else "???곌껐 ?ㅽ뙣"
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
                logger.debug("_update_conn_status_ui ?덉쇅", exc_info=True)

        def load_hypertables(self) -> None:
            try:
                if fetch_hypertables is None:
                    return
                rows, err = fetch_hypertables(self._config)
                self._sig_hypertables_ready.emit(rows)
            except Exception:
                logger.debug("load_hypertables ?덉쇅", exc_info=True)

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
                logger.debug("_update_hypertables_ui ?덉쇅", exc_info=True)

        def load_compression_policies(self) -> None:
            try:
                if fetch_compression_policies is None:
                    return
                rows, err = fetch_compression_policies(self._config)
                self._sig_compression_ready.emit(rows)
            except Exception:
                logger.debug("load_compression_policies ?덉쇅", exc_info=True)

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
                logger.debug("_update_compression_ui ?덉쇅", exc_info=True)

        def load_continuous_aggs(self) -> None:
            try:
                if fetch_continuous_aggs is None:
                    return
                rows, err = fetch_continuous_aggs(self._config)
                self._sig_aggs_ready.emit(rows)
            except Exception:
                logger.debug("load_continuous_aggs ?덉쇅", exc_info=True)

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
                logger.debug("_update_aggs_ui ?덉쇅", exc_info=True)

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
                        self.labelRawStatus.setText("議고쉶 以?..")
                    except Exception:
                        pass

                threading.Thread(target=self._load_raw_worker, args=(symbol_filter, limit), daemon=True).start()
            except Exception:
                logger.debug("_on_load_raw ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "?먯떆 ?곗씠??議고쉶瑜??쒖옉?섎뒗 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _load_raw_worker(self, symbol_filter: str, limit: int) -> None:
            try:
                try:
                    import psycopg2  # type: ignore
                except Exception:
                    self._append_log("psycopg2 誘몄꽕移? pip install psycopg2-binary")
                    self._update_label_raw_status("?섏〈??遺議? psycopg2 誘몄꽕移?)
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
                    msg = f"DB ?곌껐 ?ㅽ뙣: {e}"
                    self._append_log(msg)
                    self._update_label_raw_status("DB ?곌껐 ?ㅽ뙣")
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
                    msg = f"荑쇰━ ?ㅽ뙣: {e}"
                    self._append_log(msg)
                    self._update_label_raw_status("荑쇰━ ?ㅽ뙣")
                    return
                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

                self._sig_raw_ready.emit(rows)
                self._update_label_raw_status(f"議고쉶 ?꾨즺: {len(rows)}嫄?)
            except Exception:
                logger.debug("_load_raw_worker ?덉쇅", exc_info=True)
                self._update_label_raw_status("議고쉶 以??덉쇅 諛쒖깮")

        def _update_label_raw_status(self, txt: str) -> None:
            try:
                if hasattr(self, "labelRawStatus"):
                    self.labelRawStatus.setText(txt)
                self._append_log(f"[Raw] {txt}")
            except Exception:
                logger.debug("_update_label_raw_status ?덉쇅", exc_info=True)

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
                logger.debug("_update_raw_table_ui ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "?먯떆 ?곗씠???뚯씠釉??낅뜲?댄듃 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _on_export_raw_csv(self) -> None:
            try:
                if not hasattr(self, "tableRawData"):
                    QMessageBox.information(self, "?대낫?닿린", "?대낫???먯떆 ?곗씠?곌? ?놁뒿?덈떎.")
                    return
                row_count = self.tableRawData.rowCount()
                if row_count == 0:
                    QMessageBox.information(self, "?대낫?닿린", "?대낫???먯떆 ?곗씠?곌? ?놁뒿?덈떎.")
                    return

                path, _ = QFileDialog.getSaveFileName(self, "Raw ?곗씠??CSV ???, "market_ticks.csv", "CSV Files (*.csv)")
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
                QMessageBox.information(self, "?대낫?닿린", f"CSV ????꾨즺: {path}")
                self._append_log(f"Raw CSV ??? {path}")
            except Exception:
                logger.debug("_on_export_raw_csv ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "CSV ???以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def load_gaps(self) -> None:
            try:
                if fetch_gaps is None:
                    return
                symbol_filter = ""
                if hasattr(self, "editSymbolFilter"):
                    symbol_filter = str(self.editSymbolFilter.text()).strip()
                rows, err = fetch_gaps(self._config, symbol_filter, int(os.getenv("GAP_THRESHOLD_SECONDS", "300")))
                if rows is None:
                    rows = [["(?ㅻ쪟)","-","-","-","-","-","-"]]
                self._sig_gaps_ready.emit(rows)
            except Exception:
                logger.debug("load_gaps ?덉쇅", exc_info=True)

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
                logger.debug("_update_gaps_ui ?덉쇅", exc_info=True)

        def load_backfills(self) -> None:
            try:
                if fetch_backfills is None:
                    return
                rows, err = fetch_backfills(self._config)
                self._sig_backfills_ready.emit(rows)
            except Exception:
                logger.debug("load_backfills ?덉쇅", exc_info=True)

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
                logger.debug("_update_backfills_ui ?덉쇅", exc_info=True)

        def _on_add_gaps_to_queue(self) -> None:
            try:
                sel = self.tableGaps.selectionModel().selectedRows()
                if not sel:
                    QMessageBox.information(self, "?좏깮 ?꾩슂", "Redis??異붽???Gap???좏깮?섏꽭??")
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
                        gap_seconds = float(gap_seconds_raw) if gap_seconds_raw not in ("-", "(媛??놁쓬)", "(?ㅻ쪟)", "") else 0.0
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
                    QMessageBox.warning(self, "Redis ?ㅻ쪟", "Redis 紐⑤뱢 誘몄꽕移??먮뒗 濡쒕뱶 ?ㅽ뙣")
                    return
                added, errors = enqueue_tasks(tasks)
                QMessageBox.information(self, "Redis Push", f"異붽? ?깃났: {added}嫄?n?ㅻ쪟: {len(errors)}嫄?)
            except Exception:
                logger.debug("_on_add_gaps_to_queue ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "Redis ??異붽? 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _on_export_gaps(self) -> None:
            try:
                if not getattr(self, "_last_gaps_rows", None):
                    QMessageBox.information(self, "?대낫?닿린", "?대낫??Gap ?곗씠?곌? ?놁뒿?덈떎.")
                    return
                path, _ = QFileDialog.getSaveFileName(self, "Gap 紐⑸줉 CSV濡????, "gaps.csv", "CSV Files (*.csv)")
                if not path:
                    return
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["symbol","timeframe","gap_start","gap_end","missing_seconds","priority","backfill_state"])
                    for row in self._last_gaps_rows:
                        writer.writerow([str(c) for c in row])
                QMessageBox.information(self, "?대낫?닿린", f"CSV ????꾨즺: {path}")
            except Exception:
                logger.debug("_on_export_gaps ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "CSV ???以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _on_start_backfill(self) -> None:
            try:
                tbl = getattr(self, "tableGaps", None)
                if tbl is None:
                    QMessageBox.information(self, "諛깊븘", "Gap ?뚯씠釉붿씠 ?놁뒿?덈떎.")
                    return
                sel = tbl.selectionModel().selectedRows()
                if not sel:
                    QMessageBox.information(self, "諛깊븘", "?쒖옉??Gap???좏깮?섏꽭??")
                    return
                count = len(sel)
                QMessageBox.information(self, "諛깊븘", f"諛깊븘 ?쒖옉 ?붿껌: {count}嫄?(UI ?ㅽ뀅)")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] _on_start_backfill ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "諛깊븘 ?쒖옉 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _on_cancel_backfill(self) -> None:
            try:
                tbl = getattr(self, "tableBackfills", None)
                if tbl is None:
                    QMessageBox.information(self, "諛깊븘 痍⑥냼", "諛깊븘 ?뚯씠釉붿씠 ?놁뒿?덈떎.")
                    return
                items = tbl.selectedItems()
                if not items:
                    QMessageBox.information(self, "諛깊븘 痍⑥냼", "痍⑥냼??諛깊븘 ??ぉ???좏깮?섏꽭??")
                    return
                rows_selected = {it.row() for it in items}
                QMessageBox.information(self, "諛깊븘 痍⑥냼", f"諛깊븘 痍⑥냼 ?붿껌: {len(rows_selected)}嫄?(UI ?ㅽ뀅)")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] _on_cancel_backfill ?덉쇅", exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", "諛깊븘 痍⑥냼 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.")

        def _on_open_settings_editor(self) -> None:
            try:
                dlg = QDialog(self)
                dlg.setWindowTitle("Timescale ?곌껐 ?ㅼ젙 ?몄쭛")
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

                form.addRow("?몄뒪??", le_host)
                form.addRow("?ы듃:", le_port)
                form.addRow("?곗씠?곕쿋?댁뒪:", le_db)
                form.addRow("?ъ슜??", le_user)
                form.addRow("鍮꾨?踰덊샇:", le_pass)

                buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dlg)
                form.addRow(buttons)

                def _on_save():
                    new_host = le_host.text().strip()
                    new_port = le_port.text().strip()
                    new_db = le_db.text().strip()
                    new_user = le_user.text().strip()
                    new_pass = le_pass.text()

                    if not new_host or not new_db:
                        QMessageBox.warning(self, "?낅젰 ?ㅻ쪟", "?몄뒪?몄? ?곗씠?곕쿋?댁뒪紐낆? ?꾩닔?낅땲??")
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
                logger.debug("[TimescaleSettingsDialog] _on_open_settings_editor ?덉쇅", exc_info=True)

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
                    self._append_log(f"?봺 Gap ?먮룞 ?ㅼ틪 ?쒖옉 (媛꾧꺽 {interval}s)")
                else:
                    if self._auto_scan_timer:
                        self._auto_scan_timer.stop()
                    self._append_log("?봺 Gap ?먮룞 ?ㅼ틪 以묒?")
            except Exception:
                logger.debug("[TimescaleSettingsDialog] ?먮룞?ㅼ틪 ?좉? ?덉쇅", exc_info=True)

        def _on_change_scan_interval(self, value: int) -> None:
            try:
                if self._auto_scan_timer and self._auto_scan_timer.isActive():
                    self._auto_scan_timer.setInterval(max(5, int(value)) * 1000)
                    self._append_log(f"?봺 Gap ?먮룞 ?ㅼ틪 媛꾧꺽 蹂寃? {int(value)}s")
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
                logger.debug("[TimescaleSettingsDialog] 濡쒓렇 異붽? ?덉쇅", exc_info=True)

        def _on_open_gap_monitor(self) -> None:
            """Gap 紐⑤땲???ㅼ씠?쇰줈洹몃? 紐⑤떖濡??쎈땲??(愿由ъ옄??."""
            if GapMonitorDialog is None:
                QMessageBox.warning(self, "Gap 紐⑤땲??, "Gap 紐⑤땲??紐⑤뱢??李얠쓣 ???놁뒿?덈떎. ?뚯씪??議댁옱?섎뒗吏 ?뺤씤?섏꽭??")
                return
            try:
                dlg = GapMonitorDialog(self)
                dlg.exec_()
            except Exception as e:
                logger.exception("Gap 紐⑤땲???ㅽ뻾 以??ㅻ쪟: %s", e)
                QMessageBox.warning(self, "?ㅻ쪟", f"Gap 紐⑤땲?곕? ?щ뒗 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎: {e}")

        _MAX_REALTIME_LOG_ROWS = 100  # ?ㅼ떆媛?濡쒓렇 理쒕? ?쒖떆 ????

        # ------------------------------------------------------------------
        # DB?ㅺ퀎.md ?붽뎄 硫붿꽌?????ㅼ떆媛??듭떊 紐⑤땲??(Tab 2)
        # ------------------------------------------------------------------

        def _init_live_monitor(self) -> None:
            """Tab 2: ?ㅼ떆媛??듭떊 紐⑤땲??珥덇린??

            widget_live_chart_container ??PyQtGraph Dual Y-Axis 李⑦듃瑜??쎌엯?⑸땲??
            """
            try:
                import pyqtgraph as pg
                from PyQt5.QtWidgets import QVBoxLayout as _QVBoxLayout

                container = getattr(self, "widget_live_chart_container", None)
                if container is None:
                    # 湲곗〈 chartContainer ?대갚 (?댁쟾 UI 踰꾩쟾 ?명솚)
                    container = getattr(self, "chartContainer", None)

                if container is None:
                    return

                layout = container.layout()
                if layout is None:
                    layout = _QVBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)

                self.plot_widget = pg.PlotWidget()
                self.plot_widget.setBackground("w")  # ?쇱씠??紐⑤뱶 諛곌꼍
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
                logger.info("[TimescaleSettingsDialog] ?ㅼ떆媛??듭떊 紐⑤땲??李⑦듃 珥덇린???꾨즺")

            except ImportError:
                logger.debug("[TimescaleSettingsDialog] pyqtgraph 誘몄꽕移???李⑦듃 鍮꾪솢?깊솕")
            except Exception as exc:
                logger.warning("[TimescaleSettingsDialog] _init_live_monitor ?ㅽ뙣: %s", exc)

        def _on_tick(self) -> None:
            """1珥덈쭏???몄텧 ???ㅼ떆媛??듭떊 紐⑤땲??媛깆떊."""
            try:
                self._update_live_log()
                self._update_live_chart()
            except Exception as exc:
                logger.debug("[TimescaleSettingsDialog] _on_tick ?ㅽ뙣: %s", exc)

        def _update_live_log(self) -> None:
            """Live Query Log ?뚯씠釉?媛깆떊.

            table_live_log (?좉퇋) 諛?tableRealtimeQueries (湲곗〈) 紐⑤몢 媛깆떊?⑸땲??
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
                logger.debug("[TimescaleSettingsDialog] _update_live_log ?ㅽ뙣: %s", exc)

        def _update_live_chart(self) -> None:
            """PyQtGraph ?ㅼ떆媛?李⑦듃 ?곗씠??媛깆떊 (60珥?濡ㅻ쭅 ?덈룄??.

            QPS ?곗씠?곕? curve_qps ??諛섏쁺?섍퀬, P95 ?덉씠?댁떆瑜?curve_p95 ??諛섏쁺?⑸땲??
            ?ㅼ젣 DB 怨꾩륫 ?곗씠?곌? ?녿뒗 寃쎌슦 0?쇰줈 ?뚮젅?댁뒪??붾? ?쒖떆?⑸땲??
            """
            try:
                if not hasattr(self, "curve_qps"):
                    return
                import time as _time_mod

                now = _time_mod.time()
                cutoff = now - 60.0

                # QPS ?곗씠??(?ㅼ젣 怨꾩륫 ???뚮젅?댁뒪???= 0)
                self._live_chart_data_qps.append((now, 0))
                self._live_chart_data_qps = [p for p in self._live_chart_data_qps if p[0] >= cutoff]

                # P95 ?덉씠?댁떆 ?곗씠??(?ㅼ젣 怨꾩륫 ???뚮젅?댁뒪???= 0)
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
                logger.debug("[TimescaleSettingsDialog] _update_live_chart ?ㅽ뙣: %s", exc)

        def _on_refresh_realtime(self) -> None:
            """?ㅼ떆媛??듭떊 濡쒓렇 媛깆떊 (1珥덈쭏???몄텧) ??_on_tick() ?꾩엫."""
            self._on_tick()

        def _on_search_data(self) -> None:
            """??λ맂 ?곗씠??寃??"""
            try:
                table_name = ""
                if hasattr(self, "comboTable"):
                    table_name = self.comboTable.currentText().strip()
                keyword = ""
                if hasattr(self, "lineFilter"):
                    keyword = self.lineFilter.text().strip()
                logger.debug("[TimescaleSettingsDialog] 寃?? table=%s keyword=%s", table_name, keyword)
                # ?ㅼ젣 DB 寃?됱? 諛깃렇?쇱슫???ㅻ젅?쒖뿉???섑뻾
                threading.Thread(target=self._do_search_data, args=(table_name, keyword, 1), daemon=True).start()
            except Exception:
                logger.debug("[TimescaleSettingsDialog] on_search_data ?덉쇅", exc_info=True)

        def _do_search_data(self, table_name: str, keyword: str, page: int) -> None:
            """諛깃렇?쇱슫?쒖뿉???곗씠??寃?????뚯씠釉?媛깆떊 (TODO: DB ?곕룞 援ы쁽 ?덉젙)."""
            # ?ㅼ젣 DB ?곌껐 ??荑쇰━ ?ㅽ뻾 諛?tableData ?낅뜲?댄듃 援ы쁽 ?덉젙
            pass

        def _on_prev_page(self) -> None:
            """?댁쟾 ?섏씠吏濡??대룞."""
            try:
                if self._current_page > 1:
                    self._current_page -= 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"?섏씠吏: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_next_page(self) -> None:
            """?ㅼ쓬 ?섏씠吏濡??대룞."""
            try:
                if self._current_page < self._total_pages:
                    self._current_page += 1
                    if hasattr(self, "labelPage"):
                        self.labelPage.setText(f"?섏씠吏: {self._current_page} / {self._total_pages}")
            except Exception:
                pass

        def _on_export_csv(self) -> None:
            """??λ맂 ?곗씠??CSV ?대낫?닿린."""
            try:
                if not hasattr(self, "tableData"):
                    return
                filename, _ = QFileDialog.getSaveFileName(self, "CSV ???, "", "CSV Files (*.csv)")
                if not filename:
                    return
                with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    # ?ㅻ뜑 ??
                    headers = []
                    for col in range(self.tableData.columnCount()):
                        item = self.tableData.horizontalHeaderItem(col)
                        headers.append(item.text() if item else str(col))
                    writer.writerow(headers)
                    # ?곗씠????
                    for row in range(self.tableData.rowCount()):
                        row_data = []
                        for col in range(self.tableData.columnCount()):
                            item = self.tableData.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)
                QMessageBox.information(self, "CSV ???, f"????꾨즺: {filename}")
            except Exception as e:
                logger.debug("[TimescaleSettingsDialog] CSV ?대낫?닿린 ?덉쇅: %s", e, exc_info=True)
                QMessageBox.warning(self, "?ㅻ쪟", f"CSV ????ㅽ뙣: {e}")

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
            logger.warning("PyQt5 誘몄꽕移?- TimescaleSettingsDialog ?앹꽦 遺덇?")
