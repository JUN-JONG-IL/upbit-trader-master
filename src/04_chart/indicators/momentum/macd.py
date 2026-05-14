"""
[Purpose]
이동평균 수렴확산 (MACD - Moving Average Convergence Divergence)

[Features]
- MACD Line
- Signal Line
- Histogram

[Author] Phase 2
[Created] 2026-01-25
"""

from typing import Tuple
import pandas as pd
from ..trend.ma import ema


def macd(
    data: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    이동평균 수렴확산 (MACD)

    [Parameters]
    - data: 가격 데이터
    - fast: 빠른 EMA 기간 (기본 12)
    - slow: 느린 EMA 기간 (기본 26)
    - signal: Signal 기간 (기본 9)

    [Returns]
    - (macd_line, signal_line, histogram)
    """
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)

    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram
