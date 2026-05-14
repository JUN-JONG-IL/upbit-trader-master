#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 코인 종목 목록 테이블 위젯
- 실시간 가격, 등락률, 거래량, 관심종목 관리

[Responsibilities]
- Debounce 100ms (검색 입력)
- 가상 스크롤링 (대량 코인 목록)
- UIStateManager 연동 (심볼 변경 동기화)
- 관심종목 관리
- 정렬/필터 기능

[Main Flow]
1. CoinListWorker에서 5초마다 코인 데이터 수신
2. updateData()로 테이블 업데이트
3. chkItemClicked()에서 종목 클릭 시 UIStateManager.set_symbol() 호출
4. 다른 위젯들이 symbol_changed Signal 수신하여 동기화

[Author] Copilot + Phase 2 Integration
[Created] 2026-01-23
[Modified] 2026-01-24
"""
from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Iterable, List, Any

from PyQt5 import QtGui, uic
from PyQt5.QtCore import QEvent, QSettings, Qt, QTimer, QStringListModel
from PyQt5.QtGui import QColor, QFont, QPen, QBrush, QPixmap, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QSpinBox,
    QStyle,
    QStyleFactory,
    QStyledItemDelegate,
    QTableWidgetItem,
    QWidget,
)

import logging as _logging
try:
    import static  # type: ignore[import]
    log = getattr(static, 'log', _logging.getLogger(__name__))
except ImportError:
    try:
        from app import static  # type: ignore[import]
        log = getattr(static, 'log', _logging.getLogger(__name__))
    except ImportError:
        static = None  # type: ignore[assignment]
        log = _logging.getLogger(__name__)

# Safely extract config from static, with a robust fallback chain
config = getattr(static, 'config', None) if static is not None else None
if config is None:
    try:
        from server.static import config  # type: ignore[import,no-redef]
    except ImportError:
        try:
            from src.server.static import config  # type: ignore[import,no-redef]
        except ImportError:
            try:
                from config import Config  # type: ignore[import]
                config = Config()
                config.load()
            except Exception:
                class _StubConfig:
                    """Fallback config stub — returns None for any attribute when no config source is available."""
                    def __getattr__(self, name: str):
                        return None
                config = _StubConfig()

try:
    from utils import debounce  # type: ignore[import]
except ImportError:
    def debounce(ms: int):  # type: ignore[misc]
        """Fallback no-op debounce decorator when utils is unavailable."""
        def decorator(fn):
            return fn
        return decorator

from ..logic.coinlist_logic import CoinListLogic
from ..workers.coinlist_progress import ProgressController
from ..logic.search.coinlist_search import CoinListSearchController
from ..workers.coinlist_workers import CoinListWorker, TradeWorker
from .widget_favorite import FavoriteWidget


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


def _safe_chart_coins() -> List[Any]:
    """
    안전하게 static.chart.coins의 값을 반환.
    - static.chart 또는 static.chart.coins가 없으면 빈 리스트 반환.
    - 반환형은 list(coin_objects)
    """
    try:
        chart = getattr(static, "chart", None)
        if chart is None:
            return []
        coins = getattr(chart, "coins", None)
        if coins is None:
            return []
        # coins might be a dict mapping code->coin, or already an iterable of coin objects
        if isinstance(coins, dict):
            return list(coins.values())
        if isinstance(coins, Iterable):
            return list(coins)
        return []
    except Exception:
        log.exception("[CoinlistWidget] _safe_chart_coins failed")
        return []


class CustomDelegate(QStyledItemDelegate):
    """
    [Purpose]
    커스텀 테이블 셀 렌더링 (색상, 폰트, 정렬)
    """
    def paint(self, painter, option, index):
        painter.save()

        bg_brush = index.data(Qt.BackgroundRole)
        if bg_brush:
            painter.fillRect(option.rect, bg_brush)
        else:
            painter.fillRect(option.rect, QColor(0, 0, 0, 0))

        text = index.data(Qt.DisplayRole) or ""
        color = index.data(Qt.ForegroundRole)
        painter.setPen(color.color() if color else QColor(0, 0, 0))

        font = index.data(Qt.FontRole)
        painter.setFont(font if font else QFont("Segoe UI", 7))

        align = Qt.AlignRight | Qt.AlignVCenter
        if index.column() in (0, 1):
            align = Qt.AlignCenter | Qt.AlignVCenter
        if index.column() == 2:
            align = Qt.AlignLeft | Qt.AlignVCenter

        painter.drawText(option.rect, align, text)

        if option.state & QStyle.State_Selected:
            pen = QPen(QColor(0, 0, 0), 3)
            painter.setPen(pen)
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        painter.restore()


class _ClickableLabel(QLabel):
    """
    [Purpose]
    클릭 가능한 QLabel (아이콘 클릭 시 콜백 실행)
    """
    def __init__(self, *args, on_click=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, ev):
        if callable(self._on_click):
            self._on_click()
        return super().mousePressEvent(ev)


class CoinlistWidget(QWidget):
    """
    [Purpose]
    코인 종목 목록 메인 위젯
    
    [Responsibilities]
    - 실시간 코인 데이터 표시 (debounce 100ms)
    - UIStateManager 연동 (심볼 변경 동기화)
    - 관심종목 관리
    - 정렬/필터 기능
    - 검색 autocomplete
    
    [Main Flow]
    1. CoinListWorker에서 5초마다 데이터 수신
    2. updateData()로 테이블 업데이트
    3. chkItemClicked()에서 종목 클릭 → UIStateManager.set_symbol()
    4. 다른 위젯들이 symbol_changed Signal 수신
    """
    
    def __init__(self, parent=None, ui_state_manager=None):
        super().__init__(parent)
        uic.loadUi(_ui_file_path("coin_list.ui"), self)

        # App style (ensure consistent look)
        app = QApplication.instance()
        if app:
            app.setStyle(QStyleFactory.create("Fusion"))

        self.settings = QSettings("MyCompany", "CoinTradeApp")

        # UIStateManager 연동
        self.ui_state_manager = ui_state_manager

        # 외부 연동 (���거시 호환성)
        self.order = None
        self.chart = None
        self.trade = None
        self.orderbook = None
        self.dw = None

        # favorites
        self.favorites = set()
        self.favorite_mode = False

        # name toggle
        self.name_toggle_korean = getattr(config, "name_toggle_korean", True)
        try:
            self.btn_toggle_name.setText("영문" if not self.name_toggle_korean else "한글")
        except Exception:
            # If UI element missing, ignore
            pass

        # colors
        self.color_red = QColor(255, 0, 0)
        self.color_blue = QColor(0, 0, 255)
        self.color_white = QColor(255, 255, 255, 0)
        self.color_black = QBrush(QColor(0, 0, 0))
        self.color_light_red = QColor(255, 200, 200, 128)
        self.color_light_blue = QColor(173, 216, 230, 128)
        self.color_gray = QColor(128, 128, 128)
        self.color_gold = QColor(255, 215, 0)

        # sort
        self.sort_states = [0] * 15
        self.current_sort_col = 5
        self.sort_states[5] = -1

        # accum
        self.trade_buy_accum: dict[str, Decimal] = {}
        self.trade_sell_accum: dict[str, Decimal] = {}
        self.prev_dominance = {}
        self.ignore_accum_update = False

        # intervals/thresholds
        self.rate_calc_interval = 0
        self.trade_reset_interval = 0
        self.trade_calc_interval = 0
        self.rate_rise_threshold = 5.0
        self.rate_fall_threshold = -5.0
        self.trade_rise_threshold = 10.0
        self.trade_fall_threshold = -10.0

        # time tracking
        self.last_rate_save_time = time.time()
        self.last_trade_save_time = time.time()
        self.last_clear_time = time.time()

        # table state
        self.displayed_coins = []
        self.items: list[list[QTableWidgetItem]] = []

        # column width load should happen once per widget lifetime
        self._column_widths_loaded = False

        # controllers
        self.progress = ProgressController(self)
        self.search = CoinListSearchController(self)
        self.logic = CoinListLogic(self)

        # timers
        self.clear_timer = QTimer(self)
        self.clear_timer.timeout.connect(self.logic.auto_clear_accum)

        self.remaining_timer = QTimer(self)
        self.remaining_timer.timeout.connect(self.logic.update_remaining_time)

        self.price_timer = QTimer(self)
        self.price_timer.timeout.connect(self.logic.update_price_changes)

        self.trade_change_timer = QTimer(self)
        self.trade_change_timer.timeout.connect(self.logic.update_trade_changes)

        self.update_debounce_timer = QTimer(self)
        self.update_debounce_timer.setSingleShot(True)
        self.update_debounce_timer.timeout.connect(self.logic.partial_update_accum)

        # init ui
        self._init_table()
        self._init_search()
        self._init_progress_controls()

        # settings + signals
        self.load_settings()
        self._bind_signals()

        # status label: 잘림/깨짐 방지
        self._init_status_label_elide()

        # init data
        self.logic.init_accumulators()
        self.logic.init_baselines()

        # initial rows (safe: may be empty if chart not ready)
        self._ensure_initial_items()

        # column widths: startup once (after header exists)
        self._load_column_widths_once()

        # first render (safe use of chart coins)
        QTimer.singleShot(100, lambda: self.updateData(_safe_chart_coins(), force_sort=True))
        QTimer.singleShot(0, self.select_first_row_and_sync)

        # workers
        try:
            self.cw = CoinListWorker(interval_sec=5)
            self.cw.dataSent.connect(lambda data: self.updateData(data, force_sort=False))
            self.cw.start()
        except Exception:
            log.exception("[CoinlistWidget] CoinListWorker start failed")
            self.cw = None

        try:
            self.tw = TradeWorker()
            self.tw.tradeAccum.connect(self._on_trade_accum)
            self.tw.status.connect(self._on_trade_status)
            self.tw.start()
        except Exception:
            log.exception("[CoinlistWidget] TradeWorker start failed")
            self.tw = None

        # timers start
        try:
            self.remaining_timer.start(1000)
        except Exception:
            pass
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.progress.set_idle_status)
        self.idle_timer.start(10000)

        # apply auto toggles (protect against missing controls)
        try:
            self.logic.toggle_price_auto(self.check_price_auto.checkState())
        except Exception:
            pass
        try:
            self.logic.toggle_trade_change_auto(self.check_trade_change_auto.checkState())
        except Exception:
            pass
        try:
            self.logic.toggle_auto_clear(self.check_trade_auto.checkState())
        except Exception:
            pass

    # ---- status label elide (text 깨짐 방지) ----
    def _init_status_label_elide(self):
        self._status_full_text = ""
        try:
            self.status_label.installEventFilter(self)
        except Exception:
            pass

    def _set_status_text(self, full_text: str):
        """status_label에 공간에 맞게 ... 처리해서 표시(글자 깨짐/겹침 방지)."""
        self._status_full_text = full_text or ""
        try:
            fm = self.status_label.fontMetrics()
            elided = fm.elidedText(self._status_full_text, Qt.ElideRight, self.status_label.width())
            self.status_label.setText(elided)
        except Exception:
            # If status_label not present or causes issues, fallback to log
            log.debug("[CoinlistWidget] _set_status_text failed")

    # ---- search event filter ----
    def eventFilter(self, obj, event):
        # search IME/ESC 위임
        if self.search.event_filter(obj, event):
            return True

        # status label resize 시 elide 갱신
        if obj == getattr(self, "status_label", None) and event.type() in (QEvent.Resize, QEvent.Show):
            self._set_status_text(self._status_full_text)
            return False

        return super().eventFilter(obj, event)

    # ---- external bindings ----
    def setOrder(self, order): self.order = order
    def setChart(self, chart): self.chart = chart
    def setTrade(self, trade): self.trade = trade
    def setOrderbook(self, orderbook): self.orderbook = orderbook

    # ---- progress wrappers ----
    def start_progress(self, status, total_steps): self.progress.start_progress(status, total_steps)
    def update_progress(self, step): self.progress.update_progress(step)
    def end_progress(self): self.progress.end_progress()

    # ---- init table ----
    def _init_table(self):
        try:
            header_style = """
            QHeaderView::section { border: 1px solid gray; font-size: 7pt; min-height: 35px; padding-right: 20px; }
            QHeaderView::down-arrow, QHeaderView::up-arrow { width: 12px; height: 12px; subcontrol-position: top right; }
            """
            self.coin_list.horizontalHeader().setStyleSheet(header_style)
            self.coin_list.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            self.coin_list.setShowGrid(False)

            header = self.coin_list.horizontalHeader()
            header.setDefaultSectionSize(50)
            header.setMinimumSectionSize(50)
            header.setMinimumHeight(35)
            header.setSectionResizeMode(QHeaderView.Interactive)
            header.setSortIndicator(self.current_sort_col, Qt.DescendingOrder)

            self.coin_list.setFont(QFont("Segoe UI", 7))
            self.coin_list.setStyleSheet("QTableWidget { selection-background-color: transparent; }")
            self.coin_list.setItemDelegate(CustomDelegate(self.coin_list))

            self.coin_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.coin_list.customContextMenuRequested.connect(self.show_context_menu)

            self.coin_list.horizontalHeader().sectionClicked.connect(self.chkTopClicked)
            self.coin_list.cellClicked.connect(self.chkItemClicked)
            self.coin_list.cellClicked.connect(self.toggle_favorite)

            self.coin_list.horizontalHeader().sectionResized.connect(self._on_section_resized_save_width)

            self.coin_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.coin_list.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.coin_list.setRowCount(0)
        except Exception:
            log.exception("[CoinlistWidget] _init_table failed")

    def _on_section_resized_save_width(self, logicalIndex: int, oldSize: int, newSize: int):
        # user resize only: 그대로 저장 (기능 변경 없음)
        try:
            self.settings.setValue(f"column_{logicalIndex}_width", newSize)
        except Exception:
            pass

    def _new_item(self, col: int) -> QTableWidgetItem:
        item = QTableWidgetItem()
        align = Qt.AlignRight | Qt.AlignVCenter
        if col in (0, 1):
            align = Qt.AlignCenter | Qt.AlignVCenter
        if col == 2:
            align = Qt.AlignLeft | Qt.AlignVCenter
        item.setTextAlignment(align)
        return item

    def _ensure_initial_items(self):
        """
        안전하게 초기 행을 보장합니다.
        static.chart.coins가 준비되지 않았으면 0행으로 설정.
        """
        try:
            coins = _safe_chart_coins()
            n = len(coins)
            # Ensure at least 0 rows; allocate items structure
            self.coin_list.setRowCount(n)
            self.items = [[QTableWidgetItem() for _ in range(15)] for _ in range(n)]
            for i in range(n):
                for j in range(15):
                    align = Qt.AlignRight | Qt.AlignVCenter
                    if j in (0, 1):
                        align = Qt.AlignCenter | Qt.AlignVCenter
                    if j == 2:
                        align = Qt.AlignLeft | Qt.AlignVCenter
                    self.items[i][j].setTextAlignment(align)
                    try:
                        self.coin_list.setItem(i, j, self.items[i][j])
                    except Exception:
                        pass
        except Exception:
            log.exception("[CoinlistWidget] _ensure_initial_items failed")

    def _load_column_widths_once(self):
        if self._column_widths_loaded:
            return
        self._column_widths_loaded = True
        # header 준비된 뒤 1회만 로드
        QTimer.singleShot(0, self.load_column_widths)

    # ---- init search ----
    def _init_search(self):
        try:
            self.completer = QCompleter(self)
            self.completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.completer.setCompletionMode(QCompleter.PopupCompletion)
            self.completer.setMaxVisibleItems(10)

            self.search_line.setCompleter(self.completer)
            self.completer.activated.connect(self.search.on_completion_activated)
            self.search_line.returnPressed.connect(self.search.on_search_enter)
            
            # ✅ debounce 적용 (검색 입력 100ms)
            self.search_line.textChanged.connect(self._on_search_text_changed_debounced)
            self.search_line.installEventFilter(self)

            completion_list = self.generate_completion_list()
            self.completer.setModel(QStringListModel(completion_list, self.completer))
        except Exception:
            log.exception("[CoinlistWidget] _init_search failed")

    @debounce(100)  # ✅ 100ms debounce
    def _on_search_text_changed_debounced(self, text: str = ""):  # ✅ text 인자 추가
        """
        [Purpose]
        검색 입력 처리 (debounced 100ms)
        
        [Responsibilities]
        - Autocomplete 모델 업데이트
        - 빠른 타이핑 시 마지막 입력만 처리
        
        [Parameters]
        - text: 입력된 텍스�� (textChanged Signal에서 전달)
        """
        try:
            self.search.update_completer_model(text)  # ✅ text 인자 전달
        except Exception:
            log.exception("[CoinlistWidget] _on_search_text_changed_debounced failed")

    # ---- icon checkbox helper ----
    def _make_checkbox_pixmaps(self, size: int = 14) -> tuple[QPixmap, QPixmap]:
        def base_box() -> QPixmap:
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QColor(0, 0, 0))
            p.setBrush(QColor(255, 255, 255))
            p.drawRect(0, 0, size - 1, size - 1)
            p.end()
            return pm

        unchecked = base_box()
        checked = base_box()

        p = QPainter(checked)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(0, 0, 0), 2)
        p.setPen(pen)
        p.drawLine(int(size * 0.20), int(size * 0.55), int(size * 0.45), int(size * 0.75))
        p.drawLine(int(size * 0.42), int(size * 0.75), int(size * 0.80), int(size * 0.25))
        p.end()

        return unchecked, checked

    def _make_icon_toggle_row(self, text: str, initial: bool):
        unchecked_pm, checked_pm = self._make_checkbox_pixmaps(14)

        cb = QCheckBox(text, self)
        cb.setChecked(initial)
        # indicator 숨기고 텍스트만 (검정 사각형 방지)
        cb.setStyleSheet(
            """
            QCheckBox::indicator { width: 0px; height: 0px; }
            QCheckBox { color: #000; background: transparent; spacing: 6px; }
            """
        )
        cb.setCursor(Qt.PointingHandCursor)

        def toggle_cb():
            cb.setChecked(not cb.isChecked())

        icon = _ClickableLabel(self, on_click=toggle_cb)
        icon.setFixedSize(14, 14)
        icon.setPixmap(checked_pm if initial else unchecked_pm)

        def sync_icon(state: int):
            icon.setPixmap(checked_pm if state == Qt.Checked else unchecked_pm)

        cb.stateChanged.connect(sync_icon)
        return icon, cb

    # ---- progress UI controls ----
    def _init_progress_controls(self):
        try:
            enabled = self.settings.value("progress_enabled", True, type=bool)
            always = self.settings.value("progress_always_show", False, type=bool)
            min_ms = self.settings.value("progress_min_show_ms", 200, type=int)

            self.progress.set_options(enabled=enabled, always_show=always, min_show_seconds=min_ms / 1000.0)

            self.lbl_sep = QLabel(" | ", self)

            self.icon_progress_enabled, self.chk_progress_enabled = self._make_icon_toggle_row("상태표시", enabled)
            self.icon_progress_always, self.chk_progress_always = self._make_icon_toggle_row("항상표시", always)

            self.spin_progress_delay = QSpinBox(self)
            self.spin_progress_delay.setRange(0, 2000)
            self.spin_progress_delay.setSingleStep(50)
            self.spin_progress_delay.setValue(min_ms)
            self.spin_progress_delay.setSuffix(" ms")
            self.spin_progress_delay.setFixedHeight(18)
            self.spin_progress_delay.setStyleSheet(
                """
                QSpinBox {
                    border: 1px solid #000;
                    background: #fff;
                    color: #000;
                    padding-left: 6px;
                    padding-right: 6px;
                }
                """
            )

            self.chk_progress_enabled.stateChanged.connect(self._on_progress_option_changed)
            self.chk_progress_always.stateChanged.connect(self._on_progress_option_changed)
            self.spin_progress_delay.valueChanged.connect(self._on_progress_option_changed)

            self._apply_progress_controls_enabled_state()

            layout = getattr(self, "status_layout", None)
            if isinstance(layout, QHBoxLayout):
                layout.addWidget(self.lbl_sep)
                layout.addWidget(self.icon_progress_enabled)
                layout.addWidget(self.chk_progress_enabled)
                layout.addWidget(self.icon_progress_always)
                layout.addWidget(self.chk_progress_always)
                layout.addWidget(self.spin_progress_delay)
            else:
                parent = self.status_label.parent() if hasattr(self, "status_label") else self
                if parent and parent.layout():
                    parent.layout().addWidget(self.icon_progress_enabled)
                    parent.layout().addWidget(self.chk_progress_enabled)
                    parent.layout().addWidget(self.icon_progress_always)
                    parent.layout().addWidget(self.chk_progress_always)
                    parent.layout().addWidget(self.spin_progress_delay)
        except Exception:
            log.exception("[CoinlistWidget] _init_progress_controls failed")

    def _apply_progress_controls_enabled_state(self):
        try:
            enabled = self.chk_progress_enabled.isChecked()
            self.chk_progress_always.setEnabled(enabled)
            self.icon_progress_always.setEnabled(enabled)
            self.spin_progress_delay.setEnabled(enabled)
        except Exception:
            pass

    def _on_progress_option_changed(self):
        try:
            enabled = self.chk_progress_enabled.isChecked()
            always = self.chk_progress_always.isChecked()
            min_ms = int(self.spin_progress_delay.value())

            self.settings.setValue("progress_enabled", enabled)
            self.settings.setValue("progress_always_show", always)
            self.settings.setValue("progress_min_show_ms", min_ms)

            self._apply_progress_controls_enabled_state()
            self.progress.set_options(enabled=enabled, always_show=always, min_show_seconds=min_ms / 1000.0)
        except Exception:
            log.exception("[CoinlistWidget] _on_progress_option_changed failed")

    # ---- bind signals ----
    def _bind_signals(self):
        try:
            self.check_trade_auto.stateChanged.connect(self.logic.toggle_auto_clear)
            self.check_trade_auto.stateChanged.connect(self.save_settings)

            self.btn_rate_clear.clicked.connect(self.logic.manual_rate_reset)
            self.btn_trade_change_clear.clicked.connect(self.logic.manual_trade_reset)
            self.btn_trade_clear.clicked.connect(self.logic.manual_clear)

            self.check_sort_update.stateChanged.connect(self.save_settings)
            self.check_reverse_buy_sell.stateChanged.connect(self.save_settings)
            self.check_hold_eval.stateChanged.connect(self.save_settings)

            self.btn_favorite.clicked.connect(self.show_favorite_popup)
            self.btn_settings.clicked.connect(self.logic.show_settings_popup)
            self.btn_toggle_name.clicked.connect(self.logic.toggle_name_display)

            self.check_price_auto.stateChanged.connect(self.logic.toggle_price_auto)
            self.check_price_auto.stateChanged.connect(self.save_settings)

            self.check_trade_change_auto.stateChanged.connect(self.logic.toggle_trade_change_auto)
            self.check_trade_change_auto.stateChanged.connect(self.save_settings)
        except Exception:
            log.exception("[CoinlistWidget] _bind_signals failed")

    # ---- workers callbacks ----
    def _on_trade_status(self, msg: str):
        try:
            self._set_status_text(f"상태: {msg}")
        except Exception:
            pass

    def _on_trade_accum(self, ticker: str, ask_bid: str, amount: Decimal):
        if self.ignore_accum_update:
            return
        if ticker not in self.trade_buy_accum:
            self.trade_buy_accum[ticker] = Decimal("0")
        if ticker not in self.trade_sell_accum:
            self.trade_sell_accum[ticker] = Decimal("0")

        if ask_bid == "BID":
            self.trade_buy_accum[ticker] += amount
        elif ask_bid == "ASK":
            self.trade_sell_accum[ticker] += amount

        self.logic.handle_accum_updated()

    # ---- actions ----
    def updateData(self, data, force_sort=False):
        try:
            self.logic.updateData(data, force_sort=force_sort)
        except Exception:
            log.exception("[CoinlistWidget] updateData failed")
    
    def chkTopClicked(self, col):
        try:
            self.logic.chkTopClicked(col)
        except Exception:
            log.exception("[CoinlistWidget] chkTopClicked failed")

    def chkItemClicked(self, row=None, col=None):
        """
        [Purpose]
        종목 클릭 시 UIStateManager를 통해 심볼 변경
        
        [Responsibilities]
        - 선택된 종목 코드 추출
        - UIStateManager.set_symbol() 호출
        - 다른 위젯들이 symbol_changed Signal 수신하여 동기화
        
        [Parameters]
        - row: 클릭한 행 번호
        - col: 클릭한 열 번호
        """
        try:
            selected_row = row if row is not None else self.coin_list.currentRow()
            if selected_row < 0 or selected_row >= self.coin_list.rowCount():
                return
            item = self.coin_list.item(selected_row, 2)
            if item and item.text():
                code = item.text().split("\n")[1]
                
                # UIStateManager를 통한 심볼 변경 (있는 경우)
                if self.ui_state_manager:
                    log.info(f"[CoinlistWidget] UIStateManager.set_symbol: {code}")
                    self.ui_state_manager.set_symbol("upbit", code)
                else:
                    # 레거시 방식 (UIStateManager 없는 경우 호환성 유지)
                    log.warning("[CoinlistWidget] UIStateManager 없음, 레거시 방식 사용")
                    if self.order:
                        try: self.order.ow.ticker = code
                        except Exception: pass
                    if self.chart:
                        try: self.chart.set_coin(code)
                        except Exception: pass
                    if self.trade:
                        try: self.trade.set_price(code)
                        except Exception: pass
                    if self.orderbook:
                        QTimer.singleShot(0, lambda: self.orderbook.set_ticker(code))

            if self.search_line.text():
                self.search_line.clear()
                self.coin_list.scrollToItem(self.coin_list.item(selected_row, 0), QAbstractItemView.PositionAtTop)
        except Exception:
            log.exception("[CoinlistWidget] chkItemClicked failed")

    def show_context_menu(self, pos):
        try:
            self.logic.show_context_menu(pos)
        except Exception:
            log.exception("[CoinlistWidget] show_context_menu failed")

    def select_first_row_and_sync(self):
        """
        [Purpose]
        첫 번째 행 선택 및 동기화
        
        [Responsibilities]
        - 앱 시작 시 첫 번째 종목 자동 선택
        - UIStateManager.set_symbol() 호출
        """
        try:
            if self.coin_list.rowCount() > 0:
                self.coin_list.selectRow(0)
                self.chkItemClicked(0)
        except Exception:
            log.exception("[CoinlistWidget] select_first_row_and_sync failed")

    # ---- favorites / completion list ----
    def generate_completion_list(self):
        completion_list = []
        try:
            coins = _safe_chart_coins()
            for coin in coins:
                try:
                    completion_list.append(getattr(coin, "korean_name", "") or "")
                    completion_list.append(getattr(coin, "english_name", "") or "")
                except Exception:
                    continue
            return sorted(set([c for c in completion_list if c]), key=str.lower)
        except Exception:
            log.exception("[CoinlistWidget] generate_completion_list failed")
            return []

    def show_favorite_popup(self):
        try:
            coins = _safe_chart_coins()
            self.fav_popup = FavoriteWidget(self.favorites, coins)
            self.fav_popup.setModal(False)
            QTimer.singleShot(0, self.fav_popup.show)
            self.fav_popup.favorites_updated.connect(self.update_favorites)
        except Exception:
            log.exception("[CoinlistWidget] show_favorite_popup failed")

    def update_favorites(self, favorites):
        try:
            self.favorites = favorites
            self.start_progress("관심종목 업데이트중", 1)
            coins = _safe_chart_coins()
            self.updateData(coins, force_sort=True)
            self.end_progress()
        except Exception:
            log.exception("[CoinlistWidget] update_favorites failed")

    def toggle_favorite(self, row, col):
        try:
            if col != 1:
                return
            item = self.coin_list.item(row, 2)
            if not item or not item.text():
                return
            ticker = item.text().split("\n")[1].split("-")[1]
            if ticker in self.favorites:
                self.favorites.remove(ticker)
            else:
                self.favorites.add(ticker)

            self.start_progress("관심종목 토글 중", 1)
            self.update_favorite_icon(row)
            self.end_progress()
        except Exception:
            log.exception("[CoinlistWidget] toggle_favorite failed")

    def update_favorite_icon(self, row):
        try:
            item = self.coin_list.item(row, 1)
            if not item:
                return
            item_name = self.coin_list.item(row, 2)
            if not item_name or not item_name.text():
                return
            ticker = item_name.text().split("\n")[1].split("-")[1]
            icon_text = "★" if ticker in self.favorites else "☆"
            item.setText(icon_text)
            item.setFont(QFont("Segoe UI", 18, QFont.Bold))
            item.setForeground(self.color_gold if ticker in self.favorites else self.color_gray)
            item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        except Exception:
            log.exception("[CoinlistWidget] update_favorite_icon failed")

    # ---- column widths ----
    def load_column_widths(self):
        try:
            for col in range(self.coin_list.columnCount()):
                width = self.settings.value(f"column_{col}_width", None)
                if width is None:
                    continue
                try:
                    self.coin_list.setColumnWidth(col, int(width))
                except Exception:
                    pass
        except Exception:
            log.exception("[CoinlistWidget] load_column_widths failed")

    # ---- settings persistence ----
    def load_settings(self):
        try:
            self.rate_calc_interval = self.settings.value("rate_calc_interval", 0, type=int)
            self.trade_reset_interval = self.settings.value("trade_reset_interval", 0, type=int)
            self.trade_calc_interval = self.settings.value("trade_calc_interval", 0, type=int)

            self.rate_rise_threshold = self.settings.value("rate_rise_threshold", 5.0, type=float)
            self.rate_fall_threshold = self.settings.value("rate_fall_threshold", -5.0, type=float)
            self.trade_rise_threshold = self.settings.value("trade_rise_threshold", 10.0, type=float)
            self.trade_fall_threshold = self.settings.value("trade_fall_threshold", -10.0, type=float)

            self.check_sort_update.setChecked(self.settings.value("check_sort_update", True, type=bool))
            self.check_price_auto.setChecked(self.settings.value("check_price_auto", False, type=bool))
            self.check_trade_change_auto.setChecked(self.settings.value("check_trade_change_auto", False, type=bool))
            self.check_trade_auto.setChecked(self.settings.value("check_trade_auto", False, type=bool))
            self.check_reverse_buy_sell.setChecked(self.settings.value("check_reverse_buy_sell", False, type=bool))
            self.check_hold_eval.setChecked(self.settings.value("check_hold_eval", False, type=bool))

            self.current_sort_col = self.settings.value("current_sort_col", 5, type=int)
            self.sort_states[self.current_sort_col] = self.settings.value("sort_state", -1, type=int)
            if not self.settings.contains("sort_state"):
                self.current_sort_col = 5
                self.sort_states[5] = -1

            self.coin_list.horizontalHeader().setSortIndicator(
                self.current_sort_col,
                Qt.DescendingOrder if self.sort_states[self.current_sort_col] == -1 else Qt.AscendingOrder,
            )

            self.name_toggle_korean = getattr(config, "name_toggle_korean", True)
            try:
                self.btn_toggle_name.setText("영문" if not self.name_toggle_korean else "한글")
            except Exception:
                pass
        except Exception:
            log.exception("[CoinlistWidget] load_settings failed")

    def save_settings(self):
        try:
            self.settings.setValue("rate_calc_interval", self.rate_calc_interval)
            self.settings.setValue("trade_reset_interval", self.trade_reset_interval)
            self.settings.setValue("trade_calc_interval", self.trade_calc_interval)

            self.settings.setValue("rate_rise_threshold", self.rate_rise_threshold)
            self.settings.setValue("rate_fall_threshold", self.rate_fall_threshold)
            self.settings.setValue("trade_rise_threshold", self.trade_rise_threshold)
            self.settings.setValue("trade_fall_threshold", self.trade_fall_threshold)

            self.settings.setValue("check_sort_update", self.check_sort_update.isChecked())
            self.settings.setValue("check_price_auto", self.check_price_auto.isChecked())
            self.settings.setValue("check_trade_change_auto", self.check_trade_change_auto.isChecked())
            self.settings.setValue("check_trade_auto", self.check_trade_auto.isChecked())
            self.settings.setValue("check_reverse_buy_sell", self.check_reverse_buy_sell.isChecked())
            self.settings.setValue("check_hold_eval", self.check_hold_eval.isChecked())

            self.settings.setValue("current_sort_col", self.current_sort_col)
            self.settings.setValue("sort_state", self.sort_states[self.current_sort_col])
        except Exception:
            log.exception("[CoinlistWidget] save_settings failed")

    # ---- safe close ----
    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        try:
            if hasattr(self, "idle_timer") and self.idle_timer:
                self.idle_timer.stop()
        except Exception:
            pass

        try:
            self.remaining_timer.stop()
            self.price_timer.stop()
            self.trade_change_timer.stop()
            self.clear_timer.stop()
            self.update_debounce_timer.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "cw") and self.cw:
                self.cw.close()
        except Exception:
            pass
        try:
            if hasattr(self, "tw") and self.tw:
                self.tw.close()
        except Exception:
            pass

        try:
            if hasattr(self, "progress") and self.progress:
                self.progress.shutdown()
        except Exception:
            pass

        return super().closeEvent(a0)