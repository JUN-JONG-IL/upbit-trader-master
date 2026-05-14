"""
WidgetLoader - 커스텀 위젯 생성 및 임베드 (v10.0)

책임:
- _make_* 메서드: 각 위젯 생성 (실패 시 폴백 레이블)
- embed_widgets(): main.ui 플레이스홀더에 위젯 삽입
- _load_widget_class(): 파일 경로 기반 위젯 클래스 동적 로딩
"""
from __future__ import annotations

import importlib.util
import logging
import os
from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class WidgetLoader:
    """위젯 생성 및 임베드 관리"""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    # ─────────────────────────────────────── 임베드 진입점 ──

    def embed_widgets(self) -> None:
        """main.ui 플레이스홀더에 커스텀 위젯을 삽입합니다."""
        _tasks: list = [
            ("coinlist_widget", "_symbol_table", self._make_symbol_widget),
            ("chart_widget", "_chart_widget_inst", self._make_chart_widget),
            ("orderbook_widget", "_orderbook_widget_inst", self._make_orderbook_widget),
            ("trade_widget", "_trade_widget_inst", self._make_trade_widget),
            ("holding_list_widget", "_holding_widget_inst", self._make_holding_widget),
            ("search_frame_widget", "_search_widget_inst", self._make_search_widget),
        ]

        for placeholder_name, attr_name, factory in _tasks:
            placeholder = getattr(self.main_window, placeholder_name, None)
            if placeholder is None:
                logger.debug("[WidgetLoader] 플레이스홀더 없음: %s", placeholder_name)
                continue
            self._embed_single_widget(placeholder_name, attr_name, factory, placeholder)

    def _embed_single_widget(
        self,
        placeholder_name: str,
        attr_name: str,
        factory: Callable,
        placeholder: Any,
    ) -> None:
        """단일 위젯을 플레이스홀더에 임베드합니다."""
        try:
            widget = factory(placeholder)
            if widget is None:
                logger.warning("[WidgetLoader] %s 위젯 생성 실패 - fallback 생성", attr_name)
                widget = self._create_fallback_label(attr_name, placeholder)

            existing_layout = placeholder.layout()
            if existing_layout is not None:
                self._clear_layout_safely(existing_layout)
                layout = existing_layout
            else:
                layout = QVBoxLayout(placeholder)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)

            layout.addWidget(widget)
            setattr(self.main_window, attr_name, widget)
            logger.info("[WidgetLoader] %s → %s 임베드 완료", attr_name, placeholder_name)

        except Exception as e:
            logger.warning(
                "[WidgetLoader] %s 임베드 실패: %s", placeholder_name, e, exc_info=True
            )
            try:
                fallback = self._create_fallback_label(placeholder_name, placeholder)
                existing_layout = placeholder.layout()
                if existing_layout is None:
                    layout = QVBoxLayout(placeholder)
                    layout.setContentsMargins(0, 0, 0, 0)
                else:
                    layout = existing_layout
                layout.addWidget(fallback)
            except Exception:
                pass

    def _clear_layout_safely(self, layout: Any) -> None:
        """레이아웃에서 모든 위젯을 안전하게 제거합니다."""
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout_safely(item.layout())

    @staticmethod
    def _create_fallback_label(name: str, parent: Any) -> QLabel:
        """폴백 레이블 생성"""
        label = QLabel(f"⚠️ {name} 로딩 실패", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #999; font-size: 10pt;")
        return label

    # ─────────────────────────────────────── 위젯 클래스 동적 로딩 ──

    @staticmethod
    def _load_widget_class(rel_path: str, class_name: str) -> Optional[Any]:
        """
        src/ 디렉터리 기준 상대 경로로 위젯 클래스를 로드합니다.
        importlib.util.spec_from_file_location 을 사용하므로 sys.path 조작이 불필요합니다.
        """
        src_root = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
        )
        abs_path = os.path.join(src_root, rel_path)
        if not os.path.isfile(abs_path):
            return None

        mod_name = rel_path.replace(os.sep, ".")
        if mod_name.endswith(".py"):
            mod_name = mod_name[:-3]

        spec = importlib.util.spec_from_file_location(mod_name, abs_path)
        if spec is None or spec.loader is None:
            return None

        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return getattr(mod, class_name, None)

    # ─────────────────────────────────────── 개별 위젯 팩토리 ──

    def _make_symbol_widget(self, parent: Any) -> Optional[Any]:
        """종목 목록 위젯 생성 (src/market/coinlist/ui/widget_coin_list.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("market", "coinlist", "ui", "widget_coin_list.py"),
                "CoinlistWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] CoinlistWidget 로드 성공")
                return cls(parent)
        except Exception as e:
            logger.debug("[WidgetLoader] CoinlistWidget 로드 실패: %s", e)

        # 기본 QTableWidget 폴백
        table = QTableWidget(0, 4, parent)
        table.setHorizontalHeaderLabels(["심볼", "현재가", "등락률", "거래량"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.itemClicked.connect(self.main_window._on_symbol_item_clicked)
        logger.info("[WidgetLoader] QTableWidget(fallback)으로 coinlist_widget 초기화")
        return table

    def _make_chart_widget(self, parent: Any) -> Optional[Any]:
        """차트 위젯 생성 (src/chart/ui/widget_chart.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("chart", "ui", "widget_chart.py"),
                "ChartWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] ChartWidget 로드 성공")
                return cls(parent, ui_state_manager=getattr(self.main_window, "ui_state_manager", None))
        except Exception as e:
            logger.debug("[WidgetLoader] ChartWidget 로드 실패: %s", e)

        label = QLabel("차트 영역\n심볼을 선택하면 차트가 표시됩니다.", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: #f0f0f0; font-size: 14pt;")
        return label

    def _make_orderbook_widget(self, parent: Any) -> Optional[Any]:
        """호가창 위젯 생성 (src/market/orderbook/ui/widget_orderbook.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("market", "orderbook", "ui", "widget_orderbook.py"),
                "OrderbookWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] OrderbookWidget 로드 성공")
                return cls(parent)
        except Exception as e:
            logger.debug("[WidgetLoader] OrderbookWidget 로드 실패: %s", e)

        label = QLabel("호가창\n심볼을 선택하면 호가가 표시됩니다.", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: #f0f0f0; font-size: 14pt;")
        return label

    def _make_trade_widget(self, parent: Any) -> Optional[Any]:
        """체결창 위젯 생성 (src/market/trades/ui/widget_trade.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("market", "trades", "ui", "widget_trade.py"),
                "TradeWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] TradeWidget 로드 성공")
                return cls(parent)
        except Exception as e:
            logger.debug("[WidgetLoader] TradeWidget 로드 실패: %s", e)

        label = QLabel("체결창\n심볼을 선택하면 체결 내역이 표시됩니다.", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: #f0f0f0; font-size: 14pt;")
        return label

    def _make_holding_widget(self, parent: Any) -> Optional[Any]:
        """보유 종목 위젯 생성 (src/portfolio/holdings/ui/widget_holding_list.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("portfolio", "holdings", "ui", "widget_holding_list.py"),
                "HoldingListWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] HoldingListWidget 로드 성공")
                return cls(parent)
        except Exception as e:
            logger.debug("[WidgetLoader] HoldingListWidget 로드 실패: %s", e)

        label = QLabel("보유 종목\n포트폴리오 영역", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: #f0f0f0; font-size: 14pt;")
        return label

    def _make_search_widget(self, parent: Any) -> Optional[Any]:
        """종목 검색 위젯 생성 (src/scanner/engine/ui/widget_scanner_frame.py)"""
        try:
            cls = self._load_widget_class(
                os.path.join("scanner", "engine", "ui", "widget_scanner_frame.py"),
                "ScannerFrameWidget",
            )
            if cls is not None:
                logger.info("[WidgetLoader] ScannerFrameWidget 로드 성공")
                return cls(parent)
        except Exception as e:
            logger.debug("[WidgetLoader] ScannerFrameWidget 로드 실패: %s", e)

        label = QLabel("종목 검색\n스캐너 영역", parent)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: #f0f0f0; font-size: 14pt;")
        return label
