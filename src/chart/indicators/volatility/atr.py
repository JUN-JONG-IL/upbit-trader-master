"""
[Purpose]
평균 진폭 (ATR - Average True Range)

[Features]
- ATR (Average True Range)

[Author] Phase 2
[Created] 2026-01-25
"""

import pandas as pd


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    평균 진폭 (Average True Range)

    [Parameters]
    - high: 고가
    - low: 저가
    - close: 종가
    - period: 기간 (기본 14)

    [Returns]
    - pd.Series: ATR 값
    """
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_values = tr.rolling(window=period).mean()

    return atr_values
