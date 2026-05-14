#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
매수/매도 주문 입력 및 주문(미체결/체결) 정보 표시를 담당하는 위젯이다.

[Responsibilities]
- trade.ui 로드
- 매수/매도 탭(지정가/시장가/예약) 전환 및 입력값 계산
- 주문/취소 요청을 Upbit API(static.account.upbit)로 전달
- TradeWorker로 미체결/체결 주문 정보를 주기적으로 갱신

[UI Binding]
- trade.ui (src/10_trade/orders/ui/trade.ui)

CHANGELOG:
- 2026-03-17 | Copilot | backup/trade/widget_trade.py 복원 (import static → 조건부 import)
"""
from __future__ import annotations

import asyncio as aio
import logging
import math
import os
import traceback
from typing import Any, List, Optional

try:
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import (
        QDialog, QHBoxLayout, QHeaderView, QPushButton, QSizePolicy,
        QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
    )
    from PyQt5 import uic
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QWidget = object  # type: ignore[misc,assignment]
    QThread = object  # type: ignore[misc,assignment]
    QDialog = object  # type: ignore[misc,assignment]
    uic = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional static globals – resolved lazily to avoid hard import failures
# ---------------------------------------------------------------------------

def _get_static() -> Optional[Any]:
    """Return the legacy ``static`` module if available, else None."""
    try:
        import static as _s  # type: ignore[import]
        return _s
    except Exception:
        pass
    try:
        from app import static as _s  # type: ignore[import]
        return _s
    except Exception:
        return None


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


# ---------------------------------------------------------------------------
# TradeWorker
# ---------------------------------------------------------------------------

class TradeWorker(QThread):  # type: ignore[misc]
    """미체결/체결 주문 정보를 비동기적으로 폴링하는 워커 스레드."""

    if _HAS_QT:
        dataSent = pyqtSignal(object, int)
    else:
        dataSent = None  # type: ignore[assignment]

    def __init__(self, code: str = "KRW-BTC") -> None:
        if _HAS_QT:
            super().__init__()
        self.alive = False
        self.code = code

    def run(self) -> None:
        """비동기 주문 폴링 - UI 블로킹 방지."""
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_poll())
        finally:
            loop.close()

    async def _async_poll(self) -> None:
        while self.alive:
            await aio.sleep(0.5)
            try:
                s = _get_static()
                if s is None:
                    continue
                upbit = getattr(getattr(s, "account", None), "upbit", None)
                if upbit is None:
                    continue
                wait = await upbit.get_order(ticker_or_uuid=self.code)
                done = await upbit.get_order(ticker_or_uuid=self.code, state="done")
                if self.dataSent is not None:
                    self.dataSent.emit(wait, 1)
                    self.dataSent.emit(done, 2)
            except Exception as exc:
                log.warning("Trade worker poll error for %s: %s", self.code, exc)

    def close(self) -> None:
        self.alive = False
        if _HAS_QT:
            self.terminate()


# ---------------------------------------------------------------------------
# MessageDialog
# ---------------------------------------------------------------------------

class MessageDialog(QDialog):  # type: ignore[misc]
    """Non-modal, readable message dialog."""

    def __init__(self, parent: Optional[Any], title: str, message: str,
                 width: int = 700, height: int = 340) -> None:
        if _HAS_QT:
            super().__init__(parent=parent)
        try:
            self.setWindowTitle(title or "")
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.setWindowModality(Qt.NonModal)
            try:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            except Exception:
                pass

            layout = QVBoxLayout(self)
            txt = QTextEdit(self)
            txt.setReadOnly(True)
            txt.setPlainText(str(message))
            txt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(txt)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            ok_btn = QPushButton("확인", self)
            ok_btn.clicked.connect(self.close)
            ok_btn.setDefault(True)
            btn_row.addWidget(ok_btn)
            layout.addLayout(btn_row)

            self.resize(width, height)
        except Exception:
            traceback.print_exc()


# ---------------------------------------------------------------------------
# TradeWidget
# ---------------------------------------------------------------------------

class TradeWidget(QWidget):  # type: ignore[misc]
    """매수/매도 주문 입력 위젯."""

    def __init__(self, parent: Optional[Any] = None) -> None:
        if _HAS_QT:
            super().__init__(parent=parent)

        self.coin: str = "KRW-BTC"
        self.items1: List[Any] = []
        self.items2: List[Any] = []
        self._active_dialogs: List[Any] = []
        self._worker: Optional[TradeWorker] = None

        if not _HAS_QT or uic is None:
            return

        ui_path = _ui_file_path("trade.ui")
        if os.path.exists(ui_path):
            try:
                uic.loadUi(ui_path, self)
            except Exception:
                log.exception("[TradeWidget] UI 로드 실패")
                return
        else:
            log.warning("[TradeWidget] trade.ui 파일 없음: %s", ui_path)
            return

        # --- 주문 정보 테이블 초기화 ---
        try:
            self.info_table_1.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.info_table_2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.info_table_1.setShowGrid(False)
            self.info_table_2.setShowGrid(False)
        except Exception:
            pass

        # --- 워커 시작 ---
        try:
            self._worker = TradeWorker(self.coin)
            self._worker.dataSent.connect(self.set_execute_info)
        except Exception:
            log.warning("[TradeWidget] TradeWorker 초기화 실패")

        # --- 데모 모드 확인 ---
        s = _get_static()
        cfg = getattr(s, "config", None) if s else None
        access_key = getattr(cfg, "upbit_access_key", None) if cfg else None
        self.is_demo: bool = access_key in (None, "dummy_access", "INPUT_YOUR_UPBIT_ACCESS_KEY")

        # --- 라디오/버튼 연결 ---
        self._connect_signals()

    # ──────────────────────────────────────────── 신호 연결 ──

    def _connect_signals(self) -> None:
        """UI 위젯 신호 연결."""
        try:
            self.buy_designation_price.setChecked(True)
            self.info_not_execution.setChecked(True)

            self.buy_designation_price.clicked.connect(self.clicked_buy_designation_price)
            self.buy_market_price.clicked.connect(self.clicked_buy_market_price)
            self.buy_reservation_price.clicked.connect(self.clicked_buy_reservation_price)

            self.sell_designation_price.setChecked(True)
            self.sell_designation_price.clicked.connect(self.clicked_sell_designation_price)
            self.sell_market_price.clicked.connect(self.clicked_sell_market_price)
            self.sell_reservation_price.clicked.connect(self.clicked_sell_reservation_price)

            for btn in (self.buy_reset_1, self.buy_reset_2, self.buy_reset_3,
                        self.sell_reset_1, self.sell_reset_2, self.sell_reset_3):
                btn.clicked.connect(self.clicked_reset)

            for btn, ratio in [
                (self.buy_ten_1, 0.1), (self.buy_twenty_fifth_1, 0.25),
                (self.buy_fifty_1, 0.5), (self.buy_hundred_1, 1.0),
                (self.buy_ten_2, 0.1), (self.buy_twenty_fifth_2, 0.25),
                (self.buy_fifty_2, 0.5), (self.buy_hundred_2, 1.0),
                (self.buy_ten_3, 0.1), (self.buy_twenty_fifth_3, 0.25),
                (self.buy_fifty_3, 0.5), (self.buy_hundred_3, 1.0),
                (self.sell_ten_1, 0.1), (self.sell_twenty_fifth_1, 0.25),
                (self.sell_fifty_1, 0.5), (self.sell_hundred_1, 1.0),
                (self.sell_ten_2, 0.1), (self.sell_twenty_fifth_2, 0.25),
                (self.sell_fifty_2, 0.5), (self.sell_hundred_2, 1.0),
                (self.sell_ten_3, 0.1), (self.sell_twenty_fifth_3, 0.25),
                (self.sell_fifty_3, 0.5), (self.sell_hundred_3, 1.0),
            ]:
                btn.clicked.connect(lambda _=None, r=ratio: self.clicked_vol(r))

            self.buy_buy_btn_1.clicked.connect(lambda: self.clicked_buy_button(1))
            self.buy_buy_btn_2.clicked.connect(lambda: self.clicked_buy_button(2))
            self.buy_buy_btn_3.clicked.connect(lambda: self.clicked_buy_button(3))

            self.sell_sell_btn_1.clicked.connect(lambda: self.clicked_sell_button(1))
            self.sell_sell_btn_2.clicked.connect(lambda: self.clicked_sell_button(2))
            self.sell_sell_btn_3.clicked.connect(lambda: self.clicked_sell_button(3))

            self.buy_price_1.setGroupSeparatorShown(True)
            self.buy_price_1.valueChanged.connect(self.changed_price)
            self.buy_volume_1.valueChanged.connect(self.changed_volume)
            self.buy_total_price_1.valueChanged.connect(self.changed_total)

            self.buy_price_3.valueChanged.connect(self.changed_price)
            self.buy_volume_3.valueChanged.connect(self.changed_volume)
            self.buy_total_price_3.valueChanged.connect(self.changed_total)

            self.sell_price_1.valueChanged.connect(self.changed_price)
            self.sell_volume_1.valueChanged.connect(self.changed_volume)
            self.sell_total_price_1.valueChanged.connect(self.changed_total)

            self.sell_price_3.valueChanged.connect(self.changed_price)
            self.sell_volume_3.valueChanged.connect(self.changed_volume)
            self.sell_total_price_3.valueChanged.connect(self.changed_total)

            self.volume_changed: bool = True
            self.info_not_execution.clicked.connect(lambda: self.clicked_info_radio(0))
            self.info_execution.clicked.connect(lambda: self.clicked_info_radio(1))
            self.cancel_button.clicked.connect(self.clicked_cancel)
        except Exception:
            log.exception("[TradeWidget] 신호 연결 실패")

    # ──────────────────────────────────────────── 탭 전환 ──

    def clicked_buy_designation_price(self) -> None:
        self.buy_stack.setCurrentIndex(0)

    def clicked_buy_market_price(self) -> None:
        self.buy_stack.setCurrentIndex(1)

    def clicked_buy_reservation_price(self) -> None:
        self.buy_stack.setCurrentIndex(2)

    def clicked_sell_designation_price(self) -> None:
        self.sell_stack.setCurrentIndex(0)

    def clicked_sell_market_price(self) -> None:
        self.sell_stack.setCurrentIndex(1)

    def clicked_sell_reservation_price(self) -> None:
        self.sell_stack.setCurrentIndex(2)

    # ──────────────────────────────────────────── 비율 입력 ──

    def clicked_vol(self, ratio: float) -> None:
        s = _get_static()
        account = getattr(s, "account", None) if s else None
        try:
            if self.tabWidget.currentIndex() == 0:
                cash = account.get_total_cash() if account else 0
                fees = getattr(s, "FEES", 0.0005) if s else 0.0005
                total_order_price = cash * ratio
                total_order_price -= math.ceil(total_order_price * fees)
                idx = self.buy_stack.currentIndex()
                if idx == 0:
                    self.buy_total_price_1.setValue(total_order_price)
                elif idx == 1:
                    self.buy_total_price_2.setValue(total_order_price)
                else:
                    self.buy_total_price_3.setValue(total_order_price)
            else:
                self.volume_changed = False
                coin = self.coin.split("-")[1]
                coins = getattr(account, "coins", {}) if account else {}
                if coin in coins:
                    price = self.sell_price_1.value()
                    balance = coins[coin].get("balance", 0)
                    idx = self.sell_stack.currentIndex()
                    volume = balance * ratio
                    if idx == 0:
                        self.sell_total_price_1.setValue(price * volume)
                        self.sell_volume_1.setValue(volume)
                    elif idx == 1:
                        self.sell_total_price_2.setValue(volume)
                    else:
                        self.sell_total_price_3.setValue(price * volume)
                        self.sell_volume_3.setValue(volume)
        except Exception:
            log.exception("[TradeWidget] clicked_vol 오류")

    # ──────────────────────────────────────────── 초기화 ──

    def clicked_reset(self) -> None:
        try:
            if self.tabWidget.currentIndex() == 0:
                idx = self.buy_stack.currentIndex()
                if idx == 0:
                    self.buy_price_1.setValue(0)
                    self.buy_volume_1.setValue(0)
                    self.buy_total_price_1.setValue(0)
                elif idx == 1:
                    self.buy_total_price_2.setValue(0)
                else:
                    self.buy_price_3.setValue(0)
                    self.buy_volume_3.setValue(0)
                    self.buy_total_price_3.setValue(0)
                    self.buy_monitor_price_3.setValue(0)
            else:
                idx = self.sell_stack.currentIndex()
                if idx == 0:
                    self.sell_price_1.setValue(0)
                    self.sell_volume_1.setValue(0)
                    self.sell_total_price_1.setValue(0)
                elif idx == 1:
                    self.sell_total_price_2.setValue(0)
                else:
                    self.sell_price_3.setValue(0)
                    self.sell_volume_3.setValue(0)
                    self.sell_total_price_3.setValue(0)
                    self.sell_monitor_price_3.setValue(0)
        except Exception:
            log.exception("[TradeWidget] clicked_reset 오류")

    # ──────────────────────────────────────────── 매수/매도 버튼 ──

    def clicked_buy_button(self, tab_number: int) -> None:
        try:
            ticker = self.coin
            if self.is_demo:
                log.info("데모 모드: 매수 주문 시뮬레이션 - %s", ticker)
                self.show_messagebox(True, "데모 모드: 매수주문이 시뮬레이션되었습니다.")
                return
            s = _get_static()
            upbit = getattr(getattr(s, "account", None), "upbit", None) if s else None
            if upbit is None:
                self.show_messagebox(False, "Upbit API 연결 없음")
                return
            if tab_number == 1:
                buy_price = self.buy_price_1.value()
                buy_volume = self.buy_volume_1.value()
                ret = aio.run(upbit.buy_limit_order(ticker=ticker, price=buy_price, volume=buy_volume))
            elif tab_number == 2:
                total_buy_price = self.buy_total_price_2.value()
                ret = aio.run(upbit.buy_market_order(ticker=ticker, price=total_buy_price))
            else:
                self.show_messagebox(False, "미구현입니다")
                return
            log.info("%s", ret)
            self.show_messagebox(True, "매수주문이 정상완료되었습니다.")
        except Exception as exc:
            self.show_messagebox(False, str(exc))

    def clicked_sell_button(self, tab_number: int) -> None:
        try:
            ticker = self.coin
            if self.is_demo:
                log.info("데모 모드: 매도 주문 시뮬레이션 - %s", ticker)
                self.show_messagebox(True, "데모 모드: 매도주문이 시뮬레이션되었습니다.")
                return
            s = _get_static()
            upbit = getattr(getattr(s, "account", None), "upbit", None) if s else None
            if upbit is None:
                self.show_messagebox(False, "Upbit API 연결 없음")
                return
            if tab_number == 1:
                sell_price = self.sell_price_1.value()
                sell_volume = self.sell_volume_1.value()
                log.info("%s %s", sell_price, sell_volume)
                ret = aio.run(upbit.sell_limit_order(ticker=ticker, price=sell_price, volume=sell_volume))
            elif tab_number == 2:
                sell_volume = self.sell_total_price_2.value()
                ret = aio.run(upbit.sell_market_order(ticker=ticker, volume=sell_volume))
            else:
                self.show_messagebox(False, "미구현입니다")
                return
            log.info("%s", ret)
            self.show_messagebox(True, "매도주문이 정상완료되었습니다.")
        except Exception as exc:
            self.show_messagebox(False, str(exc))

    # ──────────────────────────────────────────── 주문 취소 ──

    def clicked_info_radio(self, index: int) -> None:
        try:
            self.info_stack.setCurrentIndex(index)
        except Exception:
            pass

    def clicked_cancel(self) -> None:
        try:
            table = self.info_table_1
            idx = table.currentIndex().row()
            if idx == -1:
                return
            dtime = table.item(idx, 0).text()
            ticker = self._worker.code if self._worker else self.coin

            s = _get_static()
            upbit = getattr(getattr(s, "account", None), "upbit", None) if s else None
            if upbit is None:
                return

            wait = aio.run(upbit.get_order(ticker_or_uuid=ticker))
            for data in wait:
                date = data["created_at"].split("T")[0]
                time_ = data["created_at"].split("T")[1].split("+")[0]
                date_time = date + "\n" + time_
                if date_time == dtime:
                    if self.is_demo:
                        log.info("데모 모드: 주문 취소 시뮬레이션 - UUID: %s", data["uuid"])
                        self.show_messagebox(True, "데모 모드: 주문 취소가 시뮬레이션되었습니다.")
                        return
                    aio.run(upbit.cancel_order(uuid=data["uuid"]))
        except Exception:
            log.exception("[TradeWidget] clicked_cancel 오류")

    # ──────────────────────────────────────────── 가격/수량 계산 ──

    def changed_price(self) -> None:
        self.set_total_price()

    def changed_volume(self) -> None:
        self.set_total_price()

    def changed_total(self) -> None:
        if not getattr(self, "volume_changed", True):
            self.volume_changed = True
            return
        try:
            if self.tabWidget.currentIndex() == 0:
                idx = self.buy_stack.currentIndex()
                if idx == 0 and self.buy_price_1.value() != 0.0:
                    volume = round(self.buy_total_price_1.value() / self.buy_price_1.value(), 8)
                    self.buy_volume_1.setValue(volume)
                elif self.buy_price_3.value() != 0.0:
                    volume = round(self.buy_total_price_3.value() / self.buy_price_3.value(), 8)
                    self.buy_volume_3.setValue(volume)
            else:
                idx = self.sell_stack.currentIndex()
                if idx == 0 and self.sell_price_1.value() != 0.0:
                    volume = round(self.sell_total_price_1.value() / self.sell_price_1.value(), 8)
                    self.sell_volume_1.setValue(volume)
                elif self.sell_price_3.value() != 0.0:
                    volume = round(self.sell_total_price_3.value() / self.sell_price_3.value(), 8)
                    self.sell_volume_3.setValue(volume)
        except Exception:
            log.exception("[TradeWidget] changed_total 오류")

    def set_total_price(self) -> None:
        try:
            if self.tabWidget.currentIndex() == 0:
                idx = self.buy_stack.currentIndex()
                if idx == 0:
                    self.buy_total_price_1.setValue(self.buy_price_1.value() * self.buy_volume_1.value())
                else:
                    self.buy_total_price_3.setValue(self.buy_price_3.value() * self.buy_volume_3.value())
            else:
                idx = self.sell_stack.currentIndex()
                if idx == 0:
                    self.sell_total_price_1.setValue(self.sell_price_1.value() * self.sell_volume_1.value())
                else:
                    self.sell_total_price_3.setValue(self.sell_price_3.value() * self.sell_volume_3.value())
        except Exception:
            log.exception("[TradeWidget] set_total_price 오류")

    # ──────────────────────────────────────────── 주문 정보 업데이트 ──

    def set_execute_info(self, data: list, idx: int) -> None:
        table = self.info_table_1
        items = self.items1
        if idx == 2:
            table = self.info_table_2
            items = self.items2
            coin = self.coin.split("-")[1]
            self.set_own_asset(coin)

        if table.rowCount() != len(data):
            table.clearContents()
            table.setRowCount(0)
            items.clear()
            if not data:
                return
            table.setRowCount(len(data))
            font = QFont()
            font.setBold(True)
            for i in range(len(data)):
                row_items = [QTableWidgetItem() for _ in range(4)]
                for j, item in enumerate(row_items):
                    item.setFont(font)
                    item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                    table.setItem(i, j, item)
                items.append(row_items)
            table.verticalHeader().setDefaultSectionSize(60)

        for i, info in enumerate(data):
            if len(data) != len(items):
                break
            date = info["created_at"].split("T")[0]
            time_ = info["created_at"].split("T")[1].split("+")[0]
            items[i][0].setText(date + "\n" + time_)

            if info["side"] == "bid":
                items[i][1].setText(info["market"] + "\n매수")
            elif info["side"] == "ask":
                items[i][1].setText(info["market"] + "\n매도")

            if info["price"] is not None:
                krw = int(float(info["price"]) * float(info["volume"]))
                items[i][2].setText(f'{info["price"]}\n{krw}')
            else:
                items[i][2].setText(str(info["price"]))

            items[i][3].setText(str(info["volume"]))

    # ──────────────────────────────────────────── 심볼/가격 설정 ──

    def all_reset(self) -> None:
        try:
            for spin in (
                self.buy_price_1, self.buy_volume_1, self.buy_total_price_1,
                self.buy_total_price_2, self.buy_price_3, self.buy_volume_3,
                self.buy_total_price_3, self.buy_monitor_price_3,
                self.sell_price_1, self.sell_volume_1, self.sell_total_price_1,
                self.sell_total_price_2, self.sell_price_3, self.sell_volume_3,
                self.sell_total_price_3, self.sell_monitor_price_3,
            ):
                spin.setValue(0.0)
        except Exception:
            log.exception("[TradeWidget] all_reset 오류")

    def set_price(self, ticker: str) -> None:
        """심볼 변경 시 호출 (레거시 호환)."""
        self.all_reset()
        self.coin = ticker
        if self._worker:
            self._worker.code = ticker

        try:
            self.info_table_1.clearContents()
            self.info_table_1.setRowCount(0)
            self.info_table_2.clearContents()
            self.info_table_2.setRowCount(0)
        except Exception:
            pass
        self.items1.clear()
        self.items2.clear()

        try:
            coin = ticker.split("-")[1]
            for lbl in (self.sell_ticker_1, self.sell_ticker_2, self.sell_ticker_3):
                lbl.setText(coin)
            self.set_own_asset(coin)
        except Exception:
            pass

        try:
            s = _get_static()
            chart = getattr(s, "chart", None) if s else None
            coins_data = getattr(chart, "coins", {}) if chart else {}
            coin_obj = coins_data.get(ticker)
            market_price = coin_obj.get_trade_price() if coin_obj else 0
            for spin in (self.buy_price_1, self.buy_price_3,
                         self.sell_price_1, self.sell_price_3):
                spin.setValue(market_price)
        except Exception:
            pass

    def update_symbol(self, source: str, symbol: str) -> None:
        """UIStateManager 연동용 심볼 업데이트."""
        try:
            self.set_price(symbol)
        except Exception:
            log.exception("[TradeWidget] update_symbol 오류")

    def set_own_asset(self, coin: str) -> None:
        try:
            s = _get_static()
            account = getattr(s, "account", None) if s else None
            cash = str(int(getattr(account, "cash", 0))) if account else "0"
            for lbl in (self.buy_orderable_1, self.buy_orderable_2, self.buy_orderable_3):
                lbl.setText(cash)

            coins = getattr(account, "coins", {}) if account else {}
            if coin in coins:
                balance = f'{coins[coin].get("balance", 0):,.8f}'
            else:
                balance = "0.0"
            for lbl in (self.sell_orderable_1, self.sell_orderable_2, self.sell_orderable_3):
                lbl.setText(balance)
        except Exception:
            log.exception("[TradeWidget] set_own_asset 오류")

    def set_current_price(self, cur_price: float) -> None:
        try:
            self.volume_changed = False
            for spin in (self.buy_price_1, self.buy_price_3,
                         self.sell_price_1, self.sell_price_3):
                spin.setValue(cur_price)
        except Exception:
            log.exception("[TradeWidget] set_current_price 오류")

    # ──────────────────────────────────────────── 메시지 다이얼로그 ──

    def show_messagebox(self, condition: bool, message: Any) -> None:
        try:
            title = "알림" if condition else "오류"
            dlg = MessageDialog(self, title, str(message))
            self._active_dialogs.append(dlg)
            dlg.destroyed.connect(
                lambda _=None, d=dlg: self._active_dialogs.remove(d)
                if d in self._active_dialogs else None
            )
            dlg.show()
        except Exception:
            log.exception("[TradeWidget] show_messagebox 실패")

    # ──────────────────────────────────────────── 종료 처리 ──

    def closeEvent(self, event: Any) -> None:
        try:
            if self._worker is not None:
                self._worker.close()
        except Exception:
            pass
        if _HAS_QT:
            super().closeEvent(event)


__all__ = ["TradeWidget", "TradeWorker", "MessageDialog"]
