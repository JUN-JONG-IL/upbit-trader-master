"""
[Purpose]
거래량 균형 (OBV - On-Balance Volume)

[Features]
- OBV (On-Balance Volume)

[Author] Phase 2
[Created] 2026-01-25
"""

import numpy as np
import pandas as pd


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    거래량 균형 (On-Balance Volume)

    [Parameters]
    - close: 종가
    - volume: 거래량

    [Returns]
    - pd.Series: OBV 값
    """
    direction = np.sign(close.diff())
    obv_values = (direction * volume).cumsum()

    return obv_values
