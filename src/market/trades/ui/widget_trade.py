#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 체결 데이터(TradeWidget) 위젯: 최근 체결 내역 표시

[Responsibilities]
- 실시간 체결 내역 표시 (WebSocket/폴링)
- 매수/매도 구분 색상
- 최근 100건 유지
- UIStateManager 연동 (심볼 변경 동기화)

[UI Binding]
- src/market/trades/ui/trade.ui
  - trade_table: 체결 내역 테이블 (Time, Price, Volume, Side)

[Author] Copilot + Phase 2 Integration
[Created] 2026-01-23
[Modified] 2026-03-12
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from PyQt5 import QtCore, QtGui, QtWidgets, uic
    from PyQt5.QtWidgets import (
        QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
        QLabel, QHeaderView, QAbstractItemView,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QColor
    _HAS_QT = True
except Exception as _e:
    try:
        from utils.qt_stub import QtCore, QtGui, QtWidgets  # type: ignore
        uic = None  # type: ignore
        QWidget = getattr(QtWidgets, "QWidget", object)
        QTableWidget = getattr(QtWidgets, "QTableWidget", object)
        QTableWidgetItem = getattr(QtWidgets, "QTableWidgetItem", object)
        QVBoxLayout = getattr(QtWidgets, "QVBoxLayout", None)
        QLabel = getattr(QtWidgets, "QLabel", object)
        QHeaderView = getattr(QtWidgets, "QHeaderView", None)
        QAbstractItemView = getattr(QtWidgets, "QAbstractItemView", None)
        Qt = getattr(QtCore, "Qt", None)
        QThread = getattr(QtCore, "QThread", object)
        pyqtSignal = getattr(QtCore, "pyqtSignal", None)
        QColor = getattr(QtGui, "QColor", None)
        _HAS_QT = False
    except Exception:
        QWidget = object
        QTableWidget = object
        QTableWidgetItem = object
        QVBoxLayout = None
        QLabel = object
        QHeaderView = None
        QAbstractItemView = None
        Qt = None
        QThread = object
        pyqtSignal = None
        QColor = None
        uic = None  # type: ignore
        _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "trade.ui")


class TradeWorker(QThread):
    """
    [Purpose]
    체결 데이터 폴링 워커 스레드 (1초 주기)

    [Responsibilities]
    - aiopyupbit REST API로 최근 체결 내역 조회
    - dataSent Signal 발행
    """

    if _HAS_QT and pyqtSignal is not None:
        dataSent = pyqtSignal(list)
    else:
        dataSent = None  # type: ignore

    def __init__(self, ticker: str = "KRW-BTC") -> None:
        if _HAS_QT:
            super().__init__()
        self._ticker = ticker
        self._alive = False

    def run(self) -> None:
        self._alive = True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._poll_loop())
        finally:
            loop.close()

    async def _poll_loop(self) -> None:
        while self._alive:
            await asyncio.sleep(1.0)
            try:
                await self._fetch_and_emit()
            except Exception:
                pass

    async def _fetch_and_emit(self) -> None:
        try:
            import aiopyupbit  # type: ignore
            trades = await aiopyupbit.get_trades_ticks(self._ticker, count=20)
            if trades is not None and self.dataSent is not None:
                self.dataSent.emit(trades if isinstance(trades, list) else [])
        except Exception:
            pass

    def set_ticker(self, ticker: str) -> None:
        self._ticker = ticker

    def close(self) -> None:
        self._alive = False
        if _HAS_QT:
            self.quit()
            self.wait()


class TradeWidget(QWidget):
    """
    체결 데이터 메인 위젯.

    - 최근 체결 내역 표시 (trade_table)
    - 매수/매도 구분 색상 (빨강=매수, 파랑=매도)
    - 최근 100건 유지
    - UIStateManager 연동: update_symbol()로 심볼 업데이트
    """

    _COLOR_BUY = "#f87171"   # 매수 빨강
    _COLOR_SELL = "#60a5fa"  # 매도 파랑
    _MAX_TRADES = 100

    def __init__(self, parent: Optional[QWidget] = None,
                 ui_state_manager: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._current_symbol: str = ""
        self._worker: Optional[TradeWorker] = None

        self._load_ui()
        self._init_table()

        # UIStateManager 연동
        self.ui_state_manager = ui_state_manager
        if ui_state_manager is not None:
            try:
                ui_state_manager.symbol_changed.connect(self._on_symbol_changed)
            except Exception:
                pass

    # ──────────────────────────────────────────── UI 초기화 ──

    def _load_ui(self) -> None:
        """trade.ui 로드 (없으면 기본 레이아웃 생성)."""
        try:
            if uic is not None and os.path.isfile(_UI_PATH):
                uic.loadUi(_UI_PATH, self)
                return
        except Exception:
            pass
        self._build_fallback_ui()

    def _build_fallback_ui(self) -> None:
        """UI 파일 없을 때 순수 코드로 레이아웃 구성."""
        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.trade_table = QTableWidget(0, 4, self)
            self.trade_table.setHorizontalHeaderLabels(["시간", "가격", "수량", "구분"])
            layout.addWidget(self.trade_table)
        except Exception:
            pass

    def _init_table(self) -> None:
        """trade_table 초기화."""
        try:
            tbl = getattr(self, "trade_table", None)
            if tbl is None:
                return
            if QAbstractItemView is not None:
                tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
                tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            if QHeaderView is not None:
                hdr = tbl.horizontalHeader()
                for col in range(tbl.columnCount()):
                    hdr.setSectionResizeMode(col, QHeaderView.Stretch)
            try:
                tbl.verticalHeader().setVisible(False)
            except Exception:
                pass
        except Exception:
            pass

    # ──────────────────────────────────────────── 심볼 변경 ──

    def update_symbol(self, source: str, symbol: str) -> None:
        """심볼 업데이트 (외부 호출 및 UIStateManager 연동용).

        Args:
            source: 데이터 소스 (예: "upbit")
            symbol: 심볼 코드 (예: "KRW-BTC")
        """
        self._on_symbol_changed(source, symbol)

    def _on_symbol_changed(self, source: str, symbol: str) -> None:
        """심볼 변경 처리: 테이블 초기화 및 워커 재시작."""
        if symbol == self._current_symbol:
            return
        self._current_symbol = symbol

        # 테이블 초기화
        try:
            tbl = getattr(self, "trade_table", None)
            if tbl is not None:
                tbl.setRowCount(0)
        except Exception:
            pass

        self._restart_worker(symbol)

    def _restart_worker(self, ticker: str) -> None:
        """기존 워커 정지 후 새 워커 시작."""
        try:
            if self._worker is not None:
                self._worker.close()
                self._worker = None
        except Exception:
            pass

        try:
            if not _HAS_QT:
                return
            self._worker = TradeWorker(ticker)
            if self._worker.dataSent is not None:
                self._worker.dataSent.connect(self._on_trades_received)
            self._worker.start()
        except Exception:
            pass

    # ──────────────────────────────────────────── 데이터 업데이트 ──

    def _on_trades_received(self, trades: List[Dict[str, Any]]) -> None:
        """워커로부터 체결 데이터 수신 시 UI 갱신."""
        try:
            tbl = getattr(self, "trade_table", None)
            if tbl is None or not trades:
                return

            align_c = Qt.AlignCenter if Qt is not None else 0
            align_r = (Qt.AlignRight | Qt.AlignVCenter) if Qt is not None else 0

            for trade in trades:
                if not isinstance(trade, dict):
                    continue
                self._insert_trade_row(tbl, trade, align_c, align_r)

            # 최대 건수 유지
            while tbl.rowCount() > self._MAX_TRADES:
                tbl.removeRow(tbl.rowCount() - 1)
        except Exception:
            pass

    def _insert_trade_row(self, tbl: QTableWidget, trade: Dict[str, Any],
                          align_c: int, align_r: int) -> None:
        """체결 한 건을 테이블 최상단에 삽입."""
        try:
            tbl.insertRow(0)

            # 시간
            ts = trade.get("timestamp", trade.get("trade_timestamp", 0))
            try:
                time_str = datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
            except Exception:
                time_str = "--"

            # 가격
            price = trade.get("trade_price", trade.get("price", 0))

            # 수량
            volume = trade.get("trade_volume", trade.get("size", trade.get("volume", 0)))

            # 구분 (ask_bid: ASK=매도, BID=매수)
            ask_bid = trade.get("ask_bid", trade.get("side", ""))
            if ask_bid == "BID":
                side_text = "매수"
                color = QColor(self._COLOR_BUY) if QColor is not None else None
            else:
                side_text = "매도"
                color = QColor(self._COLOR_SELL) if QColor is not None else None

            def _item(text: str, align: int,
                      fg: Optional[QColor] = None) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                if align:
                    it.setTextAlignment(align)
                if fg is not None:
                    it.setForeground(fg)
                return it

            tbl.setItem(0, 0, _item(time_str, align_c))
            tbl.setItem(0, 1, _item(f"{price:,.0f}", align_r, color))
            tbl.setItem(0, 2, _item(f"{volume:.4f}", align_r))
            tbl.setItem(0, 3, _item(side_text, align_c, color))
        except Exception:
            pass

    def add_trade(self, trade: Dict[str, Any]) -> None:
        """외부에서 체결 한 건 직접 추가.

        Args:
            trade: dict with keys trade_price, trade_volume, ask_bid, timestamp
        """
        try:
            tbl = getattr(self, "trade_table", None)
            if tbl is None:
                return
            align_c = Qt.AlignCenter if Qt is not None else 0
            align_r = (Qt.AlignRight | Qt.AlignVCenter) if Qt is not None else 0
            self._insert_trade_row(tbl, trade, align_c, align_r)
            while tbl.rowCount() > self._MAX_TRADES:
                tbl.removeRow(tbl.rowCount() - 1)
        except Exception:
            pass

    # ──────────────────────────────────────────── 종료 처리 ──

    def closeEvent(self, event: Any) -> None:
        try:
            if self._worker is not None:
                self._worker.close()
        except Exception:
            pass
        super().closeEvent(event)


__all__ = ["TradeWidget", "TradeWorker"]
