#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
IndicatorEngine - 기술적 지표 증분 계산 엔진 (O(1) 복잡도)
...
(see original file header)
"""

import math
import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque

# Module logger
logger = logging.getLogger("IndicatorEngine")
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)


class IndicatorEngine:
    """
    기술적 지표 증분 계산 엔진
    """
    def __init__(self):
        # 각 symbol + timeframe별 지표 상태
        self.indicator_states: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: self._init_indicator_state())

        # 메트릭스
        self.metrics = {"candle_count": 0, "indicator_calculation_count": 0}

        logger.info("[IndicatorEngine] Initialized")

    def _init_indicator_state(self) -> Dict[str, Any]:
        return {
            "rsi_14": {"period": 14, "avg_gain": 0.0, "avg_loss": 0.0, "prev_close": None, "count": 0, "value": None},
            "rsi_28": {"period": 28, "avg_gain": 0.0, "avg_loss": 0.0, "prev_close": None, "count": 0, "value": None},
            "ema_5": {"period": 5, "value": None, "multiplier": 2 / (5 + 1)},
            "ema_10": {"period": 10, "value": None, "multiplier": 2 / (10 + 1)},
            "ema_20": {"period": 20, "value": None, "multiplier": 2 / (20 + 1)},
            "ema_50": {"period": 50, "value": None, "multiplier": 2 / (50 + 1)},
            "ema_100": {"period": 100, "value": None, "multiplier": 2 / (100 + 1)},
            "ema_200": {"period": 200, "value": None, "multiplier": 2 / (200 + 1)},
            "sma_5": {"period": 5, "values": deque(maxlen=5), "sum": 0.0, "value": None},
            "sma_10": {"period": 10, "values": deque(maxlen=10), "sum": 0.0, "value": None},
            "sma_20": {"period": 20, "values": deque(maxlen=20), "sum": 0.0, "value": None},
            "sma_50": {"period": 50, "values": deque(maxlen=50), "sum": 0.0, "value": None},
            "sma_100": {"period": 100, "values": deque(maxlen=100), "sum": 0.0, "value": None},
            "sma_200": {"period": 200, "values": deque(maxlen=200), "sum": 0.0, "value": None},
            "macd": {
                "ema_12": {"period": 12, "value": None, "multiplier": 2 / (12 + 1)},
                "ema_26": {"period": 26, "value": None, "multiplier": 2 / (26 + 1)},
                "signal_9": {"period": 9, "value": None, "multiplier": 2 / (9 + 1)},
                "macd_line": None,
                "signal_line": None,
                "histogram": None,
            },
            "bb_20": {
                "period": 20,
                "std_multiplier": 2,
                "values": deque(maxlen=20),
                "count": 0,
                "mean": 0.0,
                "m2": 0.0,
                "middle": None,
                "upper": None,
                "lower": None,
                "bandwidth": None,
            },
            "atr_14": {"period": 14, "value": None, "multiplier": 2 / (14 + 1), "prev_close": None},
            "stochastic_14": {
                "k_period": 14,
                "d_period": 3,
                "high_buffer": deque(maxlen=14),
                "low_buffer": deque(maxlen=14),
                "d_values": deque(maxlen=3),
                "d_sum": 0.0,
                "k": None,
                "d": None,
            },
        }

    def calculate(self, candle: Dict[str, Any]) -> Dict[str, Any]:
        if not candle.get("is_closed"):
            return {}

        symbol = candle["symbol"]
        timeframe = candle["timeframe"]
        close = candle["c"]
        high = candle["h"]
        low = candle["l"]
        volume = candle.get("v", 0)

        key = (symbol, timeframe)
        state = self.indicator_states[key]

        rsi_14 = self._calculate_rsi(state["rsi_14"], close)
        rsi_28 = self._calculate_rsi(state["rsi_28"], close)

        ema_5 = self._calculate_ema(state["ema_5"], close)
        ema_10 = self._calculate_ema(state["ema_10"], close)
        ema_20 = self._calculate_ema(state["ema_20"], close)
        ema_50 = self._calculate_ema(state["ema_50"], close)
        ema_100 = self._calculate_ema(state["ema_100"], close)
        ema_200 = self._calculate_ema(state["ema_200"], close)

        sma_5 = self._calculate_sma(state["sma_5"], close)
        sma_10 = self._calculate_sma(state["sma_10"], close)
        sma_20 = self._calculate_sma(state["sma_20"], close)
        sma_50 = self._calculate_sma(state["sma_50"], close)
        sma_100 = self._calculate_sma(state["sma_100"], close)
        sma_200 = self._calculate_sma(state["sma_200"], close)

        macd_result = self._calculate_macd(state["macd"], close)
        bb_result = self._calculate_bollinger_bands(state["bb_20"], close)
        atr_14 = self._calculate_atr(state["atr_14"], high, low, close)
        stochastic_result = self._calculate_stochastic(state["stochastic_14"], high, low, close)

        self.metrics["candle_count"] += 1
        self.metrics["indicator_calculation_count"] += 1

        return {
            "rsi_14": rsi_14,
            "rsi_28": rsi_28,
            "ema_5": ema_5,
            "ema_10": ema_10,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_100": ema_100,
            "ema_200": ema_200,
            "sma_5": sma_5,
            "sma_10": sma_10,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_100": sma_100,
            "sma_200": sma_200,
            **macd_result,
            **bb_result,
            "atr_14": atr_14,
            **stochastic_result,
        }

    def _calculate_rsi(self, state: Dict[str, Any], close: float) -> Optional[float]:
        period = state["period"]
        if state["prev_close"] is None:
            state["prev_close"] = close
            state["count"] = 1
            return None

        change = close - state["prev_close"]
        gain = max(change, 0)
        loss = max(-change, 0)

        if state["count"] < period:
            state["avg_gain"] = (state["avg_gain"] * state["count"] + gain) / (state["count"] + 1)
            state["avg_loss"] = (state["avg_loss"] * state["count"] + loss) / (state["count"] + 1)
            state["count"] += 1
        else:
            state["avg_gain"] = (state["avg_gain"] * (period - 1) + gain) / period
            state["avg_loss"] = (state["avg_loss"] * (period - 1) + loss) / period

        state["prev_close"] = close

        if state["avg_loss"] == 0:
            state["value"] = 100.0
        else:
            rs = state["avg_gain"] / state["avg_loss"]
            state["value"] = 100.0 - (100.0 / (1.0 + rs))

        return state["value"] if state["count"] >= period else None

    def _calculate_ema(self, state: Dict[str, Any], close: float) -> Optional[float]:
        if state["value"] is None:
            state["value"] = close
        else:
            state["value"] = (close - state["value"]) * state["multiplier"] + state["value"]
        return state["value"]

    def _calculate_sma(self, state: Dict[str, Any], close: float) -> Optional[float]:
        values = state["values"]
        period = state["period"]
        if len(values) == period:
            old_value = values[0]
            state["sum"] -= old_value
        values.append(close)
        state["sum"] += close
        if len(values) == period:
            state["value"] = state["sum"] / period
            return state["value"]
        else:
            return None

    def _calculate_macd(self, state: Dict[str, Any], close: float) -> Dict[str, Optional[float]]:
        ema_12 = self._calculate_ema(state["ema_12"], close)
        ema_26 = self._calculate_ema(state["ema_26"], close)

        if ema_12 is None or ema_26 is None:
            return {"macd_line": None, "signal_line": None, "histogram": None}

    def _calculate_bollinger_bands(self, state: Dict[str, Any], close: float) -> Dict[str, Optional[float]]:
        values = state["values"]
        period = state["period"]
        std_multiplier = state["std_multiplier"]

    def _calculate_atr(self, state: Dict[str, Any], high: float, low: float, close: float) -> Optional[float]:
        if state["prev_close"] is None:
            true_range = high - low
        else:
            hl = high - low
            hc = abs(high - state["prev_close"])
            lc = abs(low - state["prev_close"])
            true_range = max(hl, hc, lc)

        state["prev_close"] = close

        if state["value"] is None:
            state["value"] = true_range
        else:
            state["value"] = (true_range - state["value"]) * state["multiplier"] + state["value"]

        return state["value"]

    def _calculate_stochastic(self, state: Dict[str, Any], high: float, low: float, close: float) -> Dict[str, Optional[float]]:
        state["high_buffer"].append(high)
        state["low_buffer"].append(low)

        if len(state["high_buffer"]) < state["k_period"]:
            return {"stochastic_k": None, "stochastic_d": None}

        highest = max(state["high_buffer"])
        lowest = min(state["low_buffer"])

        if highest == lowest:
            k = 50.0
        else:
            k = 100.0 * (close - lowest) / (highest - lowest)

        state["k"] = k

        d_values = state["d_values"]
        if len(d_values) == state["d_period"]:
            state["d_sum"] -= d_values[0]
        d_values.append(k)
        state["d_sum"] += k

        if len(d_values) == state["d_period"]:
            state["d"] = state["d_sum"] / state["d_period"]
            return {"stochastic_k": k, "stochastic_d": state["d"]}
        else:
            return {"stochastic_k": k, "stochastic_d": None}

    def get_metrics(self) -> Dict[str, int]:
        return {**self.metrics, "active_symbols": len(self.indicator_states)}


# Test harness -> use logger
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("[IndicatorEngine] Unit Test")
    logger.info("=" * 60)

    engine = IndicatorEngine()

    candles = [
        {"symbol": "KRW-BTC", "timeframe": "min_1", "o": 50000000, "h": 50100000, "l": 49900000, "c": 50000000, "v": 0.5, "is_closed": True},
        {"symbol": "KRW-BTC", "timeframe": "min_1", "o": 50000000, "h": 50200000, "l": 49950000, "c": 50100000, "v": 0.6, "is_closed": True},
        {"symbol": "KRW-BTC", "timeframe": "min_1", "o": 50100000, "h": 50150000, "l": 50000000, "c": 50050000, "v": 0.4, "is_closed": True},
        {"symbol": "KRW-BTC", "timeframe": "min_1", "o": 50050000, "h": 50100000, "l": 49900000, "c": 49950000, "v": 0.7, "is_closed": True},
        {"symbol": "KRW-BTC", "timeframe": "min_1", "o": 49950000, "h": 50000000, "l": 49800000, "c": 49900000, "v": 0.8, "is_closed": True},
    ]

    logger.info("\n[Test] Calculating indicators...")
    for i, candle in enumerate(candles):
        logger.info("Candle #%d: O=%s, H=%s, L=%s, C=%s, V=%s", i + 1, candle["o"], candle["h"], candle["l"], candle["c"], candle["v"])
        indicators = engine.calculate(candle)
        logger.info("  RSI(14): %s", indicators.get("rsi_14"))
        logger.info("  EMA(20): %s", indicators.get("ema_20"))
        logger.info("  SMA(20): %s", indicators.get("sma_20"))
    logger.info("\n" + "=" * 60)
    logger.info("[Metrics]")
    metrics = engine.get_metrics()
    for key, value in metrics.items():
        logger.info("  %s: %s", key, value)
    logger.info("=" * 60)