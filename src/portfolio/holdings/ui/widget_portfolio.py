"""
portfolio/ui/widget_portfolio.py

[Purpose]
- 보유 종목(포트폴리오) 현황을 탭 위젯으로 표시하는 메인 포트폴리오 위젯.
- HoldingListWidget(보유 목록)과 DetailHoldingWidget(상세 정보)를 통합.

[UI Binding]
- holding_list.ui
- detail_holding_list.ui
"""
from __future__ import annotations

import logging

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget

    class PortfolioWidget(QWidget):
        """
        포트폴리오 메인 위젯.

        보유 목록(HoldingListWidget)과 상세 보유 정보(DetailHoldingWidget)를
        하나의 탭 위젯으로 통합하여 표시합니다.
        """

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._setup_ui()

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            self._tabs = QTabWidget(self)
            layout.addWidget(self._tabs)

            # 보유 목록 탭
            try:
                from .widget_holding_list import HoldingListWidget  # type: ignore[import]
                self._holding_list = HoldingListWidget(self)
                self._tabs.addTab(self._holding_list, "보유 목록")
            except Exception as e:
                logging.warning("HoldingListWidget unavailable: %s", e)
                placeholder = QtWidgets.QLabel("보유 목록 (불러오기 실패)")
                self._tabs.addTab(placeholder, "보유 목록")

            # 상세 정보 탭
            try:
                from .widget_detail_holding import DetailHoldingWidget  # type: ignore[import]
                self._detail_holding = DetailHoldingWidget(self)
                self._tabs.addTab(self._detail_holding, "상세 정보")
            except Exception as e:
                logging.warning("DetailHoldingWidget unavailable: %s", e)
                placeholder = QtWidgets.QLabel("상세 정보 (불러오기 실패)")
                self._tabs.addTab(placeholder, "상세 정보")

except Exception as _qt_error:
    logging.warning("PyQt5 not available, using placeholder PortfolioWidget: %s", _qt_error)

    class PortfolioWidget:  # type: ignore[no-redef]
        """Placeholder PortfolioWidget (PyQt5 not available)."""

        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PortfolioWidget (no GUI).")
