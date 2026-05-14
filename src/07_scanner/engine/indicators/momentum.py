"""
[Purpose]
- 모멘텀 관련 기술 지표 계산 (RSI, Stochastic, CCI)

[Responsibilities]
- RSI (Relative Strength Index) 계산
- Stochastic Oscillator (%K, %D) 계산
- CCI (Commodity Channel Index) 계산

[Dependencies]
- pandas: 시계열 데이터 처리
- numpy: 수치 계산

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index) 계산.

    Args:
        series: 종가 시계열
        period: RSI 기간 (기본값: 14)

    Returns:
        RSI 시계열 (0~100)

    Raises:
        ValueError: period가 2 미만인 경우

    Examples:
        >>> rsi = calc_rsi(df['close'], 14)
        >>> latest_rsi = rsi.iloc[-1]
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def calc_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> Tuple[pd.Series, pd.Series]:
    """
    Stochastic Oscillator (%K, %D) 계산.

    Args:
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        k_period: %K 기간 (기본값: 14)
        d_period: %D 기간 (기본값: 3)
        smooth_k: %K 스무딩 기간 (기본값: 3)

    Returns:
        (stoch_k, stoch_d) 튜플 (각각 0~100)

    Examples:
        >>> k, d = calc_stochastic(df['high'], df['low'], df['close'])
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    raw_k = 100.0 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    stoch_k = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean()
    stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean()
    return stoch_k.fillna(50.0), stoch_d.fillna(50.0)


def calc_cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """
    CCI (Commodity Channel Index) 계산.

    Args:
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        period: CCI 기간 (기본값: 20)

    Returns:
        CCI 시계열

    Examples:
        >>> cci = calc_cci(df['high'], df['low'], df['close'], 20)
    """
    typical_price = (high + low + close) / 3.0
    ma_tp = typical_price.rolling(window=period, min_periods=period).mean()
    mean_dev = typical_price.rolling(window=period, min_periods=period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )
    cci = (typical_price - ma_tp) / (0.015 * mean_dev.replace(0, np.nan))
    return cci.fillna(0.0)
