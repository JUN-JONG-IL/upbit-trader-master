# -*- coding: utf-8 -*-
"""TimescaleDB 저장 데이터 상세 조회 탭

하이퍼테이블 데이터를 페이지네이션/필터/정렬/드릴다운으로 조회합니다.
비동기 QThread Worker 패턴 (메인스레드 블로킹 없음).

기준 UI (db_data_viewer.ui) 와 동일 UX 수준으로 맞춤:
  - 상단 필터: 자산군 / 거래소 / 심볼 콤보 + 한글·영문·초성 검색
  - 데이터소스(프리셋) / 행 수 / 조회 버튼
  - 심볼 필터 / 날짜 범위
  - 상태 배너 (연결 정보, 마지막 조회 시각, 행 수)
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

# data_browser 공통 위젯 로드 (sys.path 탐색)
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
    logger.debug("[DataViewTab] DataBrowserWidget 로드 실패 (폴백 QTableWidget 사용)")

# time 컬럼 후보 (우선순위 순)
_TIME_CANDIDATES = ("time", "timestamp", "ts", "candle_time", "created_at", "inserted_at", "event_time")

# 행 수 프리셋 선택지
_LIMIT_OPTIONS: List[Tuple[str, int]] = [
    ("100행", 100),
    ("200행", 200),
    ("500행", 500),
    ("1000행", 1000),
    ("2000행", 2000),
    ("5000행", 5000),
]

# 프리셋 쿼리 (label, SQL 템플릿, time_column_hint)
# {limit} → 행 수 프리셋으로 치환, time_column_hint=None → 자동 탐지, "none" → ORDER BY 없음
_PRESETS: List[Tuple[str, str, Optional[str]]] = [
    ("candles — 최신",
     "SELECT * FROM candles ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("staging_candles — 최신",
     "SELECT * FROM staging_candles ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("candles_1m — 최신",
     "SELECT * FROM candles WHERE timeframe = '1m' ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("cagg_candles_5m — 최신",
     "SELECT * FROM cagg_candles_5m ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("cagg_candles_1h — 최신",
     "SELECT * FROM cagg_candles_1h ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("market_ticks — 최신",
     "SELECT * FROM market_ticks ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("orderbook_snapshots — 최신",
     "SELECT * FROM orderbook_snapshots ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("gap_fill_queue — 최신",
     "SELECT * FROM gap_fill_queue ORDER BY created_at DESC LIMIT {limit}",
     "created_at"),
    ("technical_indicators — 최신",
     "SELECT * FROM technical_indicators ORDER BY time DESC LIMIT {limit}",
     "time"),
    ("하이퍼테이블 목록",
     "SELECT hypertable_name, "
     "approximate_row_count(format('%I', hypertable_name)::regclass) AS rows, "
     "pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass)) AS size "
     "FROM timescaledb_information.hypertables ORDER BY hypertable_name",
     "none"),
    ("연속 집계(CAGG) 목록",
     "SELECT view_name, view_schema, materialization_hypertable_name "
     "FROM timescaledb_information.continuous_aggregates ORDER BY view_name",
     "none"),
    ("청크 목록 (전체)",
     "SELECT hypertable_name, chunk_name, range_start, range_end, "
     "is_compressed FROM timescaledb_information.chunks ORDER BY range_start DESC LIMIT {limit}",
     "none"),
    ("압축 현황",
     "SELECT h.hypertable_name, "
     "COUNT(c.chunk_name) FILTER(WHERE c.is_compressed) AS compressed_chunks, "
     "COUNT(c.chunk_name) FILTER(WHERE NOT c.is_compressed) AS uncompressed_chunks "
     "FROM timescaledb_information.hypertables h "
     "LEFT JOIN timescaledb_information.chunks c ON c.hypertable_name = h.hypertable_name "
     "GROUP BY h.hypertable_name ORDER BY h.hypertable_name",
     "none"),
    ("보존 정책",
     "SELECT hypertable_name, config->>'drop_after' AS drop_after, schedule_interval "
     "FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'",
     "none"),
]

if _HAS_QT:
    class _QueryWorker(QThread):
        finished = pyqtSignal(list, list)  # headers, rows
        error = pyqtSignal(str)
        warning = pyqtSignal(str)  # 비치명 경고 (시간 컬럼 자동탐지 등)

        def __init__(self, conn_params: dict, sql: str, time_hint: Optional[str] = None):
            super().__init__()
            self._conn_params = conn_params
            self._sql = sql
            self._time_hint = time_hint  # "none" | column_name | None(=auto-detect)
            self._params: tuple = ()   # parameterized query 파라미터 (SQL 인젝션 방지)

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
            """information_schema 로 time 컬럼 후보를 탐지."""
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
            """SQL 에서 FROM 다음 테이블명(스키마 한정자 제거)을 추출."""
            import re
            # public.candles → candles, candles → candles
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

                    # hint="none" → ORDER BY 조작 없이 그대로 실행
                    if hint != "none":
                        table_name = self._extract_table_name(sql)
                        if table_name and hint is None:
                            detected = self._detect_time_col(conn, table_name)
                            if detected is None:
                                # time 컬럼 없음 → ORDER BY 절 제거 (방향 키워드 있거나 없어도)
                                sql = re.sub(
                                    r"\s*ORDER BY\s+\w+(?:\s+(?:DESC|ASC))?",
                                    "", sql, flags=re.IGNORECASE,
                                )
                                self.warning.emit(
                                    f"⚠️ '{table_name}' 테이블에서 time 컬럼을 찾지 못해 ORDER BY를 제거했습니다."
                                )
                            elif detected != "time":
                                # detected 는 _TIME_CANDIDATES 에서 온 안전한 식별자
                                safe_col = detected if detected in _TIME_CANDIDATES else "time"
                                sql = re.sub(
                                    r"\bORDER BY\s+time\b",
                                    f"ORDER BY {safe_col}",
                                    sql, flags=re.IGNORECASE,
                                )
                                self.warning.emit(
                                    f"ℹ️ time → '{safe_col}' 컬럼으로 ORDER BY를 자동 교정했습니다."
                                )

                    with conn.cursor() as cur:
                        # self._params 가 있으면 파라미터 바인딩으로 실행 (SQL 인젝션 방지)
                        cur.execute(sql, self._params or None)
                        headers = [d[0] for d in (cur.description or [])]
                        rows = cur.fetchall()
                    self.finished.emit(headers, [list(r) for r in rows])
                finally:
                    conn.close()
            except Exception as exc:
                self.error.emit(str(exc)[:300])


    class DataViewTab(QWidget):
        """TimescaleDB 저장 데이터 상세 조회 탭.

        기준 UI(db_data_viewer.ui)와 동일 UX:
        - 상단 필터 바: 자산군 / 거래소 / 심볼 콤보 + 한글·영문·초성 검색
        - 프리셋 쿼리 선택 + 행 수 + 조회 버튼
        - 심볼 필터 텍스트 + 날짜 범위
        - DataBrowserWidget (정렬/필터/페이지네이션/드릴다운)
        - 상태 배너 (연결 정보, 마지막 조회 시각, 행 수)
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._worker: Optional[_QueryWorker] = None
            # 필터 Mixin 상태 초기화
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

            # 배너
            banner = QLabel("🗄️ TimescaleDB — 저장 데이터 상세 조회")
            banner.setStyleSheet(
                "background:#1D4ED8;color:white;padding:10px 14px;"
                "font-weight:bold;font-size:11pt;border-radius:4px;"
            )
            layout.addWidget(banner)

            # 연결 정보 행
            info_frame = QFrame()
            info_frame.setStyleSheet(
                "QFrame { background:#EFF6FF; border-left:4px solid #3B82F6;"
                " border-radius:3px; }"
            )
            info_layout = QHBoxLayout(info_frame)
            info_layout.setContentsMargins(10, 6, 10, 6)
            db_name = self._conn_params.get("database") or self._conn_params.get("db") or "upbit_trader"
            port    = self._conn_params.get("port", 58529)
            self._lbl_conn = QLabel(f"🔌 DB: {db_name}  |  포트: {port}")
            self._lbl_conn.setStyleSheet("color:#1D4ED8;font-size:8pt;")
            info_layout.addWidget(self._lbl_conn)
            info_layout.addStretch()
            self._lbl_updated = QLabel("")
            self._lbl_updated.setStyleSheet("color:#6B7280;font-size:8pt;")
            info_layout.addWidget(self._lbl_updated)
            layout.addWidget(info_frame)

            # ── 상단 필터 바 (기준 UI: db_data_viewer.ui 와 동일 구성) ──────────
            filter_bar = QHBoxLayout()
            filter_bar.setSpacing(4)

            filter_bar.addWidget(QLabel("자산군:"))
            self._combo_asset = QComboBox()
            self._combo_asset.setMinimumWidth(105)
            filter_bar.addWidget(self._combo_asset)

            filter_bar.addWidget(QLabel("거래소:"))
            self._combo_exch = QComboBox()
            self._combo_exch.setMinimumWidth(95)
            filter_bar.addWidget(self._combo_exch)

            filter_bar.addWidget(QLabel("심볼:"))
            self._combo_sym = QComboBox()
            self._combo_sym.setMinimumWidth(130)
            self._combo_sym.setEditable(True)
            self._combo_sym.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            filter_bar.addWidget(self._combo_sym)

            filter_bar.addWidget(QLabel("검색:"))
            self._edit_search_filter = QLineEdit()
            self._edit_search_filter.setMinimumWidth(175)
            self._edit_search_filter.setPlaceholderText(
                "심볼·한글·영문·초성 검색 (예: shib, 시바, ㅅㅂ)"
            )
            filter_bar.addWidget(self._edit_search_filter)

            self._lbl_search_result = QLabel("")
            self._lbl_search_result.setMinimumWidth(65)
            self._lbl_search_result.setStyleSheet("color:#2980b9;font-size:8pt;")
            filter_bar.addWidget(self._lbl_search_result)

            filter_bar.addStretch()
            layout.addLayout(filter_bar)

            # 필터 콤보 초기값 설정 (DataViewFilterMixin 로직 직접 호출)
            self._populate_asset_exchange_combos()

            # 조회 조건 행 1: 프리셋 + 행 수
            ctrl_row = QHBoxLayout()
            ctrl_row.addWidget(QLabel("테이블/프리셋:"))
            self._combo = QComboBox()
            self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for label, _, _ in _PRESETS:
                self._combo.addItem(label)
            ctrl_row.addWidget(self._combo)
            ctrl_row.addWidget(QLabel("행 수:"))
            self._limit_combo = QComboBox()
            for label, _ in _LIMIT_OPTIONS:
                self._limit_combo.addItem(label)
            self._limit_combo.setCurrentIndex(2)  # 기본: 500행
            self._limit_combo.setFixedWidth(70)
            ctrl_row.addWidget(self._limit_combo)
            self._btn_load = QPushButton("🔄 조회")
            self._btn_load.setFixedWidth(80)
            self._btn_load.setStyleSheet(
                "QPushButton { background:#1D4ED8; color:white; border-radius:4px;"
                " padding:4px 10px; font-weight:bold; }"
                "QPushButton:hover { background:#1E40AF; }"
                "QPushButton:disabled { background:#9CA3AF; }"
            )
            ctrl_row.addWidget(self._btn_load)
            layout.addLayout(ctrl_row)

            # 조회 조건 행 2: 심볼 필터 + 날짜 범위 (시계열 테이블에만 활성화)
            try:
                from PyQt5.QtWidgets import QDateEdit, QCheckBox
                from PyQt5.QtCore import QDate
                _HAS_DATE = True
            except ImportError:
                _HAS_DATE = False
                QDateEdit = QCheckBox = QDate = None  # type: ignore[misc,assignment]

            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("심볼 필터:"))
            self._edit_symbol = QLineEdit()
            self._edit_symbol.setPlaceholderText("예: KRW-BTC  (비워두면 전체)")
            self._edit_symbol.setFixedWidth(160)
            filter_row.addWidget(self._edit_symbol)

            filter_row.addWidget(QLabel("날짜범위:"))
            self._chk_date = None
            if _HAS_DATE:
                # QDateEdit/QCheckBox/QDate 이미 import됨 (중복 import 제거)
                self._chk_date = QCheckBox("사용")
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

            # 경고 레이블 (time 컬럼 자동탐지 시 표시)
            self._lbl_warn = QLabel("")
            self._lbl_warn.setStyleSheet(
                "background:#FEF9C3;color:#92400E;padding:4px 8px;"
                "border-radius:3px;font-size:8pt;"
            )
            self._lbl_warn.setVisible(False)
            layout.addWidget(self._lbl_warn)

            # 브라우저 위젯 (DataBrowserWidget 우선, 폴백 QTableWidget)
            if _DATA_BROWSER is not None:
                self._browser = _DATA_BROWSER()
                self._has_browser = True
            else:
                from PyQt5.QtWidgets import QTableWidget
                self._browser = QTableWidget()
                self._has_browser = False
            layout.addWidget(self._browser)

            # 상태 레이블
            self._status = QLabel("⬜ 테이블/프리셋을 선택하고 [조회] 버튼을 누르세요.")
            self._status.setStyleSheet("color:#6B7280;font-size:8pt;")
            layout.addWidget(self._status)

        def _bind_signals(self) -> None:
            self._btn_load.clicked.connect(self._load_data)
            # ── 상단 필터 시그널 연결 ──────────────────────────────────────
            self._combo_asset.currentIndexChanged.connect(self._on_asset_filter_changed)
            self._combo_exch.currentIndexChanged.connect(self._on_exchange_filter_changed)
            self._combo_sym.currentTextChanged.connect(self._on_sym_combo_changed)
            self._edit_search_filter.textChanged.connect(self._on_search_filter)

        # ------------------------------------------------------------------
        # 상단 필터 바 메서드 (DataViewFilterMixin 로직 인라인)
        # ------------------------------------------------------------------

        def _populate_asset_exchange_combos(self) -> None:
            """자산군/거래소 콤보 초기값 설정 (DataViewFilterMixin._populate_filter_combos 로직)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._populate_filter_combos(self)

        def _on_asset_filter_changed(self, _index: int = 0) -> None:
            """자산군 변경 → 거래소 콤보 동기화."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_asset_filter_changed(self, _index)

        def _on_exchange_filter_changed(self, _index: int = 0) -> None:
            """거래소 변경 → 심볼 콤보 필터링."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_exchange_filter_changed(self, _index)

        def _on_search_filter(self, text: str) -> None:
            """검색어 입력 → 심볼 콤보 필터링 (한글/초성/영문)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._on_search_filter(self, text)

        def _filter_symbols_by_asset_exchange(self) -> None:
            """자산군·거래소 기준으로 심볼 콤보를 필터링합니다 (DataViewFilterMixin 위임)."""
            try:
                from data_view_filter_mixin import DataViewFilterMixin as _FM
            except ImportError:
                try:
                    from .data_view_filter_mixin import DataViewFilterMixin as _FM  # type: ignore[no-redef]
                except ImportError:
                    return
            _FM._filter_symbols_by_asset_exchange(self)

        def _update_filter_result_label(self, count: int, show: bool) -> None:
            """검색 결과 수 레이블을 갱신합니다."""
            lbl = getattr(self, "_lbl_search_result", None)
            if lbl is None:
                return
            lbl.setText(f"{count}개 매칭" if show else "")

        def _on_sym_combo_changed(self, text: str) -> None:
            """심볼 콤보 변경 시 _edit_symbol(SQL 쿼리용) 에도 반영합니다."""
            edit = getattr(self, "_edit_symbol", None)
            if edit is not None:
                edit.blockSignals(True)
                edit.setText(text)
                edit.blockSignals(False)

        def _on_symbols_loaded(self, symbols: list) -> None:
            """심볼 로드 완료 시 콤보 갱신."""
            self._all_symbols = symbols or []
            self._refresh_symbol_combo(self._all_symbols)

        def _on_symbols_error(self, _msg: str) -> None:
            """심볼 로드 실패 시 기본 심볼 유지."""
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
            """심볼 콤보 내용을 교체합니다."""
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
            """candles 테이블에서 심볼 목록을 비동기 로드합니다."""
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
            """현재 조건에 맞는 SQL 쿼리·time_hint·파라미터를 생성합니다.

            Returns:
                (sql, time_hint, params) — params은 parameterized query용 튜플.
                symbol 및 날짜 필터는 SQL 인젝션 방지를 위해 %s 바인딩을 사용합니다.
            """
            import re as _re
            idx = self._combo.currentIndex()
            if idx < 0 or idx >= len(_PRESETS):
                return "", None, ()
            _, sql_tmpl, time_hint = _PRESETS[idx]

            # {limit} 치환 (하드코딩된 _LIMIT_OPTIONS에서 가져오므로 인젝션 위험 없음)
            limit_idx = self._limit_combo.currentIndex() if hasattr(self, "_limit_combo") else 2
            _, limit_val = _LIMIT_OPTIONS[limit_idx] if 0 <= limit_idx < len(_LIMIT_OPTIONS) else ("500행", 500)
            sql = sql_tmpl.replace("{limit}", str(limit_val))

            params: tuple = ()

            # 심볼 결정: 상단 필터 콤보(_combo_sym) 우선, 없으면 텍스트 입력(_edit_symbol)
            sym_combo = getattr(self, "_combo_sym", None)
            sym_text_edit = getattr(self, "_edit_symbol", None)
            symbol = (
                sym_combo.currentText().strip() if sym_combo else ""
            ) or (
                sym_text_edit.text().strip() if sym_text_edit else ""
            )

            # 심볼 필터 — %s 파라미터 바인딩으로 SQL 인젝션 방지
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

            # 날짜 범위 필터 — %s 파라미터 바인딩으로 SQL 인젝션 방지
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
                # time_hint는 _PRESETS 하드코딩 상수 → 인젝션 위험 없음
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
            self._status.setText("⏳ 조회 중...")
            self._btn_load.setEnabled(False)
            self._worker = _QueryWorker(self._conn_params, sql, time_hint)
            # params를 Worker에 전달 (SQL 인젝션 방지를 위해 parameterized query 사용)
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
            self._lbl_updated.setText(f"마지막 조회: {now}  |  {len(rows):,}행")
            if self._has_browser and hasattr(self._browser, "set_data"):
                self._browser.set_data(headers, rows)
                self._status.setStyleSheet("color:#16A34A;font-size:8pt;")
                self._status.setText(
                    f"✅ {len(rows):,}행 조회 완료"
                    f" ({len(headers)}컬럼) — 더블클릭: 행 상세 보기 | 헤더 클릭: 정렬"
                )
            else:
                # 폴백: 단순 QTableWidget
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
                    f"✅ {len(rows):,}행 조회 완료 ({len(headers)}컬럼)"
                    " — DataBrowserWidget 미로드: 필터/정렬/페이지네이션 비활성"
                )

        @pyqtSlot(str)
        def _on_warning(self, msg: str) -> None:
            self._lbl_warn.setText(msg)
            self._lbl_warn.setVisible(True)

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._btn_load.setEnabled(True)
            self._status.setStyleSheet("color:#DC2626;font-size:8pt;")
            # 사용자 친화적 오류 힌트 제공
            hint = ""
            if "does not exist" in msg.lower() or "relation" in msg.lower():
                hint = " → 테이블이 아직 생성되지 않았습니다. 다른 프리셋을 선택하세요."
            elif "connection" in msg.lower() or "connect" in msg.lower():
                hint = " → DB 연결 실패. Docker 컨테이너 실행 여부 확인: docker ps | grep timescale"
            elif "permission" in msg.lower():
                hint = " → 조회 권한이 없습니다. DB 사용자 권한을 확인하세요."
            self._status.setText(f"🔴 오류: {msg[:200]}{hint}")
            self._lbl_warn.setText(f"⚠️ 조회 실패: {msg[:120]}{hint}")
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
