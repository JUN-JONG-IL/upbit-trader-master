#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
CandleAggregator - Trade 이벤트를 캔들로 집계
...
(unchanged header)
"""

import sys
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

# KST 시간대
KST = pytz.timezone("Asia/Seoul")

# Module logger
logger = logging.getLogger("CandleAggregator")
# Do not add handlers here; let the application configure handlers.
# Set a default level (INFO) — root/static configuration will control console visibility.
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)


class CandleAggregator:
    """
    Trade 이벤트를 캔들로 집계
    """
    def __init__(self, exchange: str = "upbit"):
        self.exchange = exchange
        self.timeframes = self._init_timeframes()
        self.candle_states: Dict[tuple, Dict[str, Any]] = defaultdict(dict)
        self.metrics = {
            "trade_count": 0,
            "candle_count": 0,
            "closed_candle_count": 0,
        }

        # Initialization info (logged)
        logger.info("[CandleAggregator] Initialized")
        logger.info("[CandleAggregator] Exchange: %s", exchange)
        logger.info("[CandleAggregator] Timeframes: %d types", len(self.timeframes))

    def _init_timeframes(self) -> List[Dict[str, Any]]:
        timeframes = []
        for count in [1, 3, 5, 10, 30, 60]:
            timeframes.append({"name": f"tick_{count}", "type": "tick", "count": count, "window_seconds": None})
        for seconds in range(1, 61):
            timeframes.append({"name": f"sec_{seconds}", "type": "second", "count": seconds, "window_seconds": seconds})
        for minutes in [1, 3, 5, 10, 15, 30, 60, 120, 240]:
            timeframes.append({"name": f"min_{minutes}", "type": "minute", "count": minutes, "window_seconds": minutes * 60})
        for hours in [1, 2, 4, 6, 12]:
            timeframes.append({"name": f"hour_{hours}", "type": "hour", "count": hours, "window_seconds": hours * 3600})
        timeframes.extend([
            {"name": "day", "type": "day", "count": 1, "window_seconds": 86400},
            {"name": "week", "type": "week", "count": 1, "window_seconds": 604800},
            {"name": "month", "type": "month", "count": 1, "window_seconds": None},
            {"name": "year", "type": "year", "count": 1, "window_seconds": None},
        ])
        return timeframes

    def process_trade(self, trade: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.metrics["trade_count"] += 1
        if not all(k in trade for k in ["symbol", "price", "volume", "timestamp"]):
            return []
        symbol = trade["symbol"]
        price = float(trade["price"])
        volume = float(trade["volume"])
        timestamp = int(trade["timestamp"])
        closed_candles = []
        for tf_config in self.timeframes:
            tf_name = tf_config["name"]
            tf_type = tf_config["type"]
            candle = self._update_candle(
                symbol=symbol,
                timeframe=tf_name,
                tf_type=tf_type,
                tf_config=tf_config,
                price=price,
                volume=volume,
                timestamp=timestamp,
            )
            if candle and candle.get("is_closed"):
                closed_candles.append(candle)
                self.metrics["closed_candle_count"] += 1
        return closed_candles

    def _update_candle(
        self,
        symbol: str,
        timeframe: str,
        tf_type: str,
        tf_config: Dict[str, Any],
        price: float,
        volume: float,
        timestamp: int,
    ) -> Optional[Dict[str, Any]]:
        key = (symbol, timeframe)
        state = self.candle_states[key]
        candle_time = self._get_candle_time(timestamp, tf_type, tf_config)
        if not state or state.get("t") != candle_time:
            closed_candle = None
            if state and state.get("t"):
                closed_candle = self._finalize_candle(state, symbol, timeframe)
            state = {"t": candle_time, "o": price, "h": price, "l": price, "c": price, "v": volume, "trade_count": 1, "is_closed": False}
            self.candle_states[key] = state
            if closed_candle:
                return closed_candle
        else:
            state["h"] = max(state["h"], price)
            state["l"] = min(state["l"], price)
            state["c"] = price
            state["v"] += volume
            state["trade_count"] += 1
        return None

    def _get_candle_time(self, timestamp: int, tf_type: str, tf_config: Dict[str, Any]) -> int:
        dt_utc = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
        dt_kst = dt_utc.astimezone(KST)
        if tf_type == "tick":
            return timestamp
        elif tf_type == "second":
            seconds = tf_config["count"]
            aligned = (timestamp // seconds) * seconds
            return aligned
        elif tf_type == "minute":
            minutes = tf_config["count"]
            aligned = dt_kst.replace(second=0, microsecond=0)
            aligned = aligned.replace(minute=(aligned.minute // minutes) * minutes)
            return int(aligned.timestamp())
        elif tf_type == "hour":
            hours = tf_config["count"]
            aligned = dt_kst.replace(minute=0, second=0, microsecond=0)
            aligned = aligned.replace(hour=(aligned.hour // hours) * hours)
            return int(aligned.timestamp())
        elif tf_type == "day":
            aligned = dt_kst.replace(hour=0, minute=0, second=0, microsecond=0)
            return int(aligned.timestamp())
        elif tf_type == "week":
            aligned = dt_kst.replace(hour=0, minute=0, second=0, microsecond=0)
            aligned = aligned - timedelta(days=aligned.weekday())
            return int(aligned.timestamp())
        elif tf_type == "month":
            aligned = dt_kst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return int(aligned.timestamp())
        elif tf_type == "year":
            aligned = dt_kst.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return int(aligned.timestamp())
        return timestamp

    def _finalize_candle(self, state: Dict[str, Any], symbol: str, timeframe: str) -> Dict[str, Any]:
        candle = {
            "exchange": self.exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "t": state["t"],
            "o": state["o"],
            "h": state["h"],
            "l": state["l"],
            "c": state["c"],
            "v": state["v"],
            "trade_count": state["trade_count"],
            "is_closed": True,
            "ts": int(time.time() * 1000),
        }
        self.metrics["candle_count"] += 1
        return candle

    def get_current_candles(self) -> List[Dict[str, Any]]:
        candles = []
        for (symbol, timeframe), state in self.candle_states.items():
            if state and not state.get("is_closed"):
                candles.append(
                    {
                        "exchange": self.exchange,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "t": state["t"],
                        "o": state["o"],
                        "h": state["h"],
                        "l": state["l"],
                        "c": state["c"],
                        "v": state["v"],
                        "trade_count": state["trade_count"],
                        "is_closed": False,
                    }
                )
        return candles

    def get_metrics(self) -> Dict[str, int]:
        return {**self.metrics, "active_candles": len(self.candle_states), "timeframes": len(self.timeframes)}


# Test harness (uses logger instead of print)
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("[CandleAggregator] Unit Test")
    logger.info("=" * 60)

    aggregator = CandleAggregator(exchange="upbit")

    base_timestamp = int(datetime(2026, 1, 24, 12, 0, 0, tzinfo=KST).timestamp())

    trades = [
        {"symbol": "KRW-BTC", "price": 50000000, "volume": 0.1, "timestamp": base_timestamp},
        {"symbol": "KRW-BTC", "price": 50100000, "volume": 0.2, "timestamp": base_timestamp + 30},
        {"symbol": "KRW-BTC", "price": 49900000, "volume": 0.15, "timestamp": base_timestamp + 60},
        {"symbol": "KRW-BTC", "price": 50050000, "volume": 0.3, "timestamp": base_timestamp + 90},
    ]

    logger.info("\n[Test] Processing trades...")
    for i, trade in enumerate(trades):
        logger.info("Trade #%d: price=%s, volume=%s, ts=%s", i + 1, trade["price"], trade["volume"], trade["timestamp"])
        closed_candles = aggregator.process_trade(trade)
        if closed_candles:
            logger.info("  ✅ Closed %d candles:", len(closed_candles))
            for candle in closed_candles:
                logger.info(
                    "    - %s %s: O=%s, H=%s, L=%s, C=%s, V=%s",
                    candle["symbol"],
                    candle["timeframe"],
                    candle["o"],
                    candle["h"],
                    candle["l"],
                    candle["c"],
                    candle["v"],
                )

    logger.info("\n" + "=" * 60)
    logger.info("[Metrics]")
    metrics = aggregator.get_metrics()
    for key, value in metrics.items():
        logger.info("  %s: %s", key, value)
    logger.info("=" * 60)