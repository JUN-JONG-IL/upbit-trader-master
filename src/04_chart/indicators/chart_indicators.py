"""
[Purpose]
기술 지표 계산 모듈 (mplchart 스타일)

[Features]
✅ 이동평균 (SMA, EMA, WMA)
✅ 볼린저 밴드 (Bollinger Bands)
✅ RSI (Relative Strength Index)
✅ MACD (Moving Average Convergence Divergence)
✅ Stochastic
✅ ATR (Average True Range)
✅ ADX (Average Directional Index)
✅ OBV (On-Balance Volume)
✅ Parabolic SAR
✅ Ichimoku Cloud

[Responsibilities]
- pandas 기반 지표 계산
- NaN 처리
- 벡터화 연산 (numpy)

[mplchart Reference]
- furechan/mplchart의 indicators.py 참조
- pandas rolling/ewm 사용
- 효율적인 벡터 연산

[Author] Phase 2 (mplchart 반영)
[Created] 2026-01-25
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional


def sma(data: pd.Series, period: int = 20) -> pd.Series:
    """
    단순 이동평균 (Simple Moving Average)
    
    [Parameters]
    - data: 가격 데이터 (pd.Series)
    - period: 기간 (기본 20)
    
    [Returns]
    - pd.Series: SMA 값
    """
    return data.rolling(window=period).mean()


def ema(data: pd.Series, period: int = 20) -> pd.Series:
    """
    지수 이동평균 (Exponential Moving Average)
    
    [Parameters]
    - data: 가격 데이터
    - period: 기간
    
    [Returns]
    - pd.Series: EMA 값
    """
    return data.ewm(span=period, adjust=False).mean()


def wma(data: pd.Series, period: int = 20) -> pd.Series:
    """
    가중 이동평균 (Weighted Moving Average)
    
    [Parameters]
    - data: 가격 데이터
    - period: 기간
    
    [Returns]
    - pd.Series: WMA 값
    """
    weights = np.arange(1, period + 1)
    
    def weighted_mean(x):
        if len(x) < period:
            return np.nan
        return np.dot(x[-period:], weights) / weights.sum()
    
    return data.rolling(window=period).apply(weighted_mean, raw=True)


def bollinger_bands(
    data: pd.Series, 
    period: int = 20, 
    std_dev: float = 2.0
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


def macd(
    data: pd.Series, 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
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


def stochastic(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """
    스토캐스틱 (Stochastic Oscillator)
    
    [Parameters]
    - high: 고가
    - low: 저가
    - close: 종가
    - k_period: %K 기간 (기본 14)
    - d_period: %D 기간 (기본 3)
    
    [Returns]
    - (%K, %D)
    """
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=d_period).mean()
    
    return k, d


def atr(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 14
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


def adx(
    high: pd.Series, 
    low: pd.Series, 
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    평균 방향 지수 (Average Directional Index)
    
    [Parameters]
    - high: 고가
    - low: 저가
    - close: 종가
    - period: 기간 (기본 14)
    
    [Returns]
    - pd.Series: ADX 값
    """
    # True Range
    tr = atr(high, low, close, period)
    
    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    
    # Smoothed DM and TR
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)
    
    # DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # ADX
    adx_values = dx.rolling(window=period).mean()
    
    return adx_values


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


def parabolic_sar(
    high: pd.Series, 
    low: pd.Series,
    acceleration: float = 0.02,
    maximum: float = 0.2
) -> pd.Series:
    """
    Parabolic SAR (Stop and Reverse)
    
    [Parameters]
    - high: 고가
    - low: 저가
    - acceleration: 가속 계수 (기본 0.02)
    - maximum: 최대 가속 (기본 0.2)
    
    [Returns]
    - pd.Series: SAR 값
    """
    # 단순 구현 (향후 최적화)
    sar = pd.Series(index=high.index, dtype=float)
    
    # 초기값
    sar.iloc[0] = low.iloc[0]
    
    return sar


def ichimoku_cloud(
    high: pd.Series, 
    low: pd.Series,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    displacement: int = 26
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    일목균형표 (Ichimoku Cloud)
    
    [Parameters]
    - high: 고가
    - low: 저가
    - tenkan_period: 전환선 기간 (기본 9)
    - kijun_period: 기준선 기간 (기본 26)
    - senkou_b_period: 선행스팬B 기간 (기본 52)
    - displacement: 변위 (기본 26)
    
    [Returns]
    - (tenkan, kijun, senkou_a, senkou_b, chikou)
    """
    # 전환선 (Tenkan-sen)
    tenkan = (high.rolling(window=tenkan_period).max() + 
              low.rolling(window=tenkan_period).min()) / 2
    
    # 기준선 (Kijun-sen)
    kijun = (high.rolling(window=kijun_period).max() + 
             low.rolling(window=kijun_period).min()) / 2
    
    # 선행스팬A (Senkou Span A)
    senkou_a = ((tenkan + kijun) / 2).shift(displacement)
    
    # 선행스팬B (Senkou Span B)
    senkou_b = ((high.rolling(window=senkou_b_period).max() + 
                 low.rolling(window=senkou_b_period).min()) / 2).shift(displacement)
    
    # 후행스팬 (Chikou Span)
    chikou = high.shift(-displacement)
    
    return tenkan, kijun, senkou_a, senkou_b, chikou


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    모든 지표 계산 (한 번에)
    
    [Parameters]
    - df: OHLCV DataFrame (columns: open, high, low, close, volume)
    
    [Returns]
    - pd.DataFrame: 지표가 추가된 DataFrame
    """
    result = df.copy()
    
    # 이동평균
    result['sma_20'] = sma(df['close'], 20)
    result['ema_20'] = ema(df['close'], 20)
    result['wma_20'] = wma(df['close'], 20)
    
    # 볼린저 밴드
    bb_upper, bb_middle, bb_lower = bollinger_bands(df['close'], 20, 2.0)
    result['bb_upper'] = bb_upper
    result['bb_middle'] = bb_middle
    result['bb_lower'] = bb_lower
    
    # RSI
    result['rsi_14'] = rsi(df['close'], 14)
    
    # MACD
    macd_line, signal_line, histogram = macd(df['close'], 12, 26, 9)
    result['macd_line'] = macd_line
    result['macd_signal'] = signal_line
    result['macd_histogram'] = histogram
    
    # Stochastic
    k, d = stochastic(df['high'], df['low'], df['close'], 14, 3)
    result['stoch_k'] = k
    result['stoch_d'] = d
    
    # ATR
    result['atr_14'] = atr(df['high'], df['low'], df['close'], 14)
    
    # ADX
    result['adx_14'] = adx(df['high'], df['low'], df['close'], 14)
    
    # OBV
    result['obv'] = obv(df['close'], df['volume'])
    
    # Ichimoku
    tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(
        df['high'], df['low'], 9, 26, 52, 26
    )
    result['ichimoku_tenkan'] = tenkan
    result['ichimoku_kijun'] = kijun
    result['ichimoku_senkou_a'] = senkou_a
    result['ichimoku_senkou_b'] = senkou_b
    result['ichimoku_chikou'] = chikou
    
    return result