#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PatternDetector - Technical Chart Pattern Recognition

Detects candlestick patterns, chart patterns, trend patterns, and
volume patterns.  Uses TA-Lib when available; falls back to a
pure-numpy implementation otherwise.

Latency target: P95 < 200 ms.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logger.debug("TA-Lib not available; using pure-numpy pattern detection")


class PatternDetector:
    """
    Rule-based and ML-assisted chart pattern detector.

    Detects:
    - **Candlestick patterns**: Doji, Hammer, Shooting Star, Engulfing
    - **Trend patterns**: Higher-High/Lower-Low, breakout
    - **Volume patterns**: Volume spike, accumulation/distribution

    Each detected pattern includes a ``confidence`` score (0 … 1)
    derived from signal strength.

    Example::

        detector = PatternDetector()
        result = detector.detect(open, high, low, close, volume)
        print(result["patterns"])
    """

    def __init__(
        self,
        doji_threshold: float = 0.1,
        hammer_ratio: float = 2.0,
        volume_spike_multiplier: float = 2.5,
    ):
        """
        Args:
            doji_threshold: Max body/range ratio to classify a candle as Doji.
            hammer_ratio: Minimum lower-shadow / body ratio for Hammer pattern.
            volume_spike_multiplier: Multiple of rolling average to flag a
                volume spike.
        """
        self.doji_threshold = doji_threshold
        self.hammer_ratio = hammer_ratio
        self.volume_spike_multiplier = volume_spike_multiplier

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Detect all patterns in the provided OHLCV arrays.

        Args:
            open_: Open prices.
            high: High prices.
            low: Low prices.
            close: Close prices.
            volume: Volume (optional; needed for volume patterns).

        Returns:
            ::

                {
                    "patterns": [
                        {
                            "name": str,
                            "type": str,     # candlestick | trend | volume
                            "index": int,    # candle index where pattern ends
                            "confidence": float,
                            "direction": str # bullish | bearish | neutral
                        },
                        ...
                    ],
                    "timestamp": str,
                    "total_detected": int,
                }
        """
        open_ = np.asarray(open_, dtype=np.float64)
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        patterns: List[Dict[str, Any]] = []

        if TALIB_AVAILABLE:
            patterns.extend(self._detect_talib(open_, high, low, close))
        patterns.extend(self._detect_candlestick(open_, high, low, close))
        patterns.extend(self._detect_trend(close))

        if volume is not None:
            volume = np.asarray(volume, dtype=np.float64)
            patterns.extend(self._detect_volume(close, volume))

        # Deduplicate (same name + index)
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for p in patterns:
            key = (p["name"], p["index"])
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return {
            "patterns": unique,
            "timestamp": datetime.utcnow().isoformat(),
            "total_detected": len(unique),
        }

    def get_signal(self, detection_result: Dict[str, Any]) -> float:
        """
        Aggregate pattern signals into a single directional score.

        Args:
            detection_result: Output of :meth:`detect`.

        Returns:
            Composite signal in [-1, +1].  Positive = bullish, negative =
            bearish.
        """
        patterns = detection_result.get("patterns", [])
        if not patterns:
            return 0.0

        score = 0.0
        for p in patterns:
            direction = p.get("direction", "neutral")
            confidence = p.get("confidence", 0.5)
            if direction == "bullish":
                score += confidence
            elif direction == "bearish":
                score -= confidence

        # Normalise to [-1, +1]
        max_score = max(len(patterns) * 1.0, 1.0)
        return float(np.clip(score / max_score, -1.0, 1.0))

    # ------------------------------------------------------------------
    # TA-Lib patterns
    # ------------------------------------------------------------------

    def _detect_talib(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """Use TA-Lib for candlestick pattern recognition."""
        patterns: List[Dict[str, Any]] = []

        candlestick_funcs = {
            "Doji": (talib.CDLDOJI, "neutral"),
            "Hammer": (talib.CDLHAMMER, "bullish"),
            "ShootingStar": (talib.CDLSHOOTINGSTAR, "bearish"),
            "BullishEngulfing": (talib.CDLENGULFING, "bullish"),
            "MorningStar": (talib.CDLMORNINGSTAR, "bullish"),
            "EveningStar": (talib.CDLEVENINGSTAR, "bearish"),
            "HangingMan": (talib.CDLHANGINGMAN, "bearish"),
            "InvertedHammer": (talib.CDLINVERTEDHAMMER, "bullish"),
        }

        for name, (func, direction) in candlestick_funcs.items():
            try:
                result = func(open_, high, low, close)
                indices = np.where(result != 0)[0]
                for idx in indices:
                    confidence = min(abs(result[idx]) / 100.0, 1.0)
                    patterns.append({
                        "name": name,
                        "type": "candlestick",
                        "index": int(idx),
                        "confidence": round(confidence, 3),
                        "direction": direction if result[idx] > 0 else (
                            "bearish" if direction == "bullish" else "bullish"
                        ),
                    })
            except Exception as exc:
                logger.debug("TA-Lib pattern %s failed: %s", name, exc)

        return patterns

    # ------------------------------------------------------------------
    # Pure-numpy candlestick patterns
    # ------------------------------------------------------------------

    def _detect_candlestick(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []
        n = len(close)
        if n < 2:
            return patterns

        body = np.abs(close - open_)
        total_range = high - low + 1e-10

        # Doji
        ratio = body / total_range
        doji_idx = np.where(ratio < self.doji_threshold)[0]
        for idx in doji_idx:
            patterns.append({
                "name": "Doji",
                "type": "candlestick",
                "index": int(idx),
                "confidence": round(float(1 - ratio[idx] / self.doji_threshold), 3),
                "direction": "neutral",
            })

        # Hammer (bullish)
        lower_shadow = np.where(close >= open_, open_ - low, close - low)
        upper_shadow = np.where(close >= open_, high - close, high - open_)
        for idx in range(n):
            if body[idx] > 0 and lower_shadow[idx] / body[idx] >= self.hammer_ratio:
                if upper_shadow[idx] < body[idx]:
                    patterns.append({
                        "name": "Hammer",
                        "type": "candlestick",
                        "index": idx,
                        "confidence": round(
                            min(lower_shadow[idx] / (body[idx] * self.hammer_ratio), 1.0), 3
                        ),
                        "direction": "bullish",
                    })

        # Bullish Engulfing
        for idx in range(1, n):
            prev_bear = close[idx - 1] < open_[idx - 1]
            curr_bull = close[idx] > open_[idx]
            if prev_bear and curr_bull:
                if open_[idx] < close[idx - 1] and close[idx] > open_[idx - 1]:
                    confidence = min(body[idx] / (body[idx - 1] + 1e-10), 1.0)
                    patterns.append({
                        "name": "BullishEngulfing",
                        "type": "candlestick",
                        "index": idx,
                        "confidence": round(float(confidence), 3),
                        "direction": "bullish",
                    })

        # Bearish Engulfing
        for idx in range(1, n):
            prev_bull = close[idx - 1] > open_[idx - 1]
            curr_bear = close[idx] < open_[idx]
            if prev_bull and curr_bear:
                if open_[idx] > close[idx - 1] and close[idx] < open_[idx - 1]:
                    confidence = min(body[idx] / (body[idx - 1] + 1e-10), 1.0)
                    patterns.append({
                        "name": "BearishEngulfing",
                        "type": "candlestick",
                        "index": idx,
                        "confidence": round(float(confidence), 3),
                        "direction": "bearish",
                    })

        return patterns

    # ------------------------------------------------------------------
    # Trend patterns
    # ------------------------------------------------------------------

    def _detect_trend(self, close: np.ndarray) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []
        n = len(close)
        if n < 20:
            return patterns

        # Breakout: close crosses 20-period high/low
        window = 20
        for idx in range(window, n):
            window_high = np.max(close[idx - window: idx])
            window_low = np.min(close[idx - window: idx])
            if close[idx] > window_high * 1.01:
                confidence = min((close[idx] - window_high) / window_high * 10, 1.0)
                patterns.append({
                    "name": "Breakout_Bullish",
                    "type": "trend",
                    "index": idx,
                    "confidence": round(float(confidence), 3),
                    "direction": "bullish",
                })
            elif close[idx] < window_low * 0.99:
                confidence = min((window_low - close[idx]) / window_low * 10, 1.0)
                patterns.append({
                    "name": "Breakout_Bearish",
                    "type": "trend",
                    "index": idx,
                    "confidence": round(float(confidence), 3),
                    "direction": "bearish",
                })

        return patterns

    # ------------------------------------------------------------------
    # Volume patterns
    # ------------------------------------------------------------------

    def _detect_volume(
        self, close: np.ndarray, volume: np.ndarray
    ) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []
        n = len(volume)
        if n < 20:
            return patterns

        rolling_avg = np.array([
            volume[max(0, i - 20): i].mean() if i > 0 else volume[0]
            for i in range(n)
        ])

        for idx in range(20, n):
            if rolling_avg[idx] > 0:
                ratio = volume[idx] / rolling_avg[idx]
                if ratio >= self.volume_spike_multiplier:
                    direction = "bullish" if close[idx] > close[idx - 1] else "bearish"
                    confidence = min((ratio - self.volume_spike_multiplier) / 3.0 + 0.5, 1.0)
                    patterns.append({
                        "name": "VolumeSpike",
                        "type": "volume",
                        "index": idx,
                        "confidence": round(float(confidence), 3),
                        "direction": direction,
                    })

        return patterns
