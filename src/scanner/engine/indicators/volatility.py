"""
[Purpose]
- 변동성 관련 기술 지표 계산 (Bollinger Bands, ATR)

[Responsibilities]
- Bollinger Bands (상단, 중간, 하단) 계산
- ATR (Average True Range) 계산
- Bollinger Bands 수축/팽창 감지

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


def calc_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands 계산.

    Args:
        series: 종가 시계열
        period: 중간 밴드 이동 평균 기간 (기본값: 20)
        std_dev: 표준 편차 승수 (기본값: 2.0)

    Returns:
        (upper, middle, lower) 밴드 튜플

    Examples:
        >>> upper, mid, lower = calc_bollinger_bands(df['close'])
        >>> touching_lower = df['close'].iloc[-1] <= lower.iloc[-1]
    """
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


def calc_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    ATR (Average True Range) 계산.

    Args:
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        period: ATR 기간 (기본값: 14)

    Returns:
        ATR 시계열

    Examples:
        >>> atr = calc_atr(df['high'], df['low'], df['close'], 14)
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=period - 1, adjust=False).mean()
    return atr


def detect_bb_squeeze(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
    squeeze_threshold: float = 0.1,
) -> bool:
    """
    Bollinger Bands 수축(squeeze) 감지.

    밴드폭이 최근 N 봉의 최솟값에 가까울 때 수축 상태로 판단.

    Args:
        series: 종가 시계열
        period: BB 기간
        std_dev: 표준 편차 승수
        squeeze_threshold: 수축 판단 임계값 (밴드폭 / 중간값 비율)

    Returns:
        수축 상태 여부

    Examples:
        >>> is_squeeze = detect_bb_squeeze(df['close'])
    """
    if len(series) < period:
        return False
    upper, middle, lower = calc_bollinger_bands(series, period, std_dev)
    if pd.isna(upper.iloc[-1]) or pd.isna(middle.iloc[-1]) or middle.iloc[-1] == 0:
        return False
    bandwidth = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1]
    return bool(bandwidth < squeeze_threshold)
