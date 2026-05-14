# -*- coding: utf-8 -*-
"""
호가창 위젯 - market 모듈 연동
"""
from __future__ import annotations
import sys
from pathlib import Path

_market_dir = str(Path(__file__).parents[4] / "market")
if _market_dir not in sys.path:
    sys.path.insert(0, _market_dir)

try:
    from src._market import OrderbookWidget  # type: ignore
except ImportError:
    try:
        from orderbook import OrderbookWidget  # type: ignore
    except ImportError:
        OrderbookWidget = None  # type: ignore

if OrderbookWidget is None:
    # Standalone fallback: self-contained implementation independent of market
    try:
        from PyQt5.QtWidgets import (
            QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
            QLabel, QHeaderView, QAbstractItemView,
        )
        from PyQt5.QtCore import Qt as _Qt

        class OrderbookWidget(QWidget):  # type: ignore[no-redef]
            """Fallback 호가창 위젯."""

            def __init__(self, parent=None):
                super().__init__(parent)
                self._current_symbol: str = ""
                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(2)

                self._label = QLabel("호가창\n심볼을 선택하면 호가가 표시됩니다.", self)
                self._label.setAlignment(_Qt.AlignCenter)

                self._asks_table = QTableWidget(0, 2, self)
                self._asks_table.setHorizontalHeaderLabels(["가격(매도)", "수량"])
                self._bids_table = QTableWidget(0, 2, self)
                self._bids_table.setHorizontalHeaderLabels(["가격(매수)", "수량"])

                for tbl in (self._asks_table, self._bids_table):
                    hdr = tbl.horizontalHeader()
                    hdr.setSectionResizeMode(0, QHeaderView.Stretch)
                    hdr.setSectionResizeMode(1, QHeaderView.Stretch)
                    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
                    tbl.setSelectionMode(QAbstractItemView.NoSelection)

                layout.addWidget(self._label)
                layout.addWidget(self._asks_table)
                layout.addWidget(self._bids_table)

            def update_symbol(self, source: str, symbol: str) -> None:
                self._current_symbol = symbol
                self._label.setText(f"호가창: {symbol}")
                self._asks_table.setRowCount(0)
                self._bids_table.setRowCount(0)

            def update_data(self, data) -> None:
                if not isinstance(data, dict):
                    return
                asks = data.get("asks", [])
                bids = data.get("bids", [])
                self._fill_table(self._asks_table, asks)
                self._fill_table(self._bids_table, bids)

            def _fill_table(self, table, rows) -> None:
                table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    if isinstance(row, (list, tuple)) and len(row) >= 2:
                        price, qty = str(row[0]), str(row[1])
                    elif isinstance(row, dict):
                        price = str(row.get("price", row.get("ask_price", row.get("bid_price", ""))))
                        qty = str(row.get("size", row.get("ask_size", row.get("bid_size", ""))))
                    else:
                        price, qty = str(row), ""
                    table.setItem(i, 0, QTableWidgetItem(price))
                    table.setItem(i, 1, QTableWidgetItem(qty))

    except Exception:
        OrderbookWidget = None  # type: ignore[assignment]

__all__ = ["OrderbookWidget"]
