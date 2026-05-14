"""
[Purpose]
- 기술적 지표 래퍼 (TA-Lib 기반)
"""
import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """기술적 지표 유틸리티"""

    @staticmethod
    def sma(prices: np.ndarray, period: int) -> np.ndarray:
        """단순 이동 평균"""
        if len(prices) < period:
            return np.array([])
        return np.convolve(prices, np.ones(period) / period, mode='valid')

    @staticmethod
    def ema(prices: np.ndarray, period: int) -> np.ndarray:
        """지수 이동 평균"""
        if len(prices) < period:
            return np.array([])
        try:
            import talib
            return talib.EMA(prices, timeperiod=period)
        except ImportError:
            alpha = 2.0 / (period + 1)
            ema = np.zeros(len(prices))
            ema[0] = prices[0]
            for i in range(1, len(prices)):
                ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
            return ema

    @staticmethod
    def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """RSI (Relative Strength Index)"""
        try:
            import talib
            return talib.RSI(prices, timeperiod=period)
        except ImportError:
            delta = np.diff(prices)
            gain = np.where(delta > 0, delta, 0)
            loss = np.where(delta < 0, -delta, 0)
            avg_gain = np.convolve(gain, np.ones(period) / period, mode='valid')
            avg_loss = np.convolve(loss, np.ones(period) / period, mode='valid')
            rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
            return 100 - (100 / (1 + rs))

    @staticmethod
    def bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2.0):
        """볼린저 밴드 (upper, middle, lower)"""
        try:
            import talib
            return talib.BBANDS(prices, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev)
        except ImportError:
            middle = TechnicalIndicators.sma(prices, period)
            rolling_std = np.array([np.std(prices[i:i+period]) for i in range(len(prices) - period + 1)])
            upper = middle + std_dev * rolling_std
            lower = middle - std_dev * rolling_std
            return upper, middle, lower
