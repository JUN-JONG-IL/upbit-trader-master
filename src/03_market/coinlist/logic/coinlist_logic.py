"""
[Purpose]
- CoinlistWidget의 데이터 처리/정렬/표 업데이트/리셋/자동/누적 등을 담당한다.
- 원본 동작(색상/임계값/선택 밑줄/표시 방식)을 유지하면서,
  "변한 것만" 업데이트하여 부드러움/성능을 개선한다.

[Performance Improvements]
1) QTableWidget repaint 억제:
   - 대량 갱신 구간에서 setUpdatesEnabled(False) / blockSignals(True) 사용 후 복구
2) "변한 것만" setText/setBackground/setForeground:
   - 마지막 렌더 값 캐시(row/col별)로 동일 값이면 setText 등 호출 생략
   - (Qt에서 setText/setBackground가 repaint/레이아웃 비용을 유발)
3) Progress 업데이트 빈도 감소:
   - update_progress 호출을 더 듬성듬성(50행 단위)으로

[Notes]
- 5초 스냅샷(CoinListWorker) 유지
- 기존 기능(리셋/자동/컨텍스트 메뉴/임계값 강조/누적) 유지
"""

from __future__ import annotations

import time
import traceback
from decimal import Decimal

import polars as pl
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QMenu

try:
    import static  # type: ignore[import]
except ImportError:
    try:
        from app import static  # type: ignore[import]
    except ImportError:
        static = None  # type: ignore[assignment]

from .formatting.coinlist_format import format_price


class CoinListLogic:
    def __init__(self, widget):
        self.w = widget
        # row index -> dict(cache)
        # cache key examples: "c2_text", "c6_bg" ...
        self._cell_cache: list[dict[str, object]] = []

    # ---------- cache helpers ----------
    def _ensure_cache_rows(self, row_count: int):
        if row_count > len(self._cell_cache):
            self._cell_cache.extend({} for _ in range(row_count - len(self._cell_cache)))

    def _set_text(self, row: int, col: int, text: str):
        key = f"t{col}"
        cache = self._cell_cache[row]
        if cache.get(key) == text:
            return
        cache[key] = text
        self.w.items[row][col].setText(text)

    def _set_fg(self, row: int, col: int, fg):
        key = f"fg{col}"
        cache = self._cell_cache[row]
        if cache.get(key) == fg:
            return
        cache[key] = fg
        self.w.items[row][col].setForeground(fg)

    def _set_bg(self, row: int, col: int, bg):
        key = f"bg{col}"
        cache = self._cell_cache[row]
        if cache.get(key) == bg:
            return
        cache[key] = bg
        self.w.items[row][col].setBackground(bg)

    # ---------- baselines / accum ----------
    @staticmethod
    def _get_chart_codes() -> list:
        """static.chart.codes에 안전하게 접근."""
        try:
            chart = getattr(static, "chart", None)
            if chart is None:
                return []
            codes = getattr(chart, "codes", None)
            return list(codes) if codes else []
        except Exception:
            return []

    @staticmethod
    def _get_chart_coins() -> dict:
        """static.chart.coins에 안전하게 접근."""
        try:
            chart = getattr(static, "chart", None)
            if chart is None:
                return {}
            coins = getattr(chart, "coins", None)
            return dict(coins) if coins else {}
        except Exception:
            return {}

    def init_accumulators(self):
        codes = self._get_chart_codes()
        self.w.trade_buy_accum = {code.split("-")[1]: Decimal("0") for code in codes}
        self.w.trade_sell_accum = {code.split("-")[1]: Decimal("0") for code in codes}
        self.w.prev_dominance = {code.split("-")[1]: None for code in codes}

    def init_baselines(self):
        current_time = time.time() * 1000
        for coin in self._get_chart_coins().values():
            price = coin.get_trade_price() or 0
            if price == 0:
                QTimer.singleShot(100, lambda c=coin: self._async_get_price(c))
            else:
                coin.old_price = price

            trade = coin.get_acc_trade_price_24h() or 0
            if trade == 0:
                QTimer.singleShot(100, lambda c=coin: self._async_get_trade(c))
            else:
                coin.old_trade = trade

            coin.old_time = current_time

    def reset_price_baseline(self):
        current_time = time.time() * 1000
        for coin in self._get_chart_coins().values():
            price = coin.get_trade_price() or 0
            if price == 0:
                QTimer.singleShot(100, lambda c=coin: self._async_get_price(c))
            else:
                coin.old_price = price
                coin.old_time = current_time

    def reset_trade_baseline(self):
        current_time = time.time() * 1000
        for coin in self._get_chart_coins().values():
            trade = coin.get_acc_trade_price_24h() or 0
            if trade == 0:
                QTimer.singleShot(100, lambda c=coin: self._async_get_trade(c))
            else:
                coin.old_trade = trade
                coin.old_time = current_time

    def _async_get_price(self, coin):
        price = coin.get_trade_price() or 0
        if price > 0:
            coin.old_price = price
            coin.old_time = time.time() * 1000
        else:
            QTimer.singleShot(100, lambda: self._async_get_price(coin))

    def _async_get_trade(self, coin):
        trade = coin.get_acc_trade_price_24h() or 0
        if trade > 0:
            coin.old_trade = trade
            coin.old_time = time.time() * 1000
        else:
            QTimer.singleShot(100, lambda: self._async_get_trade(coin))

    def get_rate_change(self, coin):
        if self.w.rate_calc_interval == 0 or getattr(coin, "old_price", 0) == 0:
            return 0.0, 0.0
        current_price = coin.get_trade_price() or 0
        old_price = coin.old_price
        rate = (current_price - old_price) / old_price * 100 if old_price != 0 else 0.0
        return float(rate), float(old_price)

    def get_trade_change(self, coin):
        if self.w.trade_calc_interval == 0 or getattr(coin, "old_trade", 0) == 0:
            return 0.0, 0.0
        current_trade = coin.get_acc_trade_price_24h() or 0
        old_trade = coin.old_trade
        rate = (current_trade - old_trade) / old_trade * 100 if old_trade != 0 else 0.0
        return float(rate), float(old_trade / 1000000)

    # ---------- remaining time ----------
    def update_remaining_time(self):
        try:
            if self.w.check_price_auto.isChecked() and self.w.rate_calc_interval > 0:
                elapsed = time.time() - self.w.last_rate_save_time
                remaining_sec = max(0, (self.w.rate_calc_interval / 1000) - elapsed)
                self.w.label_rate_remaining.setText(self._format_remaining("가격 계산 남음", remaining_sec))
            else:
                self.w.label_rate_remaining.setText("가격 계산 남음: 0시 0분 0초 0ms")

            if self.w.check_trade_change_auto.isChecked() and self.w.trade_calc_interval > 0:
                elapsed = time.time() - self.w.last_trade_save_time
                remaining_sec = max(0, (self.w.trade_calc_interval / 1000) - elapsed)
                self.w.label_trade_remaining.setText(self._format_remaining("거래 계산 남음", remaining_sec))
            else:
                self.w.label_trade_remaining.setText("거래 계산 남음: 0시 0분 0초 0ms")

            if self.w.check_trade_auto.isChecked() and self.w.trade_reset_interval > 0:
                elapsed = time.time() - self.w.last_clear_time
                remaining_sec = max(0, (self.w.trade_reset_interval / 1000) - elapsed)
                self.w.label_remaining_time.setText(self._format_remaining("누적 남음", remaining_sec))
            else:
                self.w.label_remaining_time.setText("누적 남음: 0시 0분 0초 0ms")
        except Exception:
            traceback.print_exc()

    def _format_remaining(self, prefix: str, remaining_sec: float) -> str:
        hours = int(remaining_sec // 3600)
        minutes = int((remaining_sec % 3600) // 60)
        seconds = int(remaining_sec % 60)
        ms = int((remaining_sec - int(remaining_sec)) * 1000)
        return f"{prefix}: {hours}시 {minutes}분 {seconds}초 {ms}ms"

    # ---------- toggles (중복 start 제거) ----------
    def toggle_price_auto(self, state):
        try:
            if state == Qt.Checked:
                self.manual_rate_reset()
            else:
                self.w.price_timer.stop()
                self.w.label_rate_remaining.setText("가격 계산 남음: 0시 0분 0초 0ms")
        except Exception:
            traceback.print_exc()

    def toggle_trade_change_auto(self, state):
        try:
            if state == Qt.Checked:
                self.manual_trade_reset()
            else:
                self.w.trade_change_timer.stop()
                self.w.label_trade_remaining.setText("거래 계산 남음: 0시 0분 0초 0ms")
        except Exception:
            traceback.print_exc()

    def toggle_auto_clear(self, state):
        try:
            if state == Qt.Checked:
                self.manual_clear()
            else:
                self.w.clear_timer.stop()
                self.w.label_remaining_time.setText("누적 남음: 0시 0분 0초 0ms")
        except Exception:
            traceback.print_exc()

    # ---------- timer callbacks ----------
    def update_price_changes(self):
        try:
            self.partial_update_changes()
            self.reset_price_baseline()
            self.w.last_rate_save_time = time.time()
            self.update_remaining_time()
        except Exception:
            traceback.print_exc()

    def update_trade_changes(self):
        try:
            self.partial_update_changes()
            self.reset_trade_baseline()
            self.w.last_trade_save_time = time.time()
            self.update_remaining_time()
        except Exception:
            traceback.print_exc()

    # ---------- manual reset ----------
    def manual_clear(self):
        try:
            self.w.ignore_accum_update = True
            self.w.update_debounce_timer.stop()

            self.init_accumulators()
            self.force_clear_table_accum()

            self.w.start_progress("거래 누적 수동 리셋중", 1)
            self.partial_update_accum()
            self.w.coin_list.viewport().update()

            if self.w.check_trade_auto.isChecked() and self.w.trade_reset_interval > 0:
                self.w.clear_timer.stop()
                self.w.clear_timer.start(self.w.trade_reset_interval)
                self.w.last_clear_time = time.time()
            else:
                self.w.clear_timer.stop()
                self.w.label_remaining_time.setText("누적 남음: 0시 0분 0초 0ms")

            self.update_remaining_time()
        except Exception:
            traceback.print_exc()
        finally:
            self.w.ignore_accum_update = False
            self.w.end_progress()

    def auto_clear_accum(self):
        try:
            self.w.ignore_accum_update = True
            self.w.update_debounce_timer.stop()

            self.init_accumulators()
            self.force_clear_table_accum()

            self.w.start_progress("거래 누적 자동 리셋중", 1)
            self.partial_update_accum()
            self.w.coin_list.viewport().update()

            self.w.last_clear_time = time.time()
            self.update_remaining_time()
        except Exception:
            traceback.print_exc()
        finally:
            self.w.ignore_accum_update = False
            self.w.end_progress()

    def manual_rate_reset(self):
        try:
            self.w.start_progress("가격 변화 수동 리셋중", 1)
            self.reset_price_baseline()
            self.partial_update_changes()

            if self.w.check_price_auto.isChecked() and self.w.rate_calc_interval > 0:
                self.w.price_timer.stop()
                self.w.price_timer.start(self.w.rate_calc_interval)
                self.w.last_rate_save_time = time.time()
            else:
                self.w.price_timer.stop()
                self.w.label_rate_remaining.setText("가격 계산 남음: 0시 0분 0초 0ms")

            self.update_remaining_time()
        except Exception:
            traceback.print_exc()
        finally:
            self.w.end_progress()

    def manual_trade_reset(self):
        try:
            self.w.start_progress("거래 변화 수동 리셋중", 1)
            self.reset_trade_baseline()
            self.partial_update_changes()

            if self.w.check_trade_change_auto.isChecked() and self.w.trade_calc_interval > 0:
                self.w.trade_change_timer.stop()
                self.w.trade_change_timer.start(self.w.trade_calc_interval)
                self.w.last_trade_save_time = time.time()
            else:
                self.w.trade_change_timer.stop()
                self.w.label_trade_remaining.setText("거래 계산 남음: 0시 0분 0초 0ms")

            self.update_remaining_time()
        except Exception:
            traceback.print_exc()
        finally:
            self.w.end_progress()

    def force_clear_table_accum(self):
        try:
            for row in range(self.w.coin_list.rowCount()):
                if self.w.coin_list.item(row, 8):
                    self.w.coin_list.item(row, 8).setText("")
                    self.w.coin_list.item(row, 8).setBackground(self.w.color_white)
                if self.w.coin_list.item(row, 9):
                    self.w.coin_list.item(row, 9).setText("")
                    self.w.coin_list.item(row, 9).setBackground(self.w.color_white)
        except Exception:
            traceback.print_exc()

    # ---------- accum update from websocket ----------
    def handle_accum_updated(self):
        if self.w.ignore_accum_update:
            return
        try:
            if self.w.check_reverse_buy_sell.isChecked():
                for ticker in list(self.w.trade_buy_accum.keys()):
                    buy = self.w.trade_buy_accum.get(ticker, Decimal("0"))
                    sell = self.w.trade_sell_accum.get(ticker, Decimal("0"))
                    prev = self.w.prev_dominance.get(ticker, None)

                    if buy == sell:
                        self.w.trade_buy_accum[ticker] = Decimal("0")
                        self.w.trade_sell_accum[ticker] = Decimal("0")
                        self.w.prev_dominance[ticker] = None
                    elif prev == "buy" and sell > buy:
                        diff = sell - buy
                        self.w.trade_sell_accum[ticker] = diff
                        self.w.trade_buy_accum[ticker] = Decimal("0")
                        self.w.prev_dominance[ticker] = "sell"
                    elif prev == "sell" and buy > sell:
                        diff = buy - sell
                        self.w.trade_buy_accum[ticker] = diff
                        self.w.trade_sell_accum[ticker] = Decimal("0")
                        self.w.prev_dominance[ticker] = "buy"
                    else:
                        if buy > sell:
                            self.w.prev_dominance[ticker] = "buy"
                        elif sell > buy:
                            self.w.prev_dominance[ticker] = "sell"

            self.debounce_update()
        except Exception:
            traceback.print_exc()

    def debounce_update(self):
        try:
            if self.w.current_sort_col in [5, 6, 7, 8] and self.w.check_sort_update.isChecked():
                self.w.start_progress("테이�� 정렬 및 업데이트 중", 1)
                self.updateData(list(self._get_chart_coins().values()), force_sort=True)
                self.w.end_progress()
            else:
                self.w.update_debounce_timer.start(200)
        except Exception:
            traceback.print_exc()

    # ---------- partial updates ----------
    def partial_update_accum(self):
        if not self.w.displayed_coins:
            return

        total = len(self.w.displayed_coins)
        self._ensure_cache_rows(total)

        self.w.start_progress("거래 누적 업데이트중", total)

        self.w.coin_list.setUpdatesEnabled(False)
        self.w.coin_list.blockSignals(True)
        try:
            for i, coin in enumerate(self.w.displayed_coins):
                ticker = coin.code[4:]
                buy = self.w.trade_buy_accum.get(ticker, Decimal("0"))
                sell = self.w.trade_sell_accum.get(ticker, Decimal("0"))

                buy_text = f"{buy:,.0f}" if buy > 0 else ""
                sell_text = f"{sell:,.0f}" if sell > 0 else ""
                self._set_text(i, 8, buy_text)
                self._set_text(i, 9, sell_text)

                if buy > sell:
                    self._set_bg(i, 8, self.w.color_light_red)
                    self._set_bg(i, 9, self.w.color_white)
                elif sell > buy:
                    self._set_bg(i, 8, self.w.color_white)
                    self._set_bg(i, 9, self.w.color_light_blue)
                else:
                    self._set_bg(i, 8, self.w.color_white)
                    self._set_bg(i, 9, self.w.color_white)

                if i % 50 == 0:
                    self.w.update_progress(i + 1)
        finally:
            self.w.coin_list.blockSignals(False)
            self.w.coin_list.setUpdatesEnabled(True)
            self.w.coin_list.viewport().update()
            self.w.end_progress()

    def partial_update_changes(self):
        if not self.w.displayed_coins:
            return

        total = len(self.w.displayed_coins)
        self._ensure_cache_rows(total)

        self.w.start_progress("변화율 업데이트중", total)

        self.w.coin_list.setUpdatesEnabled(False)
        self.w.coin_list.blockSignals(True)
        try:
            for i, coin in enumerate(self.w.displayed_coins):
                rate_change, saved_price = self.get_rate_change(coin)
                trade_change, saved_trade = self.get_trade_change(coin)

                self._set_text(i, 6, f"{rate_change:.2f}% ({format_price(saved_price, coin)})")
                self._set_text(i, 7, f"{trade_change:.2f}% ({saved_trade:,.2f}백만)")

                # fg
                self._set_fg(i, 6, self.w.color_red if rate_change > 0 else self.w.color_blue if rate_change < 0 else self.w.color_black)
                self._set_fg(i, 7, self.w.color_red if trade_change > 0 else self.w.color_blue if trade_change < 0 else self.w.color_black)

                # bg (threshold)
                if rate_change >= self.w.rate_rise_threshold:
                    self._set_bg(i, 6, self.w.color_light_red)
                    self._set_fg(i, 6, self.w.color_black)
                elif rate_change <= self.w.rate_fall_threshold:
                    self._set_bg(i, 6, self.w.color_light_blue)
                    self._set_fg(i, 6, self.w.color_black)
                else:
                    self._set_bg(i, 6, self.w.color_white)

                if trade_change >= self.w.trade_rise_threshold:
                    self._set_bg(i, 7, self.w.color_light_red)
                    self._set_fg(i, 7, self.w.color_black)
                elif trade_change <= self.w.trade_fall_threshold:
                    self._set_bg(i, 7, self.w.color_light_blue)
                    self._set_fg(i, 7, self.w.color_black)
                else:
                    self._set_bg(i, 7, self.w.color_white)

                if i % 50 == 0:
                    self.w.update_progress(i + 1)
        finally:
            self.w.coin_list.blockSignals(False)
            self.w.coin_list.setUpdatesEnabled(True)
            self.w.coin_list.viewport().update()
            self.w.end_progress()

        if self.w.check_sort_update.isChecked() and self.w.current_sort_col in [6, 7]:
            self.updateData(list(self._get_chart_coins().values()), force_sort=True)

    def partial_update_prices_and_trades(self):
        if not self.w.displayed_coins:
            return

        total = len(self.w.displayed_coins)
        self._ensure_cache_rows(total)

        self.w.start_progress("가격/거래 업데이트중", total)

        self.w.coin_list.setUpdatesEnabled(False)
        self.w.coin_list.blockSignals(True)
        try:
            for i, coin in enumerate(self.w.displayed_coins):
                trade_price = coin.get_trade_price() or 0
                signed_change_rate = (coin.get_signed_change_rate() or 0) * 100
                acc_trade_price_24h = (coin.get_acc_trade_price_24h() or 0) / 1000000

                self._set_text(i, 3, format_price(trade_price, coin))
                self._set_text(i, 4, f"{signed_change_rate:.2f}%")
                self._set_text(i, 5, f"{acc_trade_price_24h:,.2f}백만")
                self._set_fg(i, 4, self.w.color_red if signed_change_rate > 0 else self.w.color_blue if signed_change_rate < 0 else self.w.color_black)

                if i % 50 == 0:
                    self.w.update_progress(i + 1)
        finally:
            self.w.coin_list.blockSignals(False)
            self.w.coin_list.setUpdatesEnabled(True)
            self.w.coin_list.viewport().update()
            self.w.end_progress()

    # ---------- updateData (full render) ----------
    def updateData(self, data, force_sort=False):
        try:
            if data is None:
                return

            if self.w.favorite_mode:
                data = [coin for coin in data if coin.code[4:] in self.w.favorites]

            row_count = len(data)
            self._ensure_row_items(row_count)
            self._ensure_cache_rows(row_count)

            need_sort = force_sort or (self.w.current_sort_col in [5, 6, 7, 8] and self.w.check_sort_update.isChecked())
            if not need_sort and self.w.displayed_coins and len(self.w.displayed_coins) == row_count:
                self.partial_update_prices_and_trades()
                return

            reverse = (self.w.sort_states[self.w.current_sort_col] == -1)
            self.w.displayed_coins = sorted(
                data,
                key=lambda coin: self.get_sort_key(coin, self.w.current_sort_col),
                reverse=reverse,
            )

            total = len(self.w.displayed_coins)
            self.w.start_progress("데이터 로딩중", total)

            self.w.coin_list.setUpdatesEnabled(False)
            self.w.coin_list.blockSignals(True)
            try:
                total_hold = Decimal("0")

                for i, coin in enumerate(self.w.displayed_coins):
                    trade_price = coin.get_trade_price() or 0
                    signed_change_rate = (coin.get_signed_change_rate() or 0) * 100
                    rate_change, saved_price = self.get_rate_change(coin)
                    trade_change, saved_trade = self.get_trade_change(coin)
                    acc_trade_price_24h = (coin.get_acc_trade_price_24h() or 0) / 1000000

                    buy_accum = self.w.trade_buy_accum.get(coin.code[4:], Decimal("0"))
                    sell_accum = self.w.trade_sell_accum.get(coin.code[4:], Decimal("0"))
                    hold_eval = Decimal("0")
                    total_hold += hold_eval

                    code = coin.code
                    name_text = f"{coin.korean_name}\n{code}" if self.w.name_toggle_korean else f"{coin.english_name}\n{code}"

                    self._set_text(i, 0, str(i + 1))
                    self._set_text(i, 2, name_text)

                    self._set_text(i, 3, format_price(trade_price, coin))
                    self._set_text(i, 4, f"{signed_change_rate:.2f}%")
                    self._set_text(i, 5, f"{acc_trade_price_24h:,.2f}백만")

                    self._set_text(i, 6, f"{rate_change:.2f}% ({format_price(saved_price, coin)})")
                    self._set_text(i, 7, f"{trade_change:.2f}% ({saved_trade:,.2f}백만)")

                    buy_text = f"{buy_accum:,.0f}" if buy_accum > 0 else ""
                    sell_text = f"{sell_accum:,.0f}" if sell_accum > 0 else ""
                    self._set_text(i, 8, buy_text)
                    self._set_text(i, 9, sell_text)

                    self._set_text(i, 10, format_price(hold_eval, coin))

                    # fg
                    self._set_fg(i, 4, self.w.color_red if signed_change_rate > 0 else self.w.color_blue if signed_change_rate < 0 else self.w.color_black)
                    self._set_fg(i, 6, self.w.color_red if rate_change > 0 else self.w.color_blue if rate_change < 0 else self.w.color_black)
                    self._set_fg(i, 7, self.w.color_red if trade_change > 0 else self.w.color_blue if trade_change < 0 else self.w.color_black)

                    # threshold bg
                    if rate_change >= self.w.rate_rise_threshold:
                        self._set_bg(i, 6, self.w.color_light_red)
                        self._set_fg(i, 6, self.w.color_black)
                    elif rate_change <= self.w.rate_fall_threshold:
                        self._set_bg(i, 6, self.w.color_light_blue)
                        self._set_fg(i, 6, self.w.color_black)
                    else:
                        self._set_bg(i, 6, self.w.color_white)

                    if trade_change >= self.w.trade_rise_threshold:
                        self._set_bg(i, 7, self.w.color_light_red)
                        self._set_fg(i, 7, self.w.color_black)
                    elif trade_change <= self.w.trade_fall_threshold:
                        self._set_bg(i, 7, self.w.color_light_blue)
                        self._set_fg(i, 7, self.w.color_black)
                    else:
                        self._set_bg(i, 7, self.w.color_white)

                    # accum bg compare
                    if buy_accum > sell_accum:
                        self._set_bg(i, 8, self.w.color_light_red)
                        self._set_bg(i, 9, self.w.color_white)
                    elif sell_accum > buy_accum:
                        self._set_bg(i, 8, self.w.color_white)
                        self._set_bg(i, 9, self.w.color_light_blue)
                    else:
                        self._set_bg(i, 8, self.w.color_white)
                        self._set_bg(i, 9, self.w.color_white)

                    self.w.update_favorite_icon(i)

                    if i % 50 == 0:
                        self.w.update_progress(i + 1)

                self.w.label_total_hold.setText(f"총 보유금액: {format_price(total_hold)}원")
                self.w.load_column_widths()
            finally:
                self.w.coin_list.blockSignals(False)
                self.w.coin_list.setUpdatesEnabled(True)
                self.w.coin_list.viewport().update()
                self.w.end_progress()

        except Exception:
            traceback.print_exc()
            try:
                self.w.end_progress()
            except Exception:
                pass

    def _ensure_row_items(self, row_count: int):
        if self.w.coin_list.rowCount() != row_count:
            self.w.coin_list.setRowCount(row_count)

        if row_count > len(self.w.items):
            for _ in range(row_count - len(self.w.items)):
                self.w.items.append([self.w._new_item(j) for j in range(15)])

        for i in range(row_count):
            for j in range(15):
                if self.w.coin_list.item(i, j) is None:
                    self.w.coin_list.setItem(i, j, self.w.items[i][j])

    def get_sort_key(self, coin, col):
        try:
            if col == 0:
                return (0, 0)
            if col == 2:
                return (coin.korean_name if self.w.name_toggle_korean else coin.english_name, 0)
            if col == 3:
                return (coin.get_trade_price() or 0, 0)
            if col == 4:
                return (coin.get_signed_change_rate() or 0, 0)
            if col == 5:
                return (coin.get_acc_trade_price_24h() or 0, 0)
            if col == 6:
                return (self.get_rate_change(coin)[0], 0)
            if col == 7:
                return (self.get_trade_change(coin)[0], 0)
            if col == 8:
                return (self.w.trade_buy_accum.get(coin.code[4:], Decimal("0")), coin.get_acc_trade_price_24h() or 0)
            if col == 9:
                return (self.w.trade_sell_accum.get(coin.code[4:], Decimal("0")), coin.get_acc_trade_price_24h() or 0)
            return (0, 0)
        except Exception:
            return (0, 0)

    # ---------- UI actions ----------
    def chkTopClicked(self, col):
        try:
            header = self.w.coin_list.horizontalHeader()
            if self.w.current_sort_col == col:
                self.w.sort_states[col] = 1 if self.w.sort_states[col] == -1 else -1
            else:
                self.w.sort_states[col] = -1

            self.w.current_sort_col = col
            header.setSortIndicator(
                self.w.current_sort_col,
                Qt.DescendingOrder if self.w.sort_states[col] == -1 else Qt.AscendingOrder,
            )
            self.updateData(list(self._get_chart_coins().values()), force_sort=True)
            self.w.save_settings()
        except Exception:
            traceback.print_exc()

    def toggle_name_display(self):
        try:
            self.w.name_toggle_korean = not self.w.name_toggle_korean
            self.w.btn_toggle_name.setText("영문" if not self.w.name_toggle_korean else "한글")
            static.config.name_toggle_korean = self.w.name_toggle_korean
            static.config.save()

            self.w.start_progress("이름 표시 토글 중", 1)
            self.updateData(list(self._get_chart_coins().values()), force_sort=True)
        except Exception:
            traceback.print_exc()
        finally:
            self.w.end_progress()

    # ---------- context menu ----------
    def make_context_menu(self) -> QMenu:
        menu = QMenu(self.w)
        menu.addAction("이 셀 리셋").setData("reset_cell")
        menu.addAction("이 행 리셋 (가격/거래 변화율/거래대금/매수/매도)").setData("reset_row")
        menu.addAction("이 열 전체 리셋").setData("reset_column")
        menu.addAction("이 종목 누적만 리셋").setData("reset_accum")
        menu.addAction("변화율 임계값 초과 셀 리셋").setData("reset_threshold")
        return menu

    def show_context_menu(self, pos):
        try:
            index = self.w.coin_list.indexAt(pos)
            if not index.isValid():
                return
            row = index.row()
            col = index.column()
            if col not in [5, 6, 7, 8, 9]:
                return

            menu = self.make_context_menu()
            action = menu.exec_(self.w.coin_list.viewport().mapToGlobal(pos))
            if not action:
                return
            tag = action.data()

            if tag == "reset_cell":
                self.reset_single_cell(row, col)
            elif tag == "reset_row":
                self.reset_row_cells(row)
            elif tag == "reset_column":
                self.reset_column_cells(col)
            elif tag == "reset_accum":
                if col in [8, 9]:
                    self.reset_coin_accum(row)
            elif tag == "reset_threshold":
                if col in [6, 7]:
                    self.reset_threshold_cells(col)
        except Exception:
            traceback.print_exc()

    def reset_single_cell(self, row, col):
        try:
            item = self.w.coin_list.item(row, col)
            if not item:
                return
            item.setText("")
            item.setBackground(self.w.color_white)

            if col in [8, 9]:
                ticker = self.w.displayed_coins[row].code[4:]
                if col == 8:
                    self.w.trade_buy_accum[ticker] = Decimal("0")
                else:
                    self.w.trade_sell_accum[ticker] = Decimal("0")
                self.partial_update_accum()
            elif col == 6:
                self.w.displayed_coins[row].old_price = self.w.displayed_coins[row].get_trade_price() or 0
                self.partial_update_changes()
            elif col == 7:
                self.w.displayed_coins[row].old_trade = self.w.displayed_coins[row].get_acc_trade_price_24h() or 0
                self.partial_update_changes()

            self.w.coin_list.viewport().update()
        except Exception:
            traceback.print_exc()

    def reset_row_cells(self, row):
        for c in [5, 6, 7, 8, 9]:
            self.reset_single_cell(row, c)

    def reset_column_cells(self, col):
        for r in range(self.w.coin_list.rowCount()):
            self.reset_single_cell(r, col)

    def reset_coin_accum(self, row):
        ticker = self.w.displayed_coins[row].code[4:]
        self.w.trade_buy_accum[ticker] = Decimal("0")
        self.w.trade_sell_accum[ticker] = Decimal("0")
        self.partial_update_accum()

    def reset_threshold_cells(self, col):
        threshold_rise = self.w.rate_rise_threshold if col == 6 else self.w.trade_rise_threshold
        threshold_fall = self.w.rate_fall_threshold if col == 6 else self.w.trade_fall_threshold

        for r in range(self.w.coin_list.rowCount()):
            item = self.w.coin_list.item(r, col)
            if not item:
                continue
            txt = item.text()
            if not txt:
                continue
            try:
                val = float(txt.split("%")[0])
            except Exception:
                continue
            if val >= threshold_rise or val <= threshold_fall:
                self.reset_single_cell(r, col)

        self.partial_update_changes()

    # ---------- settings popup ----------
    def show_settings_popup(self):
        try:
            from .widget_time_settings import TimeSettingsDialog
        except Exception:
            traceback.print_exc()
            return

        try:
            dialog = TimeSettingsDialog(
                self.w,
                self.w.rate_calc_interval,
                self.w.trade_calc_interval,
                self.w.trade_reset_interval,
                self.w.rate_rise_threshold,
                self.w.rate_fall_threshold,
                self.w.trade_rise_threshold,
                self.w.trade_fall_threshold,
            )
            dialog.exec_()

            if dialog.result() == QDialog.Accepted:
                self.w.rate_calc_interval = (
                    dialog.spin_rate_calc_h.value() * 3600000
                    + dialog.spin_rate_calc_m.value() * 60000
                    + dialog.spin_rate_calc_s.value() * 1000
                    + dialog.spin_rate_calc_ms.value()
                )
                self.w.trade_calc_interval = (
                    dialog.spin_trade_calc_h.value() * 3600000
                    + dialog.spin_trade_calc_m.value() * 60000
                    + dialog.spin_trade_calc_s.value() * 1000
                    + dialog.spin_trade_calc_ms.value()
                )
                self.w.trade_reset_interval = (
                    dialog.spin_trade_reset_h.value() * 3600000
                    + dialog.spin_trade_reset_m.value() * 60000
                    + dialog.spin_trade_reset_s.value() * 1000
                    + dialog.spin_trade_reset_ms.value()
                )

                self.w.rate_rise_threshold = dialog.spin_rate_rise_threshold.value()
                self.w.rate_fall_threshold = dialog.spin_rate_fall_threshold.value()
                self.w.trade_rise_threshold = dialog.spin_trade_rise_threshold.value()
                self.w.trade_fall_threshold = dialog.spin_trade_fall_threshold.value()

                self.w.save_settings()

                self.toggle_auto_clear(self.w.check_trade_auto.checkState())
                self.toggle_price_auto(self.w.check_price_auto.checkState())
                self.toggle_trade_change_auto(self.w.check_trade_change_auto.checkState())

                self.partial_update_changes()
        except Exception:
            traceback.print_exc()