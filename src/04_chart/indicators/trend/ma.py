"""
[Purpose]
이동평균 지표 (Moving Averages)

[Features]
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)
- WMA (Weighted Moving Average)
- VWAP (Volume-Weighted Average Price)

[Author] Phase 2 (mplchart 반영)
[Created] 2026-01-25
"""

import numpy as np
import pandas as pd


def sma(data: pd.Series, period: int = 20) -> pd.Series:
    """
    단순 이동평균 (Simple Moving Average)

    [Parameters]
    - data: 가격 데이터 (pd.Series)
    - period: 기간 (기본 20)

    [Returns]
    - pd.Series: SMA 값
    """
    return data.rolling(window=period).mean()


def ema(data: pd.Series, period: int = 20) -> pd.Series:
    """
    지수 이동평균 (Exponential Moving Average)

    [Parameters]
    - data: 가격 데이터
    - period: 기간

    [Returns]
    - pd.Series: EMA 값
    """
    return data.ewm(span=period, adjust=False).mean()


def wma(data: pd.Series, period: int = 20) -> pd.Series:
    """
    가중 이동평균 (Weighted Moving Average)

    [Parameters]
    - data: 가격 데이터
    - period: 기간

    [Returns]
    - pd.Series: WMA 값
    """
    weights = np.arange(1, period + 1)

    def weighted_mean(x):
        if len(x) < period:
            return np.nan
        return np.dot(x[-period:], weights) / weights.sum()

    return data.rolling(window=period).apply(weighted_mean, raw=True)
