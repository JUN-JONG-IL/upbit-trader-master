"""
[Purpose]
- indicators 패키지 단위 테스트

[Responsibilities]
- trend, momentum, volatility, volume 지표 계산 검증

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

# Import directly (conftest.py sets up sys.path to src/07_scanner)
from engine.indicators.trend import (
    calc_ma, calc_ema, calc_macd,
    detect_golden_cross, detect_dead_cross,
)
from engine.indicators.momentum import calc_rsi, calc_stochastic, calc_cci
from engine.indicators.volatility import calc_bollinger_bands, calc_atr, detect_bb_squeeze
from engine.indicators.volume import calc_obv, calc_volume_ma, detect_volume_surge


def _series(n: int = 50, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 + np.cumsum(rng.normal(0, 1, n)))


def _ohlcv(n: int = 50, seed: int = 0):
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    high = np.maximum(open_, close) + rng.uniform(0, 1, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1, n)
    volume = rng.uniform(1000, 5000, n)
    return (
        pd.Series(open_),
        pd.Series(high),
        pd.Series(low),
        pd.Series(close),
        pd.Series(volume),
    )


# -----------------------------------------------------------------------
# Trend
# -----------------------------------------------------------------------

class TestCalcMA:
    def test_length_matches_input(self):
        s = _series()
        result = calc_ma(s, 5)
        assert len(result) == len(s)

    def test_first_n_minus_one_are_nan(self):
        s = _series(20)
        result = calc_ma(s, 5)
        assert result.iloc[:4].isna().all()

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            calc_ma(_series(), 0)

    def test_period_one_equals_input(self):
        s = _series()
        result = calc_ma(s, 1)
        pd.testing.assert_series_equal(result, s, check_names=False)


class TestCalcEMA:
    def test_length_matches_input(self):
        s = _series()
        result = calc_ema(s, 12)
        assert len(result) == len(s)

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            calc_ema(_series(), 0)


class TestCalcMACD:
    def test_returns_three_series(self):
        s = _series(60)
        macd, signal, hist = calc_macd(s)
        assert len(macd) == len(s)
        assert len(signal) == len(s)
        assert len(hist) == len(s)

    def test_fast_gte_slow_raises(self):
        with pytest.raises(ValueError):
            calc_macd(_series(), fast=26, slow=12)

    def test_histogram_is_macd_minus_signal(self):
        s = _series(60)
        macd, signal, hist = calc_macd(s)
        pd.testing.assert_series_equal(hist, macd - signal, check_names=False)


class TestGoldenDeadCross:
    def test_golden_cross_returns_bool(self):
        s = _series()
        assert isinstance(detect_golden_cross(s, 5, 20), bool)

    def test_dead_cross_returns_bool(self):
        s = _series()
        assert isinstance(detect_dead_cross(s, 5, 20), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_golden_cross(s, 5, 20) is False
        assert detect_dead_cross(s, 5, 20) is False


# -----------------------------------------------------------------------
# Momentum
# -----------------------------------------------------------------------

class TestCalcRSI:
    def test_values_in_0_100(self):
        s = _series()
        rsi = calc_rsi(s, 14)
        assert (rsi.dropna() >= 0).all() and (rsi.dropna() <= 100).all()

    def test_length_matches_input(self):
        s = _series()
        assert len(calc_rsi(s, 14)) == len(s)

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            calc_rsi(_series(), 1)


class TestCalcStochastic:
    def test_returns_two_series(self):
        _, high, low, close, _ = _ohlcv()
        k, d = calc_stochastic(high, low, close)
        assert len(k) == len(close)
        assert len(d) == len(close)

    def test_values_in_0_100(self):
        _, high, low, close, _ = _ohlcv()
        k, d = calc_stochastic(high, low, close)
        assert (k.dropna() >= 0).all() and (k.dropna() <= 100).all()


class TestCalcCCI:
    def test_returns_series(self):
        _, high, low, close, _ = _ohlcv()
        cci = calc_cci(high, low, close, 20)
        assert len(cci) == len(close)


# -----------------------------------------------------------------------
# Volatility
# -----------------------------------------------------------------------

class TestCalcBollingerBands:
    def test_returns_three_series(self):
        s = _series()
        upper, mid, lower = calc_bollinger_bands(s)
        assert len(upper) == len(s)

    def test_upper_ge_mid_ge_lower(self):
        s = _series()
        upper, mid, lower = calc_bollinger_bands(s)
        valid = upper.dropna()
        assert (upper.dropna() >= mid.dropna()).all()
        assert (mid.dropna() >= lower.dropna()).all()


class TestCalcATR:
    def test_length_matches_input(self):
        _, high, low, close, _ = _ohlcv()
        atr = calc_atr(high, low, close, 14)
        assert len(atr) == len(close)

    def test_values_non_negative(self):
        _, high, low, close, _ = _ohlcv()
        atr = calc_atr(high, low, close, 14)
        assert (atr.dropna() >= 0).all()


class TestDetectBBSqueeze:
    def test_returns_bool(self):
        s = _series()
        assert isinstance(detect_bb_squeeze(s), bool)

    def test_short_series_returns_false(self):
        s = _series(5)
        assert detect_bb_squeeze(s) is False


# -----------------------------------------------------------------------
# Volume
# -----------------------------------------------------------------------

class TestCalcOBV:
    def test_returns_series(self):
        _, _, _, close, volume = _ohlcv()
        obv = calc_obv(close, volume)
        assert len(obv) == len(close)


class TestCalcVolumeMA:
    def test_returns_series(self):
        _, _, _, _, volume = _ohlcv()
        vma = calc_volume_ma(volume, 20)
        assert len(vma) == len(volume)

    def test_invalid_period_raises(self):
        _, _, _, _, volume = _ohlcv()
        with pytest.raises(ValueError):
            calc_volume_ma(volume, 0)


class TestDetectVolumeSurge:
    def test_returns_bool(self):
        _, _, _, _, volume = _ohlcv()
        assert isinstance(detect_volume_surge(volume), bool)

    def test_high_ratio_returns_false(self):
        _, _, _, _, volume = _ohlcv()
        assert detect_volume_surge(volume, ratio=1_000_000) is False

    def test_zero_ratio_returns_true(self):
        _, _, _, _, volume = _ohlcv()
        assert detect_volume_surge(volume, ratio=0.0) is True
