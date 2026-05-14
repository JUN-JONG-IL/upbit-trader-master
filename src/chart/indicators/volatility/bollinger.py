"""
[Purpose]
볼린저 밴드 (Bollinger Bands)

[Features]
- Upper Band
- Middle Band (SMA)
- Lower Band

[Author] Phase 2
[Created] 2026-01-25
"""

from typing import Tuple
import pandas as pd
from ..trend.ma import sma


def bollinger_bands(
    data: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    볼린저 밴드 (Bollinger Bands)

    [Parameters]
    - data: 가격 데이터
    - period: 기간 (기본 20)
    - std_dev: 표준편차 배수 (기본 2.0)

    [Returns]
    - (upper, middle, lower): 상단/중단/하단 밴드
    """
    middle = sma(data, period)
    std = data.rolling(window=period).std()

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    return upper, middle, lower
