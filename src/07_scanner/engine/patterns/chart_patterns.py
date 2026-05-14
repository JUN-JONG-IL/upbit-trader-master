"""
[Purpose]
- 차트 패턴 감지 (Triangle, Double Top/Bottom, Head & Shoulders, Flag)

[Responsibilities]
- 여러 봉에 걸친 차트 패턴 감지
- 패턴 강도(confidence) 반환
- 패턴 탐지 기간(lookback) 매개변수 지원

[Dependencies]
- pandas: 시계열 데이터 처리
- numpy: 수치 계산

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _find_local_peaks(series: pd.Series, window: int = 5) -> pd.Series:
    """로컬 피크(고점) 인덱스 반환."""
    peaks = pd.Series(False, index=series.index)
    for i in range(window, len(series) - window):
        if series.iloc[i] == series.iloc[i - window:i + window + 1].max():
            peaks.iloc[i] = True
    return peaks


def _find_local_troughs(series: pd.Series, window: int = 5) -> pd.Series:
    """로컬 저점 인덱스 반환."""
    troughs = pd.Series(False, index=series.index)
    for i in range(window, len(series) - window):
        if series.iloc[i] == series.iloc[i - window:i + window + 1].min():
            troughs.iloc[i] = True
    return troughs


def detect_triangle(
    high: pd.Series,
    low: pd.Series,
    period: int = 30,
) -> bool:
    """
    삼각수렴 패턴 감지 (고점 하락 + 저점 상승).

    Args:
        high: 고가 시계열
        low: 저가 시계열
        period: 탐색 기간 (기본값: 30)

    Returns:
        삼각수렴 패턴 감지 여부

    Examples:
        >>> is_triangle = detect_triangle(df['high'], df['low'], 30)
    """
    if len(high) < period:
        return False
    h = high.iloc[-period:]
    l = low.iloc[-period:]
    # 단순: 고점이 우하향, 저점이 우상향
    high_slope = np.polyfit(range(len(h)), h.values, 1)[0]
    low_slope = np.polyfit(range(len(l)), l.values, 1)[0]
    return bool(high_slope < 0 and low_slope > 0)


def detect_double_top(
    close: pd.Series,
    period: int = 50,
    tolerance: float = 0.02,
) -> bool:
    """
    더블탑 패턴 감지 (두 고점이 비슷한 수준).

    Args:
        close: 종가 시계열
        period: 탐색 기간 (기본값: 50)
        tolerance: 두 고점 차이 허용 비율 (기본값: 0.02)

    Returns:
        더블탑 패턴 감지 여부

    Examples:
        >>> is_double_top = detect_double_top(df['close'], 50)
    """
    if len(close) < period:
        return False
    series = close.iloc[-period:]
    peaks = _find_local_peaks(series)
    peak_vals = series[peaks].values
    if len(peak_vals) < 2:
        return False
    top1, top2 = peak_vals[-2], peak_vals[-1]
    return bool(abs(top1 - top2) / max(top1, top2) <= tolerance and close.iloc[-1] < min(top1, top2))


def detect_double_bottom(
    close: pd.Series,
    period: int = 50,
    tolerance: float = 0.02,
) -> bool:
    """
    더블바텀 패턴 감지 (두 저점이 비슷한 수준).

    Args:
        close: 종가 시계열
        period: 탐색 기간 (기본값: 50)
        tolerance: 두 저점 차이 허용 비율 (기본값: 0.02)

    Returns:
        더블바텀 패턴 감지 여부

    Examples:
        >>> is_double_bottom = detect_double_bottom(df['close'], 50)
    """
    if len(close) < period:
        return False
    series = close.iloc[-period:]
    troughs = _find_local_troughs(series)
    trough_vals = series[troughs].values
    if len(trough_vals) < 2:
        return False
    bot1, bot2 = trough_vals[-2], trough_vals[-1]
    return bool(abs(bot1 - bot2) / max(bot1, bot2) <= tolerance and close.iloc[-1] > max(bot1, bot2))


def detect_head_and_shoulders(
    close: pd.Series,
    period: int = 60,
    tolerance: float = 0.03,
) -> bool:
    """
    Head & Shoulders 패턴 감지 (헤드가 두 숄더보다 높음).

    Args:
        close: 종가 시계열
        period: 탐색 기간 (기본값: 60)
        tolerance: 어깨 높이 차이 허용 비율 (기본값: 0.03)

    Returns:
        Head & Shoulders 패턴 감지 여부

    Examples:
        >>> is_hs = detect_head_and_shoulders(df['close'], 60)
    """
    if len(close) < period:
        return False
    series = close.iloc[-period:]
    peaks = _find_local_peaks(series)
    peak_vals = series[peaks].values
    if len(peak_vals) < 3:
        return False
    s1, head, s2 = peak_vals[-3], peak_vals[-2], peak_vals[-1]
    # 헤드가 가장 높고, 두 숄더 높이가 비슷
    return bool(
        head > s1 and head > s2
        and abs(s1 - s2) / max(s1, s2) <= tolerance
    )


def detect_flag(
    close: pd.Series,
    period: int = 20,
    pole_period: int = 5,
    flag_slope_max: float = 0.01,
) -> bool:
    """
    Flag 패턴 감지 (강한 추세 후 횡보 or 약한 반등).

    Args:
        close: 종가 시계열
        period: 기 부분(flag body) 탐색 기간 (기본값: 20)
        pole_period: 폴(pole) 기간 (기본값: 5)
        flag_slope_max: 기 부분 최대 기울기 비율 (기본값: 0.01)

    Returns:
        Flag 패턴 감지 여부

    Examples:
        >>> is_flag = detect_flag(df['close'], 20)
    """
    if len(close) < period + pole_period:
        return False
    # 폴: 강한 상승
    pole = close.iloc[-(period + pole_period):-period]
    flag = close.iloc[-period:]
    if len(pole) < 2 or len(flag) < 2:
        return False
    pole_change = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]
    flag_slope = np.polyfit(range(len(flag)), flag.values, 1)[0] / flag.mean()
    return bool(pole_change > 0.05 and abs(flag_slope) <= flag_slope_max)
