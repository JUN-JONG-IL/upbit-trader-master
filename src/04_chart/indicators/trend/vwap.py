"""
[Purpose]
거래량 가중 평균 가격 (Volume-Weighted Average Price)

[Features]
- VWAP (Volume-Weighted Average Price)
- Anchored VWAP

[Author] Phase 2
[Created] 2026-01-25
"""

import pandas as pd


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """
    거래량 가중 평균 가격 (VWAP)

    [Parameters]
    - high: 고가
    - low: 저가
    - close: 종가
    - volume: 거래량

    [Returns]
    - pd.Series: VWAP 값
    """
    typical_price = (high + low + close) / 3
    tp_vol = typical_price * volume
    return tp_vol.cumsum() / volume.cumsum()
