"""
[Purpose]
- 캔들스틱 패턴 감지 (Doji, Hammer, Shooting Star, Engulfing)

[Responsibilities]
- 최신 캔들에서 주요 캔들스틱 패턴 감지
- 각 패턴의 신뢰도(confidence) 반환
- 패턴 매개변수 커스터마이징 지원

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


def detect_doji(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    threshold: float = 0.05,
) -> bool:
    """
    Doji 캔들 패턴 감지.

    몸통(|open-close|)이 전체 범위(high-low)의 threshold 비율 이하일 때 Doji로 판단.

    Args:
        open_: 시가 시계열
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        threshold: 몸통 비율 임계값 (기본값: 0.05)

    Returns:
        Doji 패턴 감지 여부

    Examples:
        >>> is_doji = detect_doji(df['open'], df['high'], df['low'], df['close'])
    """
    if len(close) < 1:
        return False
    body = abs(close.iloc[-1] - open_.iloc[-1])
    candle_range = high.iloc[-1] - low.iloc[-1]
    if candle_range == 0:
        return True
    return bool((body / candle_range) <= threshold)


def detect_hammer(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    body_ratio: float = 0.3,
    shadow_ratio: float = 2.0,
) -> bool:
    """
    Hammer 캔들 패턴 감지.

    아래 그림자가 몸통보다 2배 이상 길고, 위 그림자가 짧은 패턴.

    Args:
        open_: 시가 시계열
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        body_ratio: 몸통 비율 기준
        shadow_ratio: 아래 그림자 / 몸통 비율 기준

    Returns:
        Hammer 패턴 감지 여부

    Examples:
        >>> is_hammer = detect_hammer(df['open'], df['high'], df['low'], df['close'])
    """
    if len(close) < 1:
        return False
    o = open_.iloc[-1]
    h = high.iloc[-1]
    l = low.iloc[-1]
    c = close.iloc[-1]

    body = abs(c - o)
    candle_range = h - l
    if candle_range == 0 or body == 0:
        return False

    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    return bool(
        lower_shadow >= body * shadow_ratio
        and upper_shadow <= body * 0.5
        and body / candle_range <= body_ratio
    )


def detect_shooting_star(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    body_ratio: float = 0.3,
    shadow_ratio: float = 2.0,
) -> bool:
    """
    Shooting Star 캔들 패턴 감지.

    위 그림자가 몸통보다 2배 이상 길고, 아래 그림자가 짧은 패턴.

    Args:
        open_: 시가 시계열
        high: 고가 시계열
        low: 저가 시계열
        close: 종가 시계열
        body_ratio: 몸통 비율 기준
        shadow_ratio: 위 그림자 / 몸통 비율 기준

    Returns:
        Shooting Star 패턴 감지 여부

    Examples:
        >>> is_star = detect_shooting_star(df['open'], df['high'], df['low'], df['close'])
    """
    if len(close) < 1:
        return False
    o = open_.iloc[-1]
    h = high.iloc[-1]
    l = low.iloc[-1]
    c = close.iloc[-1]

    body = abs(c - o)
    candle_range = h - l
    if candle_range == 0 or body == 0:
        return False

    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    return bool(
        upper_shadow >= body * shadow_ratio
        and lower_shadow <= body * 0.5
        and body / candle_range <= body_ratio
    )


def detect_bullish_engulfing(
    open_: pd.Series,
    close: pd.Series,
) -> bool:
    """
    Bullish Engulfing 패턴 감지.

    현재 양봉 몸통이 이전 음봉 몸통을 완전히 포함하는 패턴.

    Args:
        open_: 시가 시계열
        close: 종가 시계열

    Returns:
        Bullish Engulfing 패턴 감지 여부

    Examples:
        >>> is_bull_eng = detect_bullish_engulfing(df['open'], df['close'])
    """
    if len(close) < 2:
        return False
    prev_o, prev_c = open_.iloc[-2], close.iloc[-2]
    curr_o, curr_c = open_.iloc[-1], close.iloc[-1]
    # 이전 봉이 음봉, 현재 봉이 양봉이며 완전히 포함
    return bool(
        prev_c < prev_o  # 이전 음봉
        and curr_c > curr_o  # 현재 양봉
        and curr_o < prev_c
        and curr_c > prev_o
    )


def detect_bearish_engulfing(
    open_: pd.Series,
    close: pd.Series,
) -> bool:
    """
    Bearish Engulfing 패턴 감지.

    현재 음봉 몸통이 이전 양봉 몸통을 완전히 포함하는 패턴.

    Args:
        open_: 시가 시계열
        close: 종가 시계열

    Returns:
        Bearish Engulfing 패턴 감지 여부

    Examples:
        >>> is_bear_eng = detect_bearish_engulfing(df['open'], df['close'])
    """
    if len(close) < 2:
        return False
    prev_o, prev_c = open_.iloc[-2], close.iloc[-2]
    curr_o, curr_c = open_.iloc[-1], close.iloc[-1]
    # 이전 봉이 양봉, 현재 봉이 음봉이며 완전히 포함
    return bool(
        prev_c > prev_o  # 이전 양봉
        and curr_c < curr_o  # 현재 음봉
        and curr_o > prev_c
        and curr_c < prev_o
    )
