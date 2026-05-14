#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FeatureEngineer - Shared Feature Engineering Utilities

Computes technical indicators and market micro-structure features from
OHLCV data.  Provides a unified interface used by all AI/ML models.

Supports:
- Trend indicators: SMA, EMA
- Momentum: RSI, MACD, Stochastic
- Volatility: Bollinger Bands, ATR
- Volume: OBV, Volume Ratio
- Time: hour-of-day, day-of-week (cyclical encoding)
- Order-book proxies: bid-ask spread, depth imbalance
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False


class FeatureEngineer:
    """
    Reusable feature engineering for AI/ML trading models.

    All methods accept and return numpy arrays for framework-agnostic
    compatibility.  pandas DataFrames are supported as input and are
    converted internally when available.

    Example::

        fe = FeatureEngineer()
        features, names = fe.build_features(open_, high, low, close, volume)
    """

    def __init__(self, include_time_features: bool = True):
        """
        Args:
            include_time_features: If True, append cyclical time
                encodings (requires timestamps to be passed separately).
        """
        self.include_time_features = include_time_features

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_features(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: Optional[np.ndarray] = None,
        timestamps: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Build a feature matrix from OHLCV data.

        Args:
            open_: Open prices.
            high: High prices.
            low: Low prices.
            close: Close prices.
            volume: Volume (optional).
            timestamps: Unix timestamps in seconds (optional, for time features).

        Returns:
            Tuple of (feature_matrix, feature_names).
            feature_matrix shape: (N, n_features).
        """
        open_ = np.asarray(open_, dtype=np.float64)
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        n = len(close)

        features: List[np.ndarray] = []
        names: List[str] = []

        # --- Price-derived ---
        features.append(close.reshape(-1, 1))
        names.append("close")

        # Returns
        returns = np.zeros(n)
        returns[1:] = np.diff(close) / (close[:-1] + 1e-10)
        features.append(returns.reshape(-1, 1))
        names.append("return_1")

        # --- Trend ---
        for p in (5, 10, 20, 50):
            sma = self.sma(close, p)
            ema = self.ema(close, p)
            features.extend([sma.reshape(-1, 1), ema.reshape(-1, 1)])
            names.extend([f"sma_{p}", f"ema_{p}"])

        # --- Momentum ---
        rsi = self.rsi(close, 14)
        features.append(rsi.reshape(-1, 1))
        names.append("rsi_14")

        macd_line, signal_line, hist = self.macd(close)
        features.extend([
            macd_line.reshape(-1, 1),
            signal_line.reshape(-1, 1),
            hist.reshape(-1, 1),
        ])
        names.extend(["macd", "macd_signal", "macd_hist"])

        stoch_k, stoch_d = self.stochastic(high, low, close)
        features.extend([stoch_k.reshape(-1, 1), stoch_d.reshape(-1, 1)])
        names.extend(["stoch_k", "stoch_d"])

        # --- Volatility ---
        bb_upper, bb_middle, bb_lower = self.bollinger_bands(close)
        bb_width = (bb_upper - bb_lower) / (bb_middle + 1e-10)
        features.extend([
            bb_upper.reshape(-1, 1),
            bb_lower.reshape(-1, 1),
            bb_width.reshape(-1, 1),
        ])
        names.extend(["bb_upper", "bb_lower", "bb_width"])

        atr = self.atr(high, low, close)
        features.append(atr.reshape(-1, 1))
        names.append("atr_14")

        # --- Candle geometry ---
        body = np.abs(close - open_) / (high - low + 1e-10)
        features.append(body.reshape(-1, 1))
        names.append("candle_body_ratio")

        hl_range = (high - low) / (close + 1e-10)
        features.append(hl_range.reshape(-1, 1))
        names.append("hl_range_pct")

        # --- Volume ---
        if volume is not None:
            volume = np.asarray(volume, dtype=np.float64)
            vol_sma20 = self.sma(volume, 20)
            vol_ratio = volume / (vol_sma20 + 1e-10)
            features.extend([volume.reshape(-1, 1), vol_ratio.reshape(-1, 1)])
            names.extend(["volume", "volume_ratio"])

            obv = self.obv(close, volume)
            features.append(obv.reshape(-1, 1))
            names.append("obv")

        # --- Time features ---
        if self.include_time_features and timestamps is not None:
            time_feats, time_names = self.time_features(timestamps)
            features.append(time_feats)
            names.extend(time_names)

        matrix = np.hstack(features).astype(np.float32)
        # Replace NaN/Inf with 0
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        return matrix, names

    # ------------------------------------------------------------------
    # Indicator calculations
    # ------------------------------------------------------------------

    @staticmethod
    def sma(data: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average."""
        result = np.zeros_like(data)
        for i in range(len(data)):
            start = max(0, i - period + 1)
            result[i] = data[start: i + 1].mean()
        return result

    @staticmethod
    def ema(data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average."""
        result = np.zeros_like(data)
        alpha = 2.0 / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    @classmethod
    def rsi(cls, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index."""
        n = len(close)
        result = np.full(n, 50.0)
        if n < period + 1:
            return result
        delta = np.diff(close)
        gains = np.where(delta > 0, delta, 0.0)
        losses = np.where(delta < 0, -delta, 0.0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        for i in range(period, n - 1):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / (avg_loss + 1e-10)
            result[i + 1] = 100 - (100 / (1 + rs))
        return result

    @classmethod
    def macd(
        cls,
        close: np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD line, signal line, histogram."""
        ema_fast = cls.ema(close, fast)
        ema_slow = cls.ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = cls.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(
        close: np.ndarray, period: int = 20, std_dev: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Bollinger Bands: upper, middle, lower."""
        n = len(close)
        upper = np.zeros(n)
        middle = np.zeros(n)
        lower = np.zeros(n)
        for i in range(n):
            window = close[max(0, i - period + 1): i + 1]
            m = window.mean()
            s = window.std()
            middle[i] = m
            upper[i] = m + std_dev * s
            lower[i] = m - std_dev * s
        return upper, middle, lower

    @staticmethod
    def atr(
        high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> np.ndarray:
        """Average True Range."""
        n = len(close)
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        atr_arr = np.zeros(n)
        atr_arr[0] = tr[0]
        alpha = 1.0 / period
        for i in range(1, n):
            atr_arr[i] = alpha * tr[i] + (1 - alpha) * atr_arr[i - 1]
        return atr_arr

    @staticmethod
    def stochastic(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        k_period: int = 14,
        d_period: int = 3,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Stochastic Oscillator (%K, %D)."""
        n = len(close)
        k = np.zeros(n)
        for i in range(k_period - 1, n):
            window_high = high[i - k_period + 1: i + 1].max()
            window_low = low[i - k_period + 1: i + 1].min()
            denom = window_high - window_low
            k[i] = 100 * (close[i] - window_low) / (denom + 1e-10)
        # %D = SMA(%K, d_period)
        d = np.convolve(k, np.ones(d_period) / d_period, mode="same")
        return k, d

    @staticmethod
    def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """On-Balance Volume."""
        n = len(close)
        obv_arr = np.zeros(n)
        obv_arr[0] = volume[0]
        for i in range(1, n):
            if close[i] > close[i - 1]:
                obv_arr[i] = obv_arr[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv_arr[i] = obv_arr[i - 1] - volume[i]
            else:
                obv_arr[i] = obv_arr[i - 1]
        return obv_arr

    @staticmethod
    def time_features(timestamps: np.ndarray) -> Tuple[np.ndarray, List[str]]:
        """
        Encode timestamps as cyclical (sin/cos) features.

        Args:
            timestamps: Array of Unix timestamps (seconds).

        Returns:
            Feature matrix and list of feature names.
        """
        import datetime as dt
        hours = np.array([
            dt.datetime.utcfromtimestamp(float(ts)).hour
            for ts in timestamps
        ], dtype=np.float32)
        dow = np.array([
            dt.datetime.utcfromtimestamp(float(ts)).weekday()
            for ts in timestamps
        ], dtype=np.float32)

        hour_sin = np.sin(2 * np.pi * hours / 24)
        hour_cos = np.cos(2 * np.pi * hours / 24)
        dow_sin = np.sin(2 * np.pi * dow / 7)
        dow_cos = np.cos(2 * np.pi * dow / 7)

        matrix = np.column_stack([hour_sin, hour_cos, dow_sin, dow_cos])
        names = ["hour_sin", "hour_cos", "dow_sin", "dow_cos"]
        return matrix, names

    # ------------------------------------------------------------------
    # Sequence creation
    # ------------------------------------------------------------------

    @staticmethod
    def create_sequences(
        features: np.ndarray,
        targets: np.ndarray,
        seq_len: int,
        horizon: int = 1,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert a flat feature matrix into overlapping sequences for
        recurrent model training.

        Args:
            features: (N, n_features) matrix.
            targets: (N,) target array.
            seq_len: Sequence (look-back) length.
            horizon: Prediction horizon (steps ahead).

        Returns:
            (X, y) where X.shape == (samples, seq_len, n_features)
            and y.shape == (samples,).
        """
        X_list, y_list = [], []
        n = len(features)
        for i in range(seq_len, n - horizon + 1):
            X_list.append(features[i - seq_len: i])
            y_list.append(targets[i + horizon - 1])
        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)
