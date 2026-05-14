# -*- coding: utf-8 -*-
"""
종목 테이블 위젯 - 03_market 모듈 연동
"""
from __future__ import annotations
import sys
from pathlib import Path

_market_dir = str(Path(__file__).parents[4] / "03_market")
if _market_dir not in sys.path:
    sys.path.insert(0, _market_dir)

try:
    from src._03_market import CoinlistWidget as SymbolTableWidget  # type: ignore
except ImportError:
    try:
        from symbol_list import CoinlistWidget as SymbolTableWidget  # type: ignore
    except ImportError:
        SymbolTableWidget = None  # type: ignore

if SymbolTableWidget is None:
    # Standalone fallback: self-contained implementation independent of 03_market
    try:
        from PyQt5.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        )
        from PyQt5.QtCore import Qt as _Qt

        class SymbolTableWidget(QTableWidget):  # type: ignore[no-redef]
            """Fallback 종목 목록 테이블 위젯."""

            COLUMNS = ["심볼", "현재가", "등락률", "거래량"]

            def __init__(self, parent=None):
                super().__init__(0, len(self.COLUMNS), parent)
                self.setHorizontalHeaderLabels(self.COLUMNS)
                hdr = self.horizontalHeader()
                hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
                for col in range(1, len(self.COLUMNS)):
                    hdr.setSectionResizeMode(col, QHeaderView.Stretch)
                self.setSelectionBehavior(QAbstractItemView.SelectRows)
                self.setEditTriggers(QAbstractItemView.NoEditTriggers)
                self.setAlternatingRowColors(True)
                self.setSortingEnabled(True)

            def update_data(self, symbols) -> None:
                self.setSortingEnabled(False)
                self.setRowCount(len(symbols))
                for row, item in enumerate(symbols):
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        symbol = str(item[1])
                    else:
                        symbol = str(item)
                    self.setItem(row, 0, QTableWidgetItem(symbol))
                    for col in range(1, len(self.COLUMNS)):
                        self.setItem(row, col, QTableWidgetItem("--"))
                self.setSortingEnabled(True)

            def update_symbol(self, source: str, symbol: str) -> None:
                for row in range(self.rowCount()):
                    item_cell = self.item(row, 0)
                    if item_cell and item_cell.text() == symbol:
                        self.selectRow(row)
                        break

    except Exception:
        SymbolTableWidget = None  # type: ignore[assignment]

__all__ = ["SymbolTableWidget"]
