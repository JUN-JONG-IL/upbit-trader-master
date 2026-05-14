#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 호가(매수/매도), 체결 내역(티커 기반), 거래 강도/합계, 마켓뎁스 그래프를 표시하는 호가창 위젯.

[Responsibilities]
- Orderbook 실시간 업데이트 (throttle 500ms)
- UIStateManager 연동 (심볼 변경 동기화)
- 1종목만 구독 (심볼 변경 시 재구독)
- 호가 깊이 시각화 (matplotlib, 선택적)
- 15단계 호가창 (매수/매도), 진행바 잔량 표시
- 52주 고/저가, 당일 고/저가, 거래강도, 누적거래량/거래대금 패널
- 그룹 호가 보기 (모아보기), 수량/총액 토글
- 호가 클릭 → TradeWidget 가격 자동 입력

[Notes - logging reduced]
- 콘솔/터미널에 찍히는 로그를 최소화했습니다.
- 상세 정보는 static.DEBUG_MODE=True 또는 logger 레벨이 DEBUG일 때만 찍힙니다.
"""

from __future__ import annotations

import math
import os
import time
import asyncio as aio
import traceback
from typing import Any, Dict, List, Optional

try:
    from PyQt5 import QtGui, uic
    from PyQt5.QtWidgets import QWidget, QHeaderView, QTableWidgetItem, QProgressBar, QApplication
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QtGui = None  # type: ignore[assignment]
    uic = None  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment,misc]
    QHeaderView = None  # type: ignore[assignment]
    QTableWidgetItem = object  # type: ignore[assignment,misc]
    QProgressBar = object  # type: ignore[assignment,misc]
    QApplication = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]
    QThread = object  # type: ignore[assignment,misc]
    pyqtSignal = None  # type: ignore[assignment]
    QTimer = None  # type: ignore[assignment]

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MPL = True
except Exception:
    FigureCanvas = object  # type: ignore[assignment,misc]
    Figure = None  # type: ignore[assignment]
    _HAS_MPL = False

try:
    import static  # type: ignore[import]
    log = getattr(static, "log", None)
    if log is None:
        import logging
        log = logging.getLogger(__name__)
except ImportError:
    try:
        from app import static  # type: ignore[import]
        log = getattr(static, "log", None)
        if log is None:
            import logging
            log = logging.getLogger(__name__)
    except ImportError:
        static = None  # type: ignore[assignment]
        import logging
        log = logging.getLogger(__name__)

try:
    from component import Coin  # type: ignore[import]
    _HAS_COIN = True
except ImportError:
    Coin = None  # type: ignore[assignment]
    _HAS_COIN = False

try:
    from utils import throttle  # type: ignore[import]
    _HAS_THROTTLE = True
except ImportError:
    _HAS_THROTTLE = False

    def throttle(ms: int):  # type: ignore[misc]
        """Fallback no-op throttle decorator."""
        def decorator(fn):
            return fn
        return decorator


_UI_PATH = os.path.join(os.path.dirname(__file__), "orderbook.ui")


class OrderbookWorker(QThread):
    """
    Orderbook 데이터 폴링 워커 스레드

    - static.chart.coins 이용 가능 시: Coin 객체를 0.5초마다 emit
    - 불가 시: aiopyupbit REST API로 호가 데이터 조회 후 dict emit
    """

    if _HAS_QT and pyqtSignal is not None:
        dataSent = pyqtSignal(object)
    else:
        dataSent = None  # type: ignore

    def __init__(self, ticker: str = "KRW-BTC") -> None:
        if _HAS_QT:
            super().__init__()
        self.ticker = ticker
        self.alive = False

    def run(self) -> None:
        self.alive = True
        if static is not None and hasattr(static, "chart"):
            self._run_static()
        else:
            loop = aio.new_event_loop()
            aio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_rest())
            finally:
                loop.close()

    def _run_static(self) -> None:
        """static.chart.coins 기반 폴링 루프."""
        while self.alive:
            time.sleep(0.5)
            try:
                coins = getattr(getattr(static, "chart", None), "coins", None)
                if coins:
                    coin = coins.get(self.ticker)
                    if coin and self.dataSent is not None:
                        self.dataSent.emit(coin)
            except Exception:
                if getattr(static, "DEBUG_MODE", False):
                    log.exception("[OrderbookWorker] Poll error")

    async def _run_rest(self) -> None:
        """aiopyupbit REST API 기반 폴링 루프 (fallback)."""
        while self.alive:
            await aio.sleep(0.5)
            try:
                import aiopyupbit  # type: ignore
                orderbook = await aiopyupbit.get_orderbook(self.ticker)
                if orderbook and self.dataSent is not None:
                    self.dataSent.emit({"_type": "rest_orderbook", "data": orderbook, "ticker": self.ticker})
            except Exception:
                pass

    def close(self) -> None:
        self.alive = False
        if _HAS_QT:
            self.quit()
            self.wait()


if _HAS_MPL and _HAS_QT:
    class DepthCanvas(FigureCanvas):
        """Matplotlib 기반 호가 깊이 차트 캔버스."""
        def __init__(self, parent=None, width: int = 5, height: int = 2, dpi: int = 100):
            self.fig = Figure(figsize=(width, height), dpi=dpi)
            self.fig.patch.set_facecolor("white")
            self.ax = self.fig.add_subplot(111)
            self.ax.patch.set_facecolor("white")
            self.ax.tick_params(axis="x", colors="black", labelsize=6)
            self.ax.tick_params(axis="y", colors="black", labelsize=6)
            self.ax.spines["top"].set_visible(False)
            self.ax.spines["right"].set_visible(False)
            self.ax.spines["bottom"].set_color("black")
            self.ax.spines["left"].set_color("black")
            self.ax.grid(True, color="black", alpha=0.5, linestyle="--")
            self.ax.margins(0.05)
            self.fig.tight_layout()
            super().__init__(self.fig)
            self.setParent(parent)
else:
    DepthCanvas = None  # type: ignore[assignment,misc]


class OrderbookWidget(QWidget):
    """
    호가창 메인 위젯.

    - 매도/매수 15단계 호가 표시 (tableAsks / tableBids)
    - 잔량 진행바 (QProgressBar, 컬럼 1)
    - 실시간 체결 내역 표시 (tableTrades, 15행)
    - 호가 깊이 차트 (matplotlib, layout_market_depth_chart)
    - 거래강도, 누적매도/매수 합계, 52주 고/저가 패널
    - 수량/총액 토글 (pushButton_toggle_quantity)
    - 그룹 호가 보기 (comboBox_group_view)
    - 호가 클릭 → TradeWidget 가격 입력 (setTrade)
    - UIStateManager 연동: symbol_changed 시그널 구독
    """

    def __init__(self, parent: Optional[Any] = None,
                 ticker: str = "KRW-BTC",
                 ui_state_manager: Optional[Any] = None) -> None:
        if _HAS_QT:
            super().__init__(parent)
        else:
            return

        if uic is not None and os.path.isfile(_UI_PATH):
            uic.loadUi(_UI_PATH, self)

        # UIStateManager 연동
        self.ui_state_manager = ui_state_manager
        self.current_symbol: Optional[str] = None

        if self.ui_state_manager:
            try:
                self.ui_state_manager.symbol_changed.connect(self._on_symbol_changed)
            except Exception:
                pass

        # 테이블 헤더 크기
        for tbl_name in ("tableAsks", "tableBids", "tableTrades"):
            tbl = getattr(self, tbl_name, None)
            if tbl is None or QHeaderView is None:
                continue
            header = tbl.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)
            header.setDefaultSectionSize(40)
            header.setMinimumSectionSize(40)
            header.setMinimumHeight(40)
            header.update()

        # 컬럼 너비 (asks / bids: 4 columns)
        for tbl_name in ("tableAsks", "tableBids"):
            tbl = getattr(self, tbl_name, None)
            if tbl is None:
                continue
            for col, w in enumerate([80, 90, 90, 60]):
                tbl.setColumnWidth(col, w)

        tbl_trades = getattr(self, "tableTrades", None)
        if tbl_trades is not None:
            tbl_trades.setColumnWidth(0, 90)
            tbl_trades.setColumnWidth(1, 80)

        for tbl_name in ("tableAsks", "tableBids", "tableTrades"):
            tbl = getattr(self, tbl_name, None)
            if tbl is not None:
                tbl.setShowGrid(False)

        # 색상 브러시
        self.color_black = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        self.color_red_text = QtGui.QBrush(QtGui.QColor(255, 0, 0))
        self.color_blue_text = QtGui.QBrush(QtGui.QColor(0, 0, 255))
        self.color_yellow = QtGui.QBrush(QtGui.QColor(255, 255, 0))

        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(7)

        # 15행 셀/진행바 초기화
        self.ask_items: List = []
        self.bid_items: List = []
        self.trade_items: List = []
        self.trade_history: List = []
        self.ask_pbars: List = []
        self.bid_pbars: List = []
        self.prev_asks: List[float] = [0.0] * 15
        self.prev_bids: List[float] = [0.0] * 15

        asks_tbl = getattr(self, "tableAsks", None)
        bids_tbl = getattr(self, "tableBids", None)
        trades_tbl = getattr(self, "tableTrades", None)

        for i in range(15):
            self.ask_items.append([QTableWidgetItem(), None, QTableWidgetItem(), QTableWidgetItem()])
            for j in (0, 2, 3):
                self.ask_items[i][j].setFont(font)
                self.ask_items[i][j].setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            if asks_tbl is not None:
                asks_tbl.setItem(i, 0, self.ask_items[i][0])
                asks_tbl.setItem(i, 2, self.ask_items[i][2])
                asks_tbl.setItem(i, 3, self.ask_items[i][3])

            pbar_ask = QProgressBar()
            pbar_ask.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            pbar_ask.setMinimum(0)
            pbar_ask.setMaximum(100)
            pbar_ask.setTextVisible(True)
            pbar_ask.setInvertedAppearance(True)
            pbar_ask.setStyleSheet(
                "QProgressBar {background-color: #CCE5FF; border: none; color: black;"
                " text-align: right; font-size: 7pt;} "
                "QProgressBar::chunk {background-color: #99CCFF;}"
            )
            if asks_tbl is not None:
                asks_tbl.setCellWidget(i, 1, pbar_ask)
            self.ask_pbars.append(pbar_ask)

            self.bid_items.append([QTableWidgetItem(), None, QTableWidgetItem(), QTableWidgetItem()])
            for j in (0, 2, 3):
                self.bid_items[i][j].setFont(font)
                self.bid_items[i][j].setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            if bids_tbl is not None:
                bids_tbl.setItem(i, 0, self.bid_items[i][0])
                bids_tbl.setItem(i, 2, self.bid_items[i][2])
                bids_tbl.setItem(i, 3, self.bid_items[i][3])

            pbar_bid = QProgressBar()
            pbar_bid.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            pbar_bid.setMinimum(0)
            pbar_bid.setMaximum(100)
            pbar_bid.setTextVisible(True)
            pbar_bid.setInvertedAppearance(False)
            pbar_bid.setStyleSheet(
                "QProgressBar {background-color: #FFCFCF; border: none; color: black;"
                " text-align: right; font-size: 7pt;} "
                "QProgressBar::chunk {background-color: #FF9999;}"
            )
            if bids_tbl is not None:
                bids_tbl.setCellWidget(i, 1, pbar_bid)
            self.bid_pbars.append(pbar_bid)

        for i in range(15):
            self.trade_items.append([QTableWidgetItem(), QTableWidgetItem()])
            for j in range(2):
                self.trade_items[i][j].setFont(font)
                self.trade_items[i][j].setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            if trades_tbl is not None:
                trades_tbl.setItem(i, 0, self.trade_items[i][0])
                trades_tbl.setItem(i, 1, self.trade_items[i][1])

        # 시그널 연결
        if bids_tbl is not None:
            bids_tbl.cellClicked.connect(self.setBidsprice)
        if asks_tbl is not None:
            asks_tbl.cellClicked.connect(self.setAsksprice)

        cb = getattr(self, "comboBox_group_view", None)
        if cb is not None:
            cb.currentIndexChanged.connect(self.update_group_view)

        pb_toggle = getattr(self, "pushButton_toggle_quantity", None)
        if pb_toggle is not None:
            pb_toggle.clicked.connect(self.toggle_quantity)

        self.quantity_toggle = True
        if pb_toggle is not None:
            pb_toggle.setText("총액")

        self.current_ticker = ticker

        # 호가 깊이 차트 (matplotlib 이용 가능 시)
        self.depth_canvas: Optional[Any] = None
        if _HAS_MPL and DepthCanvas is not None:
            layout_depth = getattr(self, "layout_market_depth_chart", None)
            if layout_depth is not None and layout_depth.count() == 0:
                self.depth_canvas = DepthCanvas(self)
                self.depth_canvas.setStyleSheet("background-color: transparent;")
                layout_depth.addWidget(self.depth_canvas)

        self._last_depth_draw_ts = 0.0
        self._last_dbg_ts = 0.0

        # 워커 시작
        self.ow = OrderbookWorker(ticker)
        self.ow.dataSent.connect(self.updateData)
        self._ensure_orderbook_subscription(ticker)
        self.ow.start()

        self.trade: Optional[Any] = None

    # ──────────────────────────────────────── 내부 유틸 ──

    def _ensure_orderbook_subscription(self, ticker: str) -> None:
        try:
            if static is not None and hasattr(static, "chart") and static.chart:
                if hasattr(static.chart, "set_orderbook_symbols"):
                    static.chart.set_orderbook_symbols([ticker])
        except Exception:
            if getattr(static, "DEBUG_MODE", False) if static else False:
                log.exception("[OrderbookWidget] Failed to ensure orderbook subscription")

    def _color_by_sign(self, x: float) -> str:
        if x > 0:
            return "#FF0000"
        if x < 0:
            return "#0000FF"
        return "#000000"

    def format_price(self, price: float, coin: Optional[Any] = None) -> str:
        if price is None or price == 0:
            return ""
        decimal_places = 6
        if coin is not None:
            try:
                data = coin.get_orderbook_units()
                if data and len(data) >= 2:
                    tick_sizes = []
                    for i in range(len(data) - 1):
                        a, b = data[i], data[i + 1]
                        if isinstance(a, dict) and isinstance(b, dict) and a.get("bp") != b.get("bp"):
                            try:
                                tick_sizes.append(abs(a["bp"] - b["bp"]))
                            except Exception:
                                pass
                    if tick_sizes:
                        tick_size = min(tick_sizes)
                        if tick_size > 0:
                            decimal_places = max(0, int(-math.log10(tick_size)))
            except Exception:
                pass
        formatted = "{:,.{}f}".format(price, decimal_places)
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted

    # ──────────────────────────────────────── 호가 클릭 → Trade ──

    def setTrade(self, trade: Any) -> None:
        """거래 위젯 설정 — 호가 클릭 시 가격 자동 입력."""
        self.trade = trade

    def setAsksprice(self) -> None:
        if not self.trade:
            return
        asks_tbl = getattr(self, "tableAsks", None)
        if asks_tbl is None:
            return
        row = asks_tbl.currentIndex().row()
        if row >= 0:
            item = asks_tbl.item(row, 2)
            if item and item.text():
                try:
                    self.trade.set_current_price(float(item.text().replace(",", "")))
                except Exception:
                    pass

    def setBidsprice(self) -> None:
        if not self.trade:
            return
        bids_tbl = getattr(self, "tableBids", None)
        if bids_tbl is None:
            return
        row = bids_tbl.currentIndex().row()
        if row >= 0:
            item = bids_tbl.item(row, 2)
            if item and item.text():
                try:
                    self.trade.set_current_price(float(item.text().replace(",", "")))
                except Exception:
                    pass

    # ──────────────────────────────────────── 토글 / 그룹 ──

    def toggle_quantity(self) -> None:
        self.quantity_toggle = not self.quantity_toggle
        pb_toggle = getattr(self, "pushButton_toggle_quantity", None)
        trades_tbl = getattr(self, "tableTrades", None)
        if pb_toggle is not None:
            pb_toggle.setText("총액" if self.quantity_toggle else "수량")
        if trades_tbl is not None:
            hdr_item = trades_tbl.horizontalHeaderItem(1)
            if hdr_item is not None:
                hdr_item.setText("체결액" if self.quantity_toggle else "체결량")
        # 현재 coin 재렌더
        if static is not None:
            coins = getattr(getattr(static, "chart", None), "coins", None)
            if coins:
                coin = coins.get(self.ow.ticker)
                if coin:
                    self.updateData(coin)

    def update_group_view(self) -> None:
        if static is not None:
            coins = getattr(getattr(static, "chart", None), "coins", None)
            if coins:
                coin = coins.get(self.ow.ticker)
                if coin:
                    self.updateData(coin)

    # ──────────────────────────────────────── 심볼 변경 ──

    def update_symbol(self, source: str, symbol: str) -> None:
        """심볼 업데이트 (외부 호출 및 UIStateManager 연동용)."""
        self._on_symbol_changed(source, symbol)

    def set_ticker(self, ticker: str) -> None:
        self._ensure_orderbook_subscription(ticker)
        self.ow.ticker = ticker
        self.current_ticker = ticker
        self.current_symbol = ticker
        self.trade_history = []
        if static is not None:
            coins = getattr(getattr(static, "chart", None), "coins", None)
            if coins:
                coin = coins.get(ticker)
                if coin:
                    self.updateData(coin)

    def _on_symbol_changed(self, exchange: str, symbol: str) -> None:
        if exchange != "upbit":
            return
        if self.current_symbol and self.current_symbol != symbol:
            self._unsubscribe_orderbook(self.current_symbol)
        self.current_symbol = symbol
        self._subscribe_orderbook(symbol)
        self.set_ticker(symbol)

    def _subscribe_orderbook(self, symbol: str) -> None:
        try:
            if static is not None and hasattr(static, "chart") and static.chart:
                if hasattr(static.chart, "set_orderbook_symbols"):
                    static.chart.set_orderbook_symbols([symbol])
        except Exception:
            if getattr(static, "DEBUG_MODE", False) if static else False:
                log.exception("[OrderbookWidget] _subscribe_orderbook failed")

    def _unsubscribe_orderbook(self, symbol: str) -> None:
        pass  # Overwrite handled by set_orderbook_symbols

    # ──────────────────────────────────────── 데이터 업데이트 ──

    def group_orders(self, orders: List[Dict], unit: int, is_ask: bool) -> List[Dict]:
        grouped: Dict[float, Dict] = {}
        for order in orders:
            price = order["price"]
            size = order["size"]
            if is_ask:
                grouped_price = ((price - 1) // unit) * unit + unit
            else:
                grouped_price = (price // unit) * unit
            if grouped_price not in grouped:
                grouped[grouped_price] = {"price": grouped_price, "size": 0.0}
            grouped[grouped_price]["size"] += size
        return sorted(grouped.values(), key=lambda x: x["price"], reverse=True)

    @throttle(500)
    def updateData(self, payload: Any) -> None:
        """
        Orderbook 데이터 UI 업데이트 (throttled).

        payload 는 Coin 객체 또는 REST API dict 두 가지를 지원합니다.
        """
        try:
            # REST API fallback (aiopyupbit dict)
            if isinstance(payload, dict):
                self._update_from_rest(payload)
                return

            # Coin 객체 경로
            coin = payload
            if not coin:
                return

            now = time.time()
            if getattr(static, "DEBUG_MODE", False) if static else False:
                if now - self._last_dbg_ts > 5.0:
                    self._last_dbg_ts = now
                    obu_len = len(coin.get_orderbook_units() or [])
                    log.debug(
                        f"[OrderbookWidget] coin={coin.get_code()} worker_ticker={self.ow.ticker} "
                        f"obu_len={obu_len} tas={coin.orderbook.get('tas')} tbs={coin.orderbook.get('tbs')}"
                    )

            if self.current_ticker != coin.get_code():
                self.trade_history = []
                self.current_ticker = coin.get_code()

            data = coin.get_orderbook_units()[0:15]
            if not data:
                return
            len_data = min(15, len(data))

            current_price = coin.get_trade_price() or 0
            prev_close = coin.get_prev_closing_price() or 0

            # 거래강도
            acc_bid_vol = coin.get_acc_bid_volume() or 0
            acc_ask_vol = coin.get_acc_ask_volume() or 0
            strength = (acc_bid_vol / acc_ask_vol * 100) if acc_ask_vol > 0 else 0
            lbl_strength = getattr(self, "userdata_strength", None)
            if lbl_strength is not None:
                lbl_strength.setText(f"{strength:.2f}%")

            cb = getattr(self, "comboBox_group_view", None)
            group = cb.currentText() if cb is not None else "기본값"
            if group not in ("모아보기", "기본값"):
                group_unit = int(group)
                asks_raw = [{"price": d["ap"], "size": d["as"]} for d in data]
                bids_raw = [{"price": d["bp"], "size": d["bs"]} for d in data]
                grouped_asks = self.group_orders(asks_raw, unit=group_unit, is_ask=True)
                grouped_bids = self.group_orders(bids_raw, unit=group_unit, is_ask=False)
                # 그룹 후 키를 ap/as, bp/bs 로 정규화
                grouped_asks = [{"ap": d["price"], "as": d["size"]} for d in grouped_asks]
                grouped_bids = [{"bp": d["price"], "bs": d["size"]} for d in grouped_bids]
                len_data = min(15, min(len(grouped_asks), len(grouped_bids)))
            else:
                grouped_asks = [{"ap": d["ap"], "as": d["as"]} for d in data[::-1]]
                grouped_bids = [{"bp": d["bp"], "bs": d["bs"]} for d in data]

            # 합계
            lbl_ask = getattr(self, "userdata_total_ask", None)
            lbl_bid = getattr(self, "userdata_total_bid", None)
            if self.quantity_toggle:
                asks_total = sum(d["ap"] * d["as"] for d in grouped_asks[:len_data])
                bids_total = sum(d["bp"] * d["bs"] for d in grouped_bids[:len_data])
                if lbl_ask is not None:
                    lbl_ask.setText(f"{asks_total:,.0f}")
                if lbl_bid is not None:
                    lbl_bid.setText(f"{bids_total:,.0f}")
            else:
                asks_size = sum(d["as"] for d in grouped_asks[:len_data])
                bids_size = sum(d["bs"] for d in grouped_bids[:len_data])
                if lbl_ask is not None:
                    lbl_ask.setText(f"{asks_size:,.3f}")
                if lbl_bid is not None:
                    lbl_bid.setText(f"{bids_size:,.3f}")

            if len_data > 0:
                if self.quantity_toggle:
                    max_ask = max(d["ap"] * d["as"] for d in grouped_asks[:len_data]) or 1
                    max_bid = max(d["bp"] * d["bs"] for d in grouped_bids[:len_data]) or 1
                else:
                    max_ask = max(d["as"] for d in grouped_asks[:len_data]) or 1
                    max_bid = max(d["bs"] for d in grouped_bids[:len_data]) or 1
            else:
                max_ask = max_bid = 1

            asks_tbl = getattr(self, "tableAsks", None)
            bids_tbl = getattr(self, "tableBids", None)

            if asks_tbl is not None:
                asks_tbl.setUpdatesEnabled(False)
            if bids_tbl is not None:
                bids_tbl.setUpdatesEnabled(False)

            # ASKS
            for i in range(15):
                if i < len_data:
                    ask_data = grouped_asks[i]
                    ask_price = ask_data["ap"]
                    ask_size = ask_data["as"]
                    ask_change = ask_size - self.prev_asks[i]
                    self.prev_asks[i] = ask_size
                    ask_rate = ((ask_price - prev_close) / prev_close * 100) if prev_close != 0 else 0
                    ask_value = ask_price * ask_size if self.quantity_toggle else ask_size
                    ask_change_disp = ask_change * ask_price if self.quantity_toggle else ask_change

                    if ask_change != 0:
                        self.ask_items[i][0].setText(
                            f"{ask_change_disp:+,.0f}" if self.quantity_toggle else f"{ask_change_disp:+,.3f}"
                        )
                        self.ask_items[i][0].setForeground(
                            self.color_red_text if ask_change > 0 else self.color_blue_text
                        )
                        QTimer.singleShot(
                            5000,
                            lambda item=self.ask_items[i][0]: item.setText("")
                        )
                    else:
                        self.ask_items[i][0].setText("")
                        self.ask_items[i][0].setForeground(self.color_black)

                    self.ask_pbars[i].setValue(int((ask_value / max_ask) * 100) if max_ask > 0 else 0)
                    self.ask_pbars[i].setFormat(
                        f"{ask_value:,.0f}" if self.quantity_toggle else f"{ask_value:,.3f}"
                    )

                    self.ask_items[i][2].setText(self.format_price(ask_price, coin))
                    self.ask_items[i][2].setForeground(
                        self.color_red_text if ask_rate > 0
                        else self.color_blue_text if ask_rate < 0
                        else self.color_black
                    )
                    self.ask_items[i][3].setText(f"{ask_rate:+.2f}%")
                    self.ask_items[i][3].setForeground(
                        self.color_red_text if ask_rate > 0
                        else self.color_blue_text if ask_rate < 0
                        else self.color_black
                    )

                    bg = QtGui.QColor(255, 255, 0) if ask_price == current_price else QtGui.QColor(204, 229, 255, 255)
                    for j in (0, 2, 3):
                        self.ask_items[i][j].setBackground(bg)
                else:
                    for j in (0, 2, 3):
                        self.ask_items[i][j].setText("")
                        self.ask_items[i][j].setBackground(QtGui.QColor(255, 255, 255, 0))
                        self.ask_items[i][j].setForeground(self.color_black)
                    self.ask_pbars[i].setValue(0)
                    self.ask_pbars[i].setFormat("")

            # BIDS
            for i in range(15):
                if i < len_data:
                    bid_data = grouped_bids[i]
                    bid_price = bid_data["bp"]
                    bid_size = bid_data["bs"]
                    bid_change = bid_size - self.prev_bids[i]
                    self.prev_bids[i] = bid_size
                    bid_rate = ((bid_price - prev_close) / prev_close * 100) if prev_close != 0 else 0
                    bid_value = bid_price * bid_size if self.quantity_toggle else bid_size
                    bid_change_disp = bid_change * bid_price if self.quantity_toggle else bid_change

                    if bid_change != 0:
                        self.bid_items[i][0].setText(
                            f"{bid_change_disp:+,.0f}" if self.quantity_toggle else f"{bid_change_disp:+,.3f}"
                        )
                        self.bid_items[i][0].setForeground(
                            self.color_red_text if bid_change > 0 else self.color_blue_text
                        )
                        QTimer.singleShot(
                            5000,
                            lambda item=self.bid_items[i][0]: item.setText("")
                        )
                    else:
                        self.bid_items[i][0].setText("")
                        self.bid_items[i][0].setForeground(self.color_black)

                    self.bid_pbars[i].setValue(int((bid_value / max_bid) * 100) if max_bid > 0 else 0)
                    self.bid_pbars[i].setFormat(
                        f"{bid_value:,.0f}" if self.quantity_toggle else f"{bid_value:,.3f}"
                    )

                    self.bid_items[i][2].setText(self.format_price(bid_price, coin))
                    self.bid_items[i][2].setForeground(
                        self.color_red_text if bid_rate > 0
                        else self.color_blue_text if bid_rate < 0
                        else self.color_black
                    )
                    self.bid_items[i][3].setText(f"{bid_rate:+.2f}%")
                    self.bid_items[i][3].setForeground(
                        self.color_red_text if bid_rate > 0
                        else self.color_blue_text if bid_rate < 0
                        else self.color_black
                    )

                    bg = QtGui.QColor(255, 255, 0) if bid_price == current_price else QtGui.QColor(255, 207, 207, 255)
                    for j in (0, 2, 3):
                        self.bid_items[i][j].setBackground(bg)
                else:
                    for j in (0, 2, 3):
                        self.bid_items[i][j].setText("")
                        self.bid_items[i][j].setBackground(QtGui.QColor(255, 255, 255, 0))
                        self.bid_items[i][j].setForeground(self.color_black)
                    self.bid_pbars[i].setValue(0)
                    self.bid_pbars[i].setFormat("")

            if asks_tbl is not None:
                asks_tbl.setUpdatesEnabled(True)
            if bids_tbl is not None:
                bids_tbl.setUpdatesEnabled(True)

            # 체결 내역
            trade_price_str = self.format_price(coin.get_trade_price() or 0, coin)
            trade_volume_str = f"{coin.get_trade_volume():,.3f}"
            ask_bid = coin.get_ask_bid()
            new_trade = [trade_price_str, trade_volume_str, ask_bid]

            if not self.trade_history or self.trade_history[0][0:2] != [trade_price_str, trade_volume_str]:
                self.trade_history.insert(0, new_trade)
                if len(self.trade_history) > 15:
                    self.trade_history.pop()

            trades_tbl = getattr(self, "tableTrades", None)
            if trades_tbl is not None:
                trades_tbl.setUpdatesEnabled(False)
                for i in range(15):
                    if i < len(self.trade_history):
                        price_t = self.trade_history[i][0]
                        volume_t = self.trade_history[i][1]
                        ab = self.trade_history[i][2]
                        self.trade_items[i][0].setText(price_t)
                        try:
                            vol_num = float(volume_t.replace(",", "")) if volume_t else 0.0
                            price_num = float(price_t.replace(",", "")) if price_t else 0.0
                        except ValueError:
                            vol_num = price_num = 0.0
                        if self.quantity_toggle:
                            self.trade_items[i][1].setText(f"{price_num * vol_num:,.0f}")
                        else:
                            self.trade_items[i][1].setText(f"{vol_num:,.3f}")
                        rate = (price_num - prev_close) / prev_close * 100 if prev_close != 0 else 0
                        color_price = (
                            self.color_red_text if rate > 0
                            else self.color_blue_text if rate < 0
                            else self.color_black
                        )
                        color_vol = self.color_red_text if ab == "BID" else self.color_blue_text
                        self.trade_items[i][0].setForeground(color_price)
                        self.trade_items[i][1].setForeground(color_vol)
                    else:
                        for j in range(2):
                            self.trade_items[i][j].setText("")
                            self.trade_items[i][j].setForeground(self.color_black)
                trades_tbl.setUpdatesEnabled(True)

            # 호가 깊이 차트
            if self.depth_canvas is not None and _HAS_NUMPY and len_data > 0:
                bid_prices_h2l = [grouped_bids[i]["bp"] for i in range(len_data)]
                bid_sizes_h2l = [grouped_bids[i]["bs"] for i in range(len_data)]
                cum_bids_h2l = np.cumsum(bid_sizes_h2l)
                bid_prices_l2h = bid_prices_h2l[::-1]
                cum_bids_l2h = cum_bids_h2l[::-1]
                ask_prices_l2h = [grouped_asks[len_data - 1 - i]["ap"] for i in range(len_data)]
                ask_sizes_l2h = [grouped_asks[len_data - 1 - i]["as"] for i in range(len_data)]
                cum_asks_l2h = np.cumsum(ask_sizes_l2h)

                ax = self.depth_canvas.ax
                ax.clear()
                ax.patch.set_facecolor("white")
                ax.tick_params(axis="x", colors="black", labelsize=6)
                ax.tick_params(axis="y", colors="black", labelsize=6)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.spines["bottom"].set_color("black")
                ax.spines["left"].set_color("black")
                ax.grid(True, color="black", alpha=0.5, linestyle="--")
                ax.fill_between(bid_prices_l2h, 0, cum_bids_l2h, step="post", color="#FF0000", alpha=1.0)
                ax.fill_between(ask_prices_l2h, 0, cum_asks_l2h, step="post", color="#0000FF", alpha=1.0)
                all_prices = bid_prices_l2h + ask_prices_l2h
                if all_prices:
                    ax.set_xlim(min(all_prices), max(all_prices))
                    ax.set_ylim(0, max(float(max(cum_bids_l2h)), float(max(cum_asks_l2h))) * 1.1)

                now2 = time.time()
                if now2 - self._last_depth_draw_ts >= 0.5:
                    self._last_depth_draw_ts = now2
                    self.depth_canvas.draw_idle()

            # 정보 패널
            try:
                h52 = coin.get_highest_52_week_price() or 0
                l52 = coin.get_lowest_52_week_price() or 0
                hp = coin.get_high_price() or 0
                lp = coin.get_low_price() or 0

                for attr, val in [
                    ("userdata4_6", self.format_price(h52, coin)),
                    ("userdata4_8", coin.get_highest_52_week_date()),
                    ("userdata4_7", self.format_price(l52, coin)),
                    ("userdata4_9", coin.get_lowest_52_week_date()),
                    ("userdata4_10", self.format_price(prev_close, coin)),
                    ("userdata4_11", self.format_price(hp, coin)),
                    ("userdata4_14", self.format_price(lp, coin)),
                ]:
                    w = getattr(self, attr, None)
                    if w is not None:
                        w.setText(val)

                high_rate = ((hp - prev_close) / prev_close * 100) if prev_close else 0
                low_rate = ((lp - prev_close) / prev_close * 100) if prev_close else 0
                h52_rate = ((h52 - prev_close) / prev_close * 100) if prev_close else 0
                l52_rate = ((l52 - prev_close) / prev_close * 100) if prev_close else 0

                for attr, val in [
                    ("userdata4_12", f"{high_rate:+.2f}"),
                    ("userdata4_13", f"{low_rate:+.2f}"),
                ]:
                    w = getattr(self, attr, None)
                    if w is not None:
                        w.setText(val)

                for attr, color_fn in [
                    ("userdata4_11", lambda: self._color_by_sign(high_rate)),
                    ("userdata4_12", lambda: self._color_by_sign(high_rate)),
                    ("userdata4_14", lambda: self._color_by_sign(low_rate)),
                    ("userdata4_13", lambda: self._color_by_sign(low_rate)),
                    ("userdata4_6", lambda: self._color_by_sign(h52_rate)),
                    ("userdata4_7", lambda: self._color_by_sign(l52_rate)),
                ]:
                    w = getattr(self, attr, None)
                    if w is not None:
                        w.setStyleSheet(f"color: {color_fn()};")

                coin_name = coin.get_code().split("-")[1]
                w_vol = getattr(self, "userdata4_3", None)
                if w_vol is not None:
                    w_vol.setText(f"{coin.get_acc_trade_volume_24h():,.3f} ({coin_name})")
                w_price = getattr(self, "userdata4_5", None)
                if w_price is not None:
                    w_price.setText(f"{coin.get_acc_trade_price_24h() / 1_000_000:,.0f}백만")
            except Exception:
                pass

        except Exception:
            log.exception("[OrderbookWidget] updateData exception")

    def _update_from_rest(self, payload: Dict) -> None:
        """REST API dict로 기본 호가창 업데이트 (Coin 객체 없을 때 fallback)."""
        try:
            orderbook = payload.get("data")
            if not orderbook:
                return
            if isinstance(orderbook, list) and orderbook:
                orderbook = orderbook[0]
            if not isinstance(orderbook, dict):
                return
            units: List[Dict] = orderbook.get("orderbook_units", [])
            asks_tbl = getattr(self, "tableAsks", None)
            bids_tbl = getattr(self, "tableBids", None)
            if Qt is None:
                return

            if asks_tbl is not None:
                ask_units = list(reversed(units[:15]))
                len_data = min(15, len(ask_units))
                for i in range(15):
                    if i < len_data:
                        u = ask_units[i]
                        price = u.get("ask_price", 0)
                        size = u.get("ask_size", 0)
                        val = price * size if self.quantity_toggle else size
                        max_val = max((units[j].get("ask_price", 0) * units[j].get("ask_size", 0)
                                       if self.quantity_toggle else units[j].get("ask_size", 0))
                                      for j in range(min(len(units), 15))) or 1
                        self.ask_items[i][2].setText(f"{price:,.0f}")
                        self.ask_pbars[i].setValue(int((val / max_val) * 100))
                        self.ask_pbars[i].setFormat(
                            f"{val:,.0f}" if self.quantity_toggle else f"{val:,.4f}"
                        )
                    else:
                        self.ask_items[i][2].setText("")
                        self.ask_pbars[i].setValue(0)
                        self.ask_pbars[i].setFormat("")

            if bids_tbl is not None:
                bid_units = units[:15]
                len_data = min(15, len(bid_units))
                for i in range(15):
                    if i < len_data:
                        u = bid_units[i]
                        price = u.get("bid_price", 0)
                        size = u.get("bid_size", 0)
                        val = price * size if self.quantity_toggle else size
                        max_val = max((units[j].get("bid_price", 0) * units[j].get("bid_size", 0)
                                       if self.quantity_toggle else units[j].get("bid_size", 0))
                                      for j in range(min(len(units), 15))) or 1
                        self.bid_items[i][2].setText(f"{price:,.0f}")
                        self.bid_pbars[i].setValue(int((val / max_val) * 100))
                        self.bid_pbars[i].setFormat(
                            f"{val:,.0f}" if self.quantity_toggle else f"{val:,.4f}"
                        )
                    else:
                        self.bid_items[i][2].setText("")
                        self.bid_pbars[i].setValue(0)
                        self.bid_pbars[i].setFormat("")

            total_ask = orderbook.get("total_ask_size", 0)
            total_bid = orderbook.get("total_bid_size", 0)
            lbl_ask = getattr(self, "userdata_total_ask", None)
            lbl_bid = getattr(self, "userdata_total_bid", None)
            if lbl_ask is not None:
                lbl_ask.setText(f"{total_ask:.2f}")
            if lbl_bid is not None:
                lbl_bid.setText(f"{total_bid:.2f}")
        except Exception:
            pass

    def update_data(self, data: Any) -> None:
        """외부에서 호가 데이터를 직접 전달할 때 사용 (레거시 호환)."""
        self.updateData(data)

    def add_trade(self, trade: Dict) -> None:
        """체결 내역 한 건 추가 (tableTrades 최상단 삽입, 레거시 호환)."""
        try:
            from datetime import datetime as _dt
            tbl = getattr(self, "tableTrades", None)
            if tbl is None:
                return
            ts = trade.get("timestamp", 0)
            try:
                time_str = _dt.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
            except Exception:
                time_str = "--"
            ask_bid = trade.get("ask_bid", "")
            price = trade.get("trade_price", 0)
            volume = trade.get("trade_volume", 0)
            new_trade = [f"{price:,.0f}", f"{volume:,.4f}", ask_bid]
            if not self.trade_history or self.trade_history[0][0:2] != new_trade[0:2]:
                self.trade_history.insert(0, new_trade)
                if len(self.trade_history) > 15:
                    self.trade_history.pop()
        except Exception:
            pass

    # ──────────────────────────────────────── 종료 ──

    def closeEvent(self, event: Any) -> None:
        try:
            self.ow.close()
            if self.ow.isRunning():
                self.ow.wait(2000)
        except Exception:
            pass
        if _HAS_QT:
            super().closeEvent(event)


__all__ = ["OrderbookWidget", "OrderbookWorker"]
