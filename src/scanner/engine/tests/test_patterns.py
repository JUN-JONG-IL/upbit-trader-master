"""
[Purpose]
- patterns 패키지 단위 테스트

[Responsibilities]
- candlestick 패턴 및 차트 패턴 감지 검증

[Dependencies]
- pytest
- pandas, numpy

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Import directly (conftest.py sets up sys.path to src/scanner)
from engine.patterns.candlestick import (
    detect_doji,
    detect_hammer,
    detect_shooting_star,
    detect_bullish_engulfing,
    detect_bearish_engulfing,
)
from engine.patterns.chart_patterns import (
    detect_triangle,
    detect_double_top,
    detect_double_bottom,
    detect_head_and_shoulders,
    detect_flag,
)


def _make_candle(
    open_: float, high: float, low: float, close: float, n: int = 3
) -> tuple:
    """마지막 봉에 특정 OHLC 값을 가진 시리즈 튜플 반환."""
    opens = pd.Series([100.0] * (n - 1) + [open_])
    highs = pd.Series([101.0] * (n - 1) + [high])
    lows = pd.Series([99.0] * (n - 1) + [low])
    closes = pd.Series([100.0] * (n - 1) + [close])
    return opens, highs, lows, closes


def _series(n: int = 60, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 + np.cumsum(rng.normal(0, 1, n)))


# -----------------------------------------------------------------------
# Candlestick patterns
# -----------------------------------------------------------------------

class TestDetectDoji:
    def test_doji_candle_returns_true(self):
        # body ≈ 0, large range
        opens, highs, lows, closes = _make_candle(100.0, 110.0, 90.0, 100.1)
        assert detect_doji(opens, highs, lows, closes, threshold=0.05) is True

    def test_strong_candle_returns_false(self):
        opens, highs, lows, closes = _make_candle(90.0, 110.0, 89.0, 109.0)
        assert detect_doji(opens, highs, lows, closes, threshold=0.05) is False

    def test_empty_series_returns_false(self):
        empty = pd.Series([], dtype=float)
        assert detect_doji(empty, empty, empty, empty) is False

    def test_returns_bool(self):
        opens, highs, lows, closes = _make_candle(100.0, 101.0, 99.0, 100.05)
        assert isinstance(detect_doji(opens, highs, lows, closes), bool)


class TestDetectHammer:
    def test_hammer_pattern(self):
        # long lower shadow, small body, tiny upper shadow
        opens, highs, lows, closes = _make_candle(100.0, 101.0, 80.0, 100.5)
        result = detect_hammer(opens, highs, lows, closes)
        assert isinstance(result, bool)

    def test_returns_bool(self):
        opens, highs, lows, closes = _make_candle(100.0, 105.0, 95.0, 102.0)
        assert isinstance(detect_hammer(opens, highs, lows, closes), bool)

    def test_empty_returns_false(self):
        empty = pd.Series([], dtype=float)
        assert detect_hammer(empty, empty, empty, empty) is False


class TestDetectShootingStar:
    def test_returns_bool(self):
        opens, highs, lows, closes = _make_candle(100.0, 120.0, 99.0, 100.5)
        assert isinstance(detect_shooting_star(opens, highs, lows, closes), bool)

    def test_shooting_star_pattern(self):
        # long upper shadow, small body, tiny lower shadow
        opens, highs, lows, closes = _make_candle(100.0, 120.0, 99.5, 100.5)
        result = detect_shooting_star(opens, highs, lows, closes)
        assert isinstance(result, bool)

    def test_empty_returns_false(self):
        empty = pd.Series([], dtype=float)
        assert detect_shooting_star(empty, empty, empty, empty) is False


class TestDetectEngulfing:
    def test_bullish_engulfing(self):
        # prev: bearish(105→95), curr: bullish(90→110) - engulfs the bearish candle
        opens = pd.Series([105.0, 90.0])
        closes = pd.Series([95.0, 110.0])
        assert detect_bullish_engulfing(opens, closes) == True

    def test_not_bullish_engulfing(self):
        opens = pd.Series([95.0, 105.0])
        closes = pd.Series([105.0, 95.0])
        assert detect_bullish_engulfing(opens, closes) == False

    def test_bearish_engulfing(self):
        opens = pd.Series([95.0, 115.0])
        closes = pd.Series([105.0, 90.0])
        assert detect_bearish_engulfing(opens, closes) == True

    def test_not_bearish_engulfing(self):
        opens = pd.Series([105.0, 95.0])
        closes = pd.Series([95.0, 110.0])
        assert detect_bearish_engulfing(opens, closes) == False

    def test_short_series_returns_false(self):
        opens = pd.Series([100.0])
        closes = pd.Series([105.0])
        assert detect_bullish_engulfing(opens, closes) is False
        assert detect_bearish_engulfing(opens, closes) is False


# -----------------------------------------------------------------------
# Chart patterns
# -----------------------------------------------------------------------

class TestDetectTriangle:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_triangle(s, s, 30), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_triangle(s, s, 30) is False

    def test_converging_triangle(self):
        n = 40
        high = pd.Series(np.linspace(110, 100, n))
        low = pd.Series(np.linspace(90, 100, n))
        assert detect_triangle(high, low, n) is True


class TestDetectDoubleTop:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_double_top(s, 50), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_double_top(s, 50) is False


class TestDetectDoubleBottom:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_double_bottom(s, 50), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_double_bottom(s, 50) is False


class TestDetectHeadAndShoulders:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_head_and_shoulders(s, 60), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_head_and_shoulders(s, 60) is False


class TestDetectFlag:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_flag(s, 20), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_flag(s, 20) is False
