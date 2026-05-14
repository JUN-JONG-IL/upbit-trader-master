"""
[Purpose]
- 거래량 관련 기술 지표 계산 (OBV, Volume MA)

[Responsibilities]
- OBV (On-Balance Volume) 계산
- 거래량 이동 평균 계산
- 거래량 급등/급감 감지

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


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    OBV (On-Balance Volume) 계산.

    Args:
        close: 종가 시계열
        volume: 거래량 시계열

    Returns:
        OBV 시계열

    Examples:
        >>> obv = calc_obv(df['close'], df['volume'])
        >>> obv_increasing = obv.iloc[-1] > obv.iloc[-5]
    """
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).cumsum()
    return obv


def calc_volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
    """
    거래량 이동 평균 계산.

    Args:
        volume: 거래량 시계열
        period: 이동 평균 기간 (기본값: 20)

    Returns:
        거래량 이동 평균 시계열

    Raises:
        ValueError: period가 1 미만인 경우

    Examples:
        >>> vol_ma = calc_volume_ma(df['volume'], 20)
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return volume.rolling(window=period, min_periods=period).mean()


def detect_volume_surge(
    volume: pd.Series,
    period: int = 20,
    ratio: float = 2.0,
) -> bool:
    """
    거래량 급등 감지.

    현재 봉의 거래량이 이동 평균의 ratio배 이상이면 급등으로 판단.

    Args:
        volume: 거래량 시계열
        period: 기준 이동 평균 기간 (기본값: 20)
        ratio: 급등 판단 배수 (기본값: 2.0)

    Returns:
        거래량 급등 여부

    Examples:
        >>> surging = detect_volume_surge(df['volume'], ratio=3.0)
    """
    if len(volume) < period + 1:
        return False
    vol_ma = calc_volume_ma(volume, period)
    avg = vol_ma.iloc[-1]
    current = volume.iloc[-1]
    if pd.isna(avg) or avg == 0:
        return False
    return bool(current >= avg * ratio)
