# -*- coding: utf-8 -*-
"""
DB 데이터 뷰어 탭 — TimescaleDB 캔들 데이터 직접 조회 UI (v2.0)

기능:
  - 자산군 × 거래소 2-depth 필터
  - 심볼 검색 (영문/한글/초성)
  - 타임프레임 / 기간 선택 후 조회
  - 실시간 저장 상태 배너
  - CSV 내보내기
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QComboBox, QPushButton, QTableWidget, QHeaderView,
        QLineEdit, QSizePolicy,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_COL_HEADERS = ["시각", "시가", "고가", "저가", "종가", "거래량", "거래대금", "체결수", "완성"]

if _HAS_QT:
    from .db_viewer_logic import DBViewerLogicMixin
    from .db_viewer_ui_updaters import DBViewerUIUpdatersMixin
    from .db_viewer_auto_period import DBViewerAutoPeriodMixin

    class DBDataViewerTab(
        DBViewerAutoPeriodMixin,
        DBViewerLogicMixin,
        DBViewerUIUpdatersMixin,
        QWidget,
    ):
        """Tab: 🗄️ DB 데이터 — TimescaleDB 캔들 조회 뷰어 (v2.0)"""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._rows: List[Tuple] = []
            self._all_symbols: List[str] = []
            self._all_symbol_stats: List[Any] = []
            self._name_map: Optional[Any] = None
            self._name_en_map: Optional[Any] = None

            # UI 로드
            ui_path = Path(__file__).parent / "db_data_viewer.ui"
            try:
                uic.loadUi(str(ui_path), self)
                logger.info("[DBDataViewerTab] ✅ UI 파일 로드 성공: %s", ui_path)
            except Exception as exc:
                logger.warning("[DBDataViewerTab] UI 파일 로드 실패: %s — 폴백 UI 구성", exc)
                self._build_ui_fallback()

            # 테이블 헤더 설정
            self._setup_table()

            # 콤보 초기화
            self._populate_combos()

            # 시그널 연결
            self._connect_signals()

            # 백필 검증 시그널 연결
            self._connect_verify_signals()

            # StorageStatusBar 삽입
            self._insert_status_bar()

            # 심볼 로드
            self._load_symbols_for_combo()

            # 자동완성 설정 (심볼 로드 후)
            self._setup_autocomplete()

            # 자동 갱신 타이머 (저장 상태 배너)
            self._banner_timer = QTimer(self)
            self._banner_timer.setInterval(5000)
            self._banner_timer.timeout.connect(self._refresh_banner)

        # ------------------------------------------------------------------
        # 자동 갱신 제어
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 5000) -> None:
            """저장 상태 배너 자동 갱신을 시작합니다."""
            self._banner_timer.setInterval(max(3000, int(interval_ms)))
            if not self._banner_timer.isActive():
                self._banner_timer.start()
            # StorageStatusBar 갱신 시작
            status_bar = getattr(self, "_storage_status_bar", None)
            if status_bar is not None and hasattr(status_bar, "start_updates"):
                status_bar.start_updates(interval_ms)

        def stop_updates(self) -> None:
            """자동 갱신을 중지합니다."""
            if self._banner_timer.isActive():
                self._banner_timer.stop()
            status_bar = getattr(self, "_storage_status_bar", None)
            if status_bar is not None and hasattr(status_bar, "stop_updates"):
                status_bar.stop_updates()

        def closeEvent(self, event: Any) -> None:
            """위젯 닫힐 때 타이머 및 자동완성 정리."""
            self.stop_updates()
            # 자동완성 completer 정리 (메모리 누수 방지)
            edit = getattr(self, "edit_search", None)
            if edit is not None:
                edit.setCompleter(None)
            self._completer = None  # type: ignore[assignment]
            super().closeEvent(event)

        # ------------------------------------------------------------------
        # 내부 초기화
        # ------------------------------------------------------------------

        def _setup_table(self) -> None:
            """테이블 헤더 및 속성 설정."""
            table = getattr(self, "table_candles", None)
            if table is None:
                return
            table.setColumnCount(len(_COL_HEADERS))
            table.setHorizontalHeaderLabels(_COL_HEADERS)
            hh = table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 시각
            for i in range(1, len(_COL_HEADERS) - 1):
                hh.setSectionResizeMode(i, QHeaderView.Stretch)
            hh.setSectionResizeMode(len(_COL_HEADERS) - 1, QHeaderView.ResizeToContents)  # 완성
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def _connect_signals(self) -> None:
            """위젯 시그널을 슬롯에 연결합니다."""
            btn_query = getattr(self, "btn_query", None)
            if btn_query is not None:
                btn_query.clicked.connect(self._on_query)

            btn_export = getattr(self, "btn_export", None)
            if btn_export is not None:
                btn_export.clicked.connect(self._on_export)

            edit_search = getattr(self, "edit_search", None)
            if edit_search is not None:
                edit_search.textChanged.connect(self._on_search)

            combo_ac = getattr(self, "combo_asset_class", None)
            if combo_ac is not None:
                combo_ac.currentIndexChanged.connect(self._on_asset_changed)

            combo_ex = getattr(self, "combo_exchange", None)
            if combo_ex is not None:
                combo_ex.currentIndexChanged.connect(self._on_exchange_changed)

        def _insert_status_bar(self) -> None:
            """StorageStatusBar 위젯을 statusBannerLayout에 삽입합니다."""
            try:
                from ..widgets.storage_status_bar import StorageStatusBar
                self._storage_status_bar = StorageStatusBar(self)
                # statusBannerLayout이 없을 경우 상단에 직접 삽입
                layout = self.layout()
                if layout is not None:
                    layout.insertWidget(1, self._storage_status_bar)
            except Exception as exc:
                logger.debug("[DBDataViewerTab] StorageStatusBar 삽입 실패: %s", exc)
                self._storage_status_bar = None

        def _refresh_banner(self) -> None:
            """저장 상태 배너를 주기적으로 갱신합니다."""
            try:
                from ..utils.candle_queries import query_table_counts, get_save_rate_per_sec
                counts = query_table_counts()
                rate = get_save_rate_per_sec()
                self.update_status_banner(
                    counts.get("candles", 0),
                    counts.get("staging", 0),
                    counts.get("isolated", 0),
                    rate,
                    counts.get("last_save_time"),
                )
            except Exception as exc:
                logger.debug("[DBDataViewerTab] 배너 갱신 실패: %s", exc)

        def _setup_autocomplete(self) -> None:
            """edit_search에 QCompleter 자동완성을 연결합니다.

            심볼 로드 완료 후 호출해야 합니다.
            자동완성 항목 형태: "KRW-BTC — 비트코인 — Bitcoin"
            """
            from PyQt5.QtWidgets import QCompleter
            from PyQt5.QtCore import Qt

            all_symbols = getattr(self, "_all_symbols", [])

            # name_map / name_en_map 미리 빌드 (캐시)
            try:
                from ..utils.symbol_search import build_name_map, build_name_en_map
                if self._name_map is None:
                    self._name_map = build_name_map()
                if self._name_en_map is None:
                    self._name_en_map = build_name_en_map()
            except Exception as exc:
                logger.debug("[DBDataViewerTab] name_map 빌드 실패: %s", exc)
                self._name_map = self._name_map or {}
                self._name_en_map = self._name_en_map or {}

            name_map = self._name_map or {}
            name_en_map = self._name_en_map or {}

            # 자동완성 항목 목록 생성
            items: List[str] = []
            for sym in all_symbols:
                ko = name_map.get(sym, "")
                en = name_en_map.get(sym, "")
                if ko and en:
                    items.append(f"{sym} — {ko} — {en}")
                elif ko:
                    items.append(f"{sym} — {ko}")
                else:
                    items.append(sym)

            completer = QCompleter(items, self)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setMaxVisibleItems(12)
            self._completer = completer

            edit = getattr(self, "edit_search", None)
            if edit is not None:
                edit.setCompleter(completer)
                completer.activated.connect(self._on_autocomplete_selected)

        def _on_autocomplete_selected(self, text: str) -> None:
            """자동완성 항목 선택 시 해당 심볼로 combo_symbol을 맞추고 조회합니다.

            Args:
                text: 선택된 자동완성 텍스트 (예: "KRW-SHIB — 시바이누 — Shiba Inu")
            """
            # "KRW-SHIB — 시바이누 — Shiba Inu" 형태에서 심볼 추출
            sym = text.split(" — ")[0].strip() if " — " in text else text.strip()
            combo = getattr(self, "combo_symbol", None)
            if combo is None:
                return
            idx = combo.findText(sym)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            # edit_search 텍스트를 심볼로 교체하여 콤보 필터도 갱신
            edit = getattr(self, "edit_search", None)
            if edit is not None:
                edit.blockSignals(True)
                edit.setText(sym)
                edit.blockSignals(False)
            self._on_query()

        # ------------------------------------------------------------------
        # 폴백 UI (uic.loadUi 실패 시)
        # ------------------------------------------------------------------

        def _build_ui_fallback(self) -> None:
            """코드 기반 폴백 UI를 구성합니다."""
            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(4)

            # 상단 컨트롤 행 1
            top = QHBoxLayout()
            for attr, label, width in [
                ("combo_asset_class", "자산군:", 110),
                ("combo_exchange",    "거래소:", 100),
                ("combo_symbol",      "심볼:",   140),
            ]:
                top.addWidget(QLabel(label))
                cb = QComboBox()
                cb.setMinimumWidth(width)
                setattr(self, attr, cb)
                top.addWidget(cb)

            top.addWidget(QLabel("검색:"))
            self.edit_search = QLineEdit()
            self.edit_search.setPlaceholderText("심볼·한글·초성 검색")
            self.edit_search.setMinimumWidth(140)
            top.addWidget(self.edit_search)
            top.addStretch()
            root.addLayout(top)

            # 상단 컨트롤 행 2
            top2 = QHBoxLayout()
            for attr, label, width in [
                ("combo_data_source", "데이터소스:", 120),
                ("combo_timeframe",   "타임프레임:", 70),
                ("combo_period",      "기간:",       110),
            ]:
                top2.addWidget(QLabel(label))
                cb = QComboBox()
                cb.setMinimumWidth(width)
                setattr(self, attr, cb)
                top2.addWidget(cb)

            self.btn_query = QPushButton("조회")
            self.btn_query.setMinimumWidth(60)
            top2.addWidget(self.btn_query)

            self.btn_export = QPushButton("내보내기")
            self.btn_export.setMinimumWidth(70)
            top2.addWidget(self.btn_export)
            top2.addStretch()
            root.addLayout(top2)

            # 테이블
            self.table_candles = QTableWidget(0, len(_COL_HEADERS))
            self.table_candles.setHorizontalHeaderLabels(_COL_HEADERS)
            root.addWidget(self.table_candles)

            # 하단 요약
            bot = QHBoxLayout()
            self.label_summary = QLabel("총 조회: 0건")
            bot.addWidget(self.label_summary)
            bot.addStretch()
            self.label_query_time = QLabel("조회 시간: -")
            bot.addWidget(self.label_query_time)
            root.addLayout(bot)

else:
    class DBDataViewerTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 클래스."""

        def __init__(self, parent: Optional[object] = None) -> None:
            pass

        def start_updates(self, interval_ms: int = 5000) -> None:
            pass

        def stop_updates(self) -> None:
            pass
