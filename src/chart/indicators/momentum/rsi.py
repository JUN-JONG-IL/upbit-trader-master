"""
[Purpose]
상대강도지수 (RSI - Relative Strength Index)

[Features]
- RSI (14-period default)

[Author] Phase 2
[Created] 2026-01-25
"""

import pandas as pd


def rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """
    상대강도지수 (Relative Strength Index)

    [Parameters]
    - data: 가격 데이터
    - period: 기간 (기본 14)

    [Returns]
    - pd.Series: RSI 값 (0~100)
    """
    delta = data.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi_values = 100 - (100 / (1 + rs))

    return rsi_values
