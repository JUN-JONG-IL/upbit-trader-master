"""
[Purpose]
- 추세 관련 기술 지표 계산 (MA, EMA, MACD)

[Responsibilities]
- 단순 이동 평균(MA) 계산
- 지수 이동 평균(EMA) 계산
- MACD 계산 및 시그널, 히스토그램 생성
- 골든크로스/데드크로스 감지

[Dependencies]
- pandas: 시계열 데이터 처리
- numpy: 수치 계산

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd


def calc_ma(series: pd.Series, period: int) -> pd.Series:
    """
    단순 이동 평균 계산.

    Args:
        series: 가격 시계열
        period: 이동 평균 기간

    Returns:
        이동 평균 시계열

    Raises:
        ValueError: period가 1 미만인 경우
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.rolling(window=period, min_periods=period).mean()


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """
    지수 이동 평균 계산.

    Args:
        series: 가격 시계열
        period: EMA 기간

    Returns:
        EMA 시계열

    Raises:
        ValueError: period가 1 미만인 경우
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.ewm(span=period, adjust=False).mean()


def calc_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD 계산.

    Args:
        series: 가격 시계열
        fast: 단기 EMA 기간 (기본값: 12)
        slow: 장기 EMA 기간 (기본값: 26)
        signal: 시그널 EMA 기간 (기본값: 9)

    Returns:
        (macd_line, signal_line, histogram) 튜플

    Raises:
        ValueError: fast >= slow인 경우
    """
    if fast >= slow:
        raise ValueError(f"fast ({fast}) must be < slow ({slow})")
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def detect_golden_cross(
    series: pd.Series,
    short_period: int = 5,
    long_period: int = 20,
) -> bool:
    """
    골든크로스 감지 (단기 MA가 장기 MA를 상향 돌파).

    Args:
        series: 가격 시계열
        short_period: 단기 MA 기간
        long_period: 장기 MA 기간

    Returns:
        골든크로스 발생 여부

    Examples:
        >>> detected = detect_golden_cross(df['close'], 5, 20)
    """
    if len(series) < long_period + 1:
        return False
    ma_short = calc_ma(series, short_period)
    ma_long = calc_ma(series, long_period)
    # 이전 봉에서 단기 < 장기, 현재 봉에서 단기 > 장기
    return bool(
        pd.notna(ma_short.iloc[-2]) and pd.notna(ma_long.iloc[-2])
        and pd.notna(ma_short.iloc[-1]) and pd.notna(ma_long.iloc[-1])
        and ma_short.iloc[-2] < ma_long.iloc[-2]
        and ma_short.iloc[-1] > ma_long.iloc[-1]
    )


def detect_dead_cross(
    series: pd.Series,
    short_period: int = 5,
    long_period: int = 20,
) -> bool:
    """
    데드크로스 감지 (단기 MA가 장기 MA를 하향 돌파).

    Args:
        series: 가격 시계열
        short_period: 단기 MA 기간
        long_period: 장기 MA 기간

    Returns:
        데드크로스 발생 여부

    Examples:
        >>> detected = detect_dead_cross(df['close'], 5, 20)
    """
    if len(series) < long_period + 1:
        return False
    ma_short = calc_ma(series, short_period)
    ma_long = calc_ma(series, long_period)
    return bool(
        pd.notna(ma_short.iloc[-2]) and pd.notna(ma_long.iloc[-2])
        and pd.notna(ma_short.iloc[-1]) and pd.notna(ma_long.iloc[-1])
        and ma_short.iloc[-2] > ma_long.iloc[-2]
        and ma_short.iloc[-1] < ma_long.iloc[-1]
    )
