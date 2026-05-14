# -*- coding: utf-8 -*-
"""TimescaleDB ????곗씠???곸꽭 議고쉶 ??

?섏씠?쇳뀒?대툝 ?곗씠?곕? ?섏씠吏?ㅼ씠???꾪꽣/?뺣젹/?쒕┫?ㅼ슫?쇰줈 議고쉶?⑸땲??
鍮꾨룞湲?QThread Worker ?⑦꽩 (硫붿씤?ㅻ젅??釉붾줈???놁쓬).

湲곗? UI (db_data_viewer.ui) ? ?숈씪 UX ?섏??쇰줈 留욎땄:
  - ?곷떒 ?꾪꽣: ?먯궛援?/ 嫄곕옒??/ ?щ낵 肄ㅻ낫 + ?쒓?쨌?곷Ц쨌珥덉꽦 寃??
  - ?곗씠?곗냼???꾨━?? / ????/ 議고쉶 踰꾪듉
  - ?щ낵 ?꾪꽣 / ?좎쭨 踰붿쐞
  - ?곹깭 諛곕꼫 (?곌껐 ?뺣낫, 留덉?留?議고쉶 ?쒓컖, ????
"""
from __future__ import annotations
import os
import sys
import logging
from typing import Optional, Dict, List, Tuple

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QFrame, QSizePolicy, QLineEdit,
    )
    from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# data_browser 怨듯넻 ?꾩젽 濡쒕뱶 (sys.path ?먯깋)
_DATA_BROWSER = None
try:
    from pathlib import Path as _Path
    # __file__ = src/data_01/timescale/ui/tabs/data_view_tab.py
    # parents[3] = src/data_01/
    _widget_dir = str(_Path(__file__).resolve().parents[3] / "ui" / "widgets")
    if _widget_dir not in sys.path:
        sys.path.insert(0, _widget_dir)
    from data_browser import DataBrowserWidget
    _DATA_BROWSER = DataBrowserWidget
except Exception:
    _DATA_BROWSER = None

logger = logging.getLogger(__name__)
if _DATA_BROWSER is None:
    logger.debug("[DataViewTab] DataBrowserWidget 濡쒕뱶 ?ㅽ뙣 (?대갚 QTableWidget ?ъ슜)")

# time 而щ읆 ?꾨낫 (?곗꽑?쒖쐞 ??
_TIME_CANDIDATES = ("time", "timestamp", "ts", "candle_time", "created_at", "inserted_at", "event_time")

# ?????꾨━???좏깮吏
_LIMIT_OPTIONS: List[Tuple[str, int]] = [
    ("100??, 100),
    ("200??, 200),
    ("500??, 500),
    ("1000??, 1000),
    ("2000??, 2000),
    ("5000??, 5000),
]

# ?꾨━??荑쇰━ (label, SQL ?쒗뵆由? time_column_hint)
# {limit} ???????꾨━?뗭쑝濡?移섑솚, time_column_hint=None ???먮룞 ?먯?, "none" ??ORDER BY ?놁쓬
_PRESETS: List[Tuple[str, str, Optional[str]]] = [
    ("candles ??理쒖떊",
     "SELECT * FROM candles ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("staging_candles ??理쒖떊",
     "SELECT * FROM staging_candles ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("candles_1m ??理쒖떊",
     "SELECT * FROM candles WHERE timeframe = '1m' ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("cagg_candles_5m ??理쒖떊",
     "SELECT * FROM cagg_candles_5m ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("cagg_candles_1h ??理쒖떊",
     "SELECT * FROM cagg_candles_1h ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("market_ticks ??理쒖떊",
     "SELECT * FROM market_ticks ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("orderbook_snapshots ??理쒖떊",
     "SELECT * FROM orderbook_snapshots ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("gap_fill_queue ??理쒖떊",
     "SELECT * FROM gap_fill_queue ORDER BY created_at DESC LIMIT {limit}",
     "created_at"),
    ("technical_indicators ??理쒖떊",
     "SELECT * FROM technical_indicators ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("?섏씠?쇳뀒?대툝 紐⑸줉",
     "SELECT hypertable_name, "
     "approximate_row_count(format('%I', hypertable_name)::regclass) AS rows, "
     "pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass)) AS size "
     "FROM timescaledb_information.hypertables ORDER BY hypertable_name",
     "none"),
    ("?곗냽 吏묎퀎(CAGG) 紐⑸줉",
     "SELECT view_name, view_schema, materialization_hypertable_name "
     "FROM timescaledb_information.continuous_aggregates ORDER BY view_name",
     "none"),
    ("泥?겕 紐⑸줉 (?꾩껜)",
     "SELECT hypertable_name, chunk_name, range_start, range_end, "
     "is_compressed FROM timescaledb_information.chunks ORDER BY range_start DESC LIMIT {limit}",
     "none"),
    ("?뺤텞 ?꾪솴",
     "SELECT h.hypertable_name, "
     "COUNT(c.chunk_name) FILTER(WHERE c.is_compressed) AS compressed_chunks, "
     "COUNT(c.chunk_name) FILTER(WHERE NOT c.is_compressed) AS uncompressed_chunks "
     "FROM timescaledb_information.hypertables h "
     "LEFT JOIN timescaledb_information.chunks c ON c.hypertable_name = h.hypertable_name "
     "GROUP BY h.hypertable_name ORDER BY h.hypertable_name",
     "none"),
    ("蹂댁〈 ?뺤콉",
     "SELECT hypertable_name, config->>'drop_after' AS drop_after, schedule_interval "
     "FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'",
     "none"),
]

if _HAS_QT:
    class _QueryWorker(QThread):
        finished = pyqtSignal(list, list)  # headers, rows
        error = pyqtSignal(str)
        warning = pyqtSignal(str)  # 鍮꾩튂紐?寃쎄퀬 (?쒓컙 而щ읆 ?먮룞?먯? ??

        def __init__(self, conn_params: dict, sql: str, time_hint: Optional[str] = None):
            super().__init__()
            self._conn_params = conn_params
            self._sql = sql
            self._time_hint = time_hint  # "none" | column_name | None(=auto-detect)
            self._params: tuple = ()   # parameterized query ?뚮씪誘명꽣 (SQL ?몄젥??諛⑹?)

        def _make_conn(self):
            import psycopg2
            try:
                from db_worker import build_connect_kwargs
                return psycopg2.connect(**build_connect_kwargs(self._conn_params, connect_timeout=5))
            except ImportError:
                pass
            p = self._conn_params
            host = p.get("host", "127.0.0.1") or "127.0.0.1"
            if str(host).lower() in ("localhost", ""):
                host = "127.0.0.1"
            port = int(p.get("port", 58529))
            db   = p.get("database") or p.get("db") or p.get("dbname") or "upbit_trader"
            user = p.get("user", "postgres") or "postgres"
            pw   = p.get("password") or p.get("pass") or ""
            return psycopg2.connect(
                host=host, port=port, database=db,
                user=user, password=pw, connect_timeout=5,
            )

        def _detect_time_col(self, conn, table_name: str) -> Optional[str]:
            """information_schema 濡?time 而щ읆 ?꾨낫瑜??먯?."""
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = %s AND table_schema = 'public' "
                        "ORDER BY ordinal_position",
                        (table_name,),
                    )
                    cols = {r[0] for r in cur.fetchall()}
                for candidate in _TIME_CANDIDATES:
                    if candidate in cols:
                        return candidate
            except Exception:
                pass
            return None

        def _extract_table_name(self, sql: str) -> Optional[str]:
            """SQL ?먯꽌 FROM ?ㅼ쓬 ?뚯씠釉붾챸(?ㅽ궎留??쒖젙???쒓굅)??異붿텧."""
            import re
            # public.candles ??candles, candles ??candles
            m = re.search(
                r"\bFROM\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)",
                sql, re.IGNORECASE,
            )
            return m.group(1) if m else None

        def run(self):
            import re
            try:
                conn = self._make_conn()
                try:
                    sql = self._sql
                    hint = self._time_hint

                    # hint="none" ??ORDER BY 議곗옉 ?놁씠 洹몃?濡??ㅽ뻾
                    if hint != "none":
                        table_name = self._extract_table_name(sql)
                        if table_name and hint is None:
                            detected = self._detect_time_col(conn, table_name)
                            if detected is None:
                                # time 而щ읆 ?놁쓬 ??ORDER BY ???쒓굅 (諛⑺뼢 ?ㅼ썙???덇굅???놁뼱??
                                sql = re.sub(
                                    r"\s*ORDER BY\s+\w+(?:\s+(?:DESC|ASC))?",
                                    "", sql, flags=re.IGNORECASE,
                                )
                                self.warning.emit(
                                    f"?좑툘 '{table_name}' ?뚯씠釉붿뿉??time 而щ읆??李얠? 紐삵빐 ORDER BY瑜??쒓굅?덉뒿?덈떎."
                                )
                            elif detected != "time":
                                # detected ??_TIME_CANDIDATES ?먯꽌 ???덉쟾???앸퀎??
                                safe_col = detected if detected in _TIME_CANDIDATES else "time"
                                sql = re.sub(
                                    r"\bORDER BY\s+time\b",
                                    f"ORDER BY {safe_col}",
                                    sql, flags=re.IGNORECASE,
                                )
                                self.warning.emit(
                                    f"?뱄툘 time ??'{safe_col}' 而щ읆?쇰줈 ORDER BY瑜??먮룞 援먯젙?덉뒿?덈떎."
                                )

                    with conn.cursor() as cur:
                        # self._params 媛 ?덉쑝硫??뚮씪誘명꽣 諛붿씤?⑹쑝濡??ㅽ뻾 (SQL ?몄젥??諛⑹?)
                        cur.execute(sql, self._params or None)
                        headers = [d[0] for d in (cur.description or [])]
                        rows = cur.fetchall()
                    self.finished.emit(headers, [list(r) for r in rows])
                finally:
                    conn.close()
            except Exception as exc:
                self.error.emit(str(exc)[:300])


    class DataViewTab(QWidget):
        """TimescaleDB ????곗씠???곸꽭 議고쉶 ??

        湲곗? UI(db_data_viewer.ui)? ?숈씪 UX:
        - ?곷떒 ?꾪꽣 諛? ?먯궛援?/ 嫄곕옒??/ ?щ낵 肄ㅻ낫 + ?쒓?쨌?곷Ц쨌珥덉꽦 寃??
        - ?꾨━??荑쇰━ ?좏깮 + ????+ 議고쉶 踰꾪듉
        - ?щ낵 ?꾪꽣 ?띿뒪??+ ?좎쭨 踰붿쐞
        - DataBrowserWidget (?뺣젹/?꾪꽣/?섏씠吏?ㅼ씠???쒕┫?ㅼ슫)
        - ?곹깭 諛곕꼫 (?곌껐 ?뺣낫, 留덉?留?議고쉶 ?쒓컖, ????
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._worker: Optional[_QueryWorker] = None
            # ?꾪꽣 Mixin ?곹깭 珥덇린??
            self._all_symbols: List[str] = []
            self._all_symbol_stats: list = []
            self._name_map: Optional[dict] = None
            self._name_en_map: Optional[dict] = None
            self._symbol_worker = None
            self._build_ui()
            self._bind_signals()

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)

            # 諛곕꼫
            banner = QLabel("?뾼截?TimescaleDB ??????곗씠???곸꽭 議고쉶")
            banner.setStyleSheet(
                "background:#1D4ED8;color:white;padding:10px 14px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)

            # ?곌껐 ?뺣낫 ??
            info_frame = QFrame()
            info_frame.setStyleSheet(
                "QFrame { background:#EFF6FF; border-left:4px solid #3B82F6;"
                " border-radius:3px; }"
            )
            info_layout = QHBoxLayout(info_frame)
            info_layout.setContentsMargins(10, 6, 10, 6)
            db_name = self._conn_params.get("database") or self._conn_params.get("db") or "upbit_trader"
            port    = self._conn_params.get("port", 58529)
            self._lbl_conn = QLabel(f"?뵆 DB: {db_name}  |  ?ы듃: {port}")
            self._lbl_conn.setStyleSheet("color:#1D4ED8;font-size:8pt;")
            info_layout.addWidget(self._lbl_conn)
            info_layout.addStretch()
            self._lbl_updated = QLabel("")
            self._lbl_updated.setStyleSheet("color:#6B7280;font-size:8pt;")
            info_layout.addWidget(self._lbl_updated)
            layout.addWidget(info_frame)

            # ?? ?곷떒 ?꾪꽣 諛?(湲곗? UI: db_data_viewer.ui ? ?숈씪 援ъ꽦) ??????????
            filter_bar = QHBoxLayout()
            filter_bar.setSpacing(4)

            filter_bar.addWidget(QLabel("?먯궛援?"))
            self._combo_asset = QComboBox()
            self._combo_asset.setMinimumWidth(105)
            filter_bar.addWidget(self._combo_asset)

            filter_bar.addWidget(QLabel("嫄곕옒??"))
            self._combo_exch = QComboBox()
            self._combo_exch.setMinimumWidth(95)
            filter_bar.addWidget(self._combo_exch)

            filter_bar.addWidget(QLabel("?щ낵:"))
            self._combo_sym = QComboBox()
            self._combo_sym.setMinimumWidth(130)
            self._combo_sym.setEditable(True)
            self._combo_sym.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            filter_bar.addWidget(self._combo_sym)

            filter_bar.addWidget(QLabel("寃??"))
            self._edit_search_filter = QLineEdit()
            self._edit_search_filter.setMinimumWidth(175)
            self._edit_search_filter.setPlaceholderText(
                "?щ낵쨌?쒓?쨌?곷Ц쨌珥덉꽦 寃??(?? shib, ?쒕컮, ?끹뀆)"
            )
            filter_bar.addWidget(self._edit_search_filter)

            self._lbl_search_result = QLabel("")
            self._lbl_search_result.setMinimumWidth(65)
            self._lbl_search_result.setStyleSheet("color:#2980b9;font-size:8pt;")
            filter_bar.addWidget(self._lbl_search_result)

            filter_bar.addStretch()
            layout.addLayout(filter_bar)

            # ?꾪꽣 肄ㅻ낫 珥덇린媛??ㅼ젙 (DataViewFilterMixin 濡쒖쭅 吏곸젒 ?몄텧)
            self._populate_asset_exchange_combos()

            # 議고쉶 議곌굔 ??1: ?꾨━??+ ????
            ctrl_row = QHBoxLayout()
            ctrl_row.addWidget(QLabel("?뚯씠釉??꾨━??"))
            self._combo = QComboBox()
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for label, _, _ in _PRESETS:
                self._combo.addItem(label)
            ctrl_row.addWidget(self._combo)
            ctrl_row.addWidget(QLabel("????"))
            self._limit_combo = QComboBox()
            for label, _ in _LIMIT_OPTIONS:
                self._limit_combo.addItem(label)
            self._limit_combo.setCurrentIndex(2)  # 湲곕낯: 500??
            self._limit_combo.setFixedWidth(70)
            ctrl_row.addWidget(self._limit_combo)
            self._btn_load = QPushButton("?봽 議고쉶")
            self._btn_load.setFixedWidth(80)
            self._btn_load.setStyleSheet(
                "QPushButton { background:#1D4ED8; color:white; border-radius:4px;"
                " padding:4px 10px; font-weight:bold; }"
                "QPushButton:hover { background:#1E40AF; }"
                "QPushButton:disabled { background:#9CA3AF; }"
            )
            ctrl_row.addWidget(self._btn_load)
            layout.addLayout(ctrl_row)

            # 議고쉶 議곌굔 ??2: ?щ낵 ?꾪꽣 + ?좎쭨 踰붿쐞 (?쒓퀎???뚯씠釉붿뿉留??쒖꽦??
            try:
                from PyQt5.QtWidgets import QDateEdit, QCheckBox
                from PyQt5.QtCore import QDate
                _HAS_DATE = True
            except ImportError:
                _HAS_DATE = False
                QDateEdit = QCheckBox = QDate = None  # type: ignore[misc,assignment]

            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("?щ낵 ?꾪꽣:"))
            self._edit_symbol = QLineEdit()
            self._edit_symbol.setPlaceholderText("?? KRW-BTC  (鍮꾩썙?먮㈃ ?꾩껜)")
            self._edit_symbol.setFixedWidth(160)
            filter_row.addWidget(self._edit_symbol)

            filter_row.addWidget(QLabel("?좎쭨踰붿쐞:"))
            self._chk_date = None
            if _HAS_DATE:
                # QDateEdit/QCheckBox/QDate ?대? import??(以묐났 import ?쒓굅)
                self._chk_date = QCheckBox("?ъ슜")
                self._chk_date.setChecked(False)
                filter_row.addWidget(self._chk_date)
                today = QDate.currentDate()
                self._date_from = QDateEdit(today.addDays(-7))
                self._date_from.setCalendarPopup(True)
                self._date_from.setDisplayFormat("yyyy-MM-dd")
                self._date_from.setEnabled(False)
                filter_row.addWidget(self._date_from)
                filter_row.addWidget(QLabel("~"))
                self._date_to = QDateEdit(today)
                self._date_to.setCalendarPopup(True)
                self._date_to.setDisplayFormat("yyyy-MM-dd")
                self._date_to.setEnabled(False)
                filter_row.addWidget(self._date_to)
                self._chk_date.toggled.connect(self._date_from.setEnabled)
                self._chk_date.toggled.connect(self._date_to.setEnabled)
            else:
                self._date_from = None
                self._date_to = None

            filter_row.addStretch()
            layout.addLayout(filter_row)

            # 寃쎄퀬 ?덉씠釉?(time 而щ읆 ?먮룞?먯? ???쒖떆)
            self._lbl_warn = QLabel("")
            self._lbl_warn.setStyleSheet(
                "background:#FEF9C3;color:#92400E;padding:4px 8px;"
                "border-radius:3px;font-size:8pt;"
            )
            self._lbl_warn.setVisible(False)
            layout.addWidget(self._lbl_warn)

            # 釉뚮씪?곗? ?꾩젽 (DataBrowserWidget ?곗꽑, ?대갚 QTableWidget)
            if _DATA_BROWSER is not None:
                self._browser = _DATA_BROWSER()
                self._has_browser = True
            else:
                from PyQt5.QtWidgets import QTableWidget
                self._browser = QTableWidget()
                self._has_browser = False
            layout.addWidget(self._browser)

            # ?곹깭 ?덉씠釉?
            self._status = QLabel("燧??뚯씠釉??꾨━?뗭쓣 ?좏깮?섍퀬 [議고쉶] 踰꾪듉???꾨Ⅴ?몄슂.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)
            # ?? ?곷떒 ?꾪꽣 ?쒓렇???곌껐 ??????????????????????????????????????
            self._combo_asset.currentIndexChanged.connect(self._on_asset_filter_changed)
            self._combo_exch.currentIndexChanged.connect(self._on_exchange_filter_changed)
            self._combo_sym.currentTextChanged.connect(self._on_sym_combo_changed)
            self._edit_search_filter.textChanged.connect(self._on_search_filter)

        # ------------------------------------------------------------------
        # ?곷떒 ?꾪꽣 諛?硫붿꽌??(DataViewFilterMixin 濡쒖쭅 ?몃씪??
        # ------------------------------------------------------------------

        def _populate_asset_exchange_combos(self) -> None:
            """?먯궛援?嫄곕옒??肄ㅻ낫 珥덇린媛??ㅼ젙 (DataViewFilterMixin._populate_filter_combos 濡쒖쭅)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._populate_filter_combos(self)

        def _on_asset_filter_changed(self, _index: int = 0) -> None:
            """?먯궛援?蹂寃???嫄곕옒??肄ㅻ낫 ?숆린??"""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_asset_filter_changed(self, _index)

        def _on_exchange_filter_changed(self, _index: int = 0) -> None:
            """嫄곕옒??蹂寃????щ낵 肄ㅻ낫 ?꾪꽣留?"""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_exchange_filter_changed(self, _index)

        def _on_search_filter(self, text: str) -> None:
            """寃?됱뼱 ?낅젰 ???щ낵 肄ㅻ낫 ?꾪꽣留?(?쒓?/珥덉꽦/?곷Ц)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_search_filter(self, text)

        def _filter_symbols_by_asset_exchange(self) -> None:
            """?먯궛援걔룰굅?섏냼 湲곗??쇰줈 ?щ낵 肄ㅻ낫瑜??꾪꽣留곹빀?덈떎 (DataViewFilterMixin ?꾩엫)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._filter_symbols_by_asset_exchange(self)

        def _update_filter_result_label(self, count: int, show: bool) -> None:
            """寃??寃곌낵 ???덉씠釉붿쓣 媛깆떊?⑸땲??"""
            lbl = getattr(self, "_lbl_search_result", None)
            if lbl is None:
                return
            lbl.setText(f"{count}媛?留ㅼ묶" if show else "")

        def _on_sym_combo_changed(self, text: str) -> None:
            """?щ낵 肄ㅻ낫 蹂寃???_edit_symbol(SQL 荑쇰━?? ?먮룄 諛섏쁺?⑸땲??"""
            edit = getattr(self, "_edit_symbol", None)
            if edit is not None:
                edit.blockSignals(True)
                edit.setText(text)
                edit.blockSignals(False)

        def _on_symbols_loaded(self, symbols: list) -> None:
            """?щ낵 濡쒕뱶 ?꾨즺 ??肄ㅻ낫 媛깆떊."""
            self._all_symbols = symbols or []
            self._refresh_symbol_combo(self._all_symbols)

        def _on_symbols_error(self, _msg: str) -> None:
            """?щ낵 濡쒕뱶 ?ㅽ뙣 ??湲곕낯 ?щ낵 ?좎?."""
            try:
                from data_view_filter_mixin import _DEFAULT_SYMBOLS as _DS
            except ImportError:
                try:
                    from .data_view_filter_mixin import _DEFAULT_SYMBOLS as _DS  # type: ignore[no-redef]
                except ImportError:
                    return
            if not self._all_symbols:
                self._all_symbols = list(_DS)
                self._refresh_symbol_combo(self._all_symbols)

        def _refresh_symbol_combo(self, symbols: list) -> None:
            """?щ낵 肄ㅻ낫 ?댁슜??援먯껜?⑸땲??"""
            combo = getattr(self, "_combo_sym", None)
            if combo is None:
                return
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(symbols)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        def _start_symbol_load_from_db(self) -> None:
            """candles ?뚯씠釉붿뿉???щ낵 紐⑸줉??鍮꾨룞湲?濡쒕뱶?⑸땲??"""
            try:
                from data_view_filter_mixin import _SymbolLoadWorker
            except ImportError:
                try:
                    from .data_view_filter_mixin import _SymbolLoadWorker  # type: ignore[no-redef]
                except ImportError:
                    return
            if getattr(self, "_symbol_worker", None) and self._symbol_worker.isRunning():
                return
            self._symbol_worker = _SymbolLoadWorker(self._conn_params)
            self._symbol_worker.finished.connect(self._on_symbols_loaded)
            self._symbol_worker.error.connect(self._on_symbols_error)
            self._symbol_worker.start()

        def _build_sql(self) -> Tuple[str, Optional[str], tuple]:
            """?꾩옱 議곌굔??留욌뒗 SQL 荑쇰━쨌time_hint쨌?뚮씪誘명꽣瑜??앹꽦?⑸땲??

            Returns:
                (sql, time_hint, params) ??params? parameterized query???쒗뵆.
                symbol 諛??좎쭨 ?꾪꽣??SQL ?몄젥??諛⑹?瑜??꾪빐 %s 諛붿씤?⑹쓣 ?ъ슜?⑸땲??
            """
            import re as _re
            idx = self._combo.currentIndex()
            if idx < 0 or idx >= len(_PRESETS):
                return "", None, ()
            _, sql_tmpl, time_hint = _PRESETS[idx]

            # {limit} 移섑솚 (?섎뱶肄붾뵫??_LIMIT_OPTIONS?먯꽌 媛?몄삤誘濡??몄젥???꾪뿕 ?놁쓬)
            limit_idx = self._limit_combo.currentIndex() if hasattr(self, "_limit_combo") else 2
            _, limit_val = _LIMIT_OPTIONS[limit_idx] if 0 <= limit_idx < len(_LIMIT_OPTIONS) else ("500??, 500)
            sql = sql_tmpl.replace("{limit}", str(limit_val))

            params: tuple = ()

            # ?щ낵 寃곗젙: ?곷떒 ?꾪꽣 肄ㅻ낫(_combo_sym) ?곗꽑, ?놁쑝硫??띿뒪???낅젰(_edit_symbol)
            sym_combo = getattr(self, "_combo_sym", None)
            sym_text_edit = getattr(self, "_edit_symbol", None)
            symbol = (
                sym_combo.currentText().strip() if sym_combo else ""
            ) or (
                sym_text_edit.text().strip() if sym_text_edit else ""
            )

            # ?щ낵 ?꾪꽣 ??%s ?뚮씪誘명꽣 諛붿씤?⑹쑝濡?SQL ?몄젥??諛⑹?
            if symbol and time_hint != "none":
                if _re.search(r"\bWHERE\b", sql, _re.IGNORECASE):
                    sql = _re.sub(
                        r"\bORDER BY\b",
                        "AND symbol = %s ORDER BY",
                        sql, flags=_re.IGNORECASE, count=1,
                    )
                else:
                    sql = _re.sub(
                        r"\bORDER BY\b",
                        "WHERE symbol = %s ORDER BY",
                        sql, flags=_re.IGNORECASE, count=1,
                    )
                params = params + (symbol,)

            # ?좎쭨 踰붿쐞 ?꾪꽣 ??%s ?뚮씪誘명꽣 諛붿씤?⑹쑝濡?SQL ?몄젥??諛⑹?
            if (
                time_hint not in (None, "none")
                and hasattr(self, "_chk_date")
                and self._chk_date is not None
                and self._chk_date.isChecked()
                and self._date_from is not None
                and self._date_to is not None
            ):
                date_from_str = self._date_from.date().toString("yyyy-MM-dd")
                date_to_str   = self._date_to.date().toString("yyyy-MM-dd")
                # time_hint??_PRESETS ?섎뱶肄붾뵫 ?곸닔 ???몄젥???꾪뿕 ?놁쓬
                time_col = time_hint
                date_filter = f"{time_col} >= %s AND {time_col} < (%s::date + interval '1 day')"
                if _re.search(r"\bWHERE\b", sql, _re.IGNORECASE):
                    sql = _re.sub(
                        r"\bORDER BY\b",
                        f"AND {date_filter} ORDER BY",
                        sql, flags=_re.IGNORECASE, count=1,
                    )
                else:
                    sql = _re.sub(
                        r"\bORDER BY\b",
                        f"WHERE {date_filter} ORDER BY",
                        sql, flags=_re.IGNORECASE, count=1,
                    )
                params = params + (date_from_str, date_to_str)

            return sql, time_hint, params

        @pyqtSlot()
        def _load_data(self) -> None:
            if self._worker and self._worker.isRunning():
                return
            sql, time_hint, params = self._build_sql()
            if not sql:
                return
            self._lbl_warn.setVisible(False)
            self._status.setStyleSheet("color:#F59E0B;font-size:8pt;")
            self._status.setText("??議고쉶 以?..")
            self._btn_load.setEnabled(False)
            self._worker = _QueryWorker(self._conn_params, sql, time_hint)
            # params瑜?Worker???꾨떖 (SQL ?몄젥??諛⑹?瑜??꾪빐 parameterized query ?ъ슜)
            if params:
                self._worker._params = params
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.warning.connect(self._on_warning)
            self._worker.start()

        @pyqtSlot(list, list)
        def _on_finished(self, headers: list, rows: list) -> None:
            from datetime import datetime
            self._btn_load.setEnabled(True)
            now = datetime.now().strftime("%H:%M:%S")
            self._lbl_updated.setText(f"留덉?留?議고쉶: {now}  |  {len(rows):,}??)
            if self._has_browser and hasattr(self._browser, "set_data"):
                self._browser.set_data(headers, rows)
                self._status.setStyleSheet("color:#16A34A;font-size:8pt;")
                self._status.setText(
                    f"??{len(rows):,}??議고쉶 ?꾨즺"
                    f" ({len(headers)}而щ읆) ???붾툝?대┃: ???곸꽭 蹂닿린 | ?ㅻ뜑 ?대┃: ?뺣젹"
                )
            else:
                # ?대갚: ?⑥닚 QTableWidget
                from PyQt5.QtWidgets import QTableWidgetItem
                tbl = self._browser
                tbl.setColumnCount(len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.setRowCount(len(rows))
                for r_idx, row in enumerate(rows):
                    for c_idx, val in enumerate(row):
                        tbl.setItem(r_idx, c_idx, QTableWidgetItem(str(val) if val is not None else ""))
                self._status.setStyleSheet("color:#16A34A;font-size:8pt;")
                self._status.setText(
                    f"??{len(rows):,}??議고쉶 ?꾨즺 ({len(headers)}而щ읆)"
                    " ??DataBrowserWidget 誘몃줈?? ?꾪꽣/?뺣젹/?섏씠吏?ㅼ씠??鍮꾪솢??
                )

        @pyqtSlot(str)
        def _on_warning(self, msg: str) -> None:
            self._lbl_warn.setText(msg)
            self._lbl_warn.setVisible(True)

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._btn_load.setEnabled(True)
            self._status.setStyleSheet("color:#DC2626;font-size:8pt;")
            # ?ъ슜??移쒗솕???ㅻ쪟 ?뚰듃 ?쒓났
            hint = ""
            if "does not exist" in msg.lower() or "relation" in msg.lower():
                hint = " ???뚯씠釉붿씠 ?꾩쭅 ?앹꽦?섏? ?딆븯?듬땲?? ?ㅻⅨ ?꾨━?뗭쓣 ?좏깮?섏꽭??"
            elif "connection" in msg.lower() or "connect" in msg.lower():
                hint = " ??DB ?곌껐 ?ㅽ뙣. Docker 而⑦뀒?대꼫 ?ㅽ뻾 ?щ? ?뺤씤: docker ps | grep timescale"
            elif "permission" in msg.lower():
                hint = " ??議고쉶 沅뚰븳???놁뒿?덈떎. DB ?ъ슜??沅뚰븳???뺤씤?섏꽭??"
            self._status.setText(f"?뵶 ?ㅻ쪟: {msg[:200]}{hint}")
            self._lbl_warn.setText(f"?좑툘 議고쉶 ?ㅽ뙣: {msg[:120]}{hint}")
            self._lbl_warn.setVisible(True)

        def start_updates(self, interval_ms: int = 0) -> None:
            self._start_symbol_load_from_db()
            self._load_data()

        def stop_updates(self) -> None:
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)
            sym_w = getattr(self, "_symbol_worker", None)
            if sym_w and hasattr(sym_w, "isRunning") and sym_w.isRunning():
                sym_w.quit()
                sym_w.wait(1000)

        def closeEvent(self, event) -> None:
            self.stop_updates()
            super().closeEvent(event)

else:
    class DataViewTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass

