"""
Feature Engineer - Generates features from raw market data
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Generates trading features from market data"""
    
    def __init__(self):
        self.feature_groups = {
            "price_features": self._generate_price_features,
            "technical_indicators": self._generate_technical_indicators,
            "volume_features": self._generate_volume_features,
            "volatility_features": self._generate_volatility_features,
            "momentum_features": self._generate_momentum_features
        }
    
    def generate_features(
        self,
        candles: List[Dict],
        feature_groups: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Generate features from candle data
        
        Args:
            candles: List of candle dictionaries
            feature_groups: Optional list of feature groups to generate
            
        Returns:
            Dictionary of features
        """
        if not candles:
            return {}
        
        # Convert to DataFrame
        df = pd.DataFrame(candles)
        
        # Generate requested feature groups
        features = {}
        groups_to_generate = feature_groups if feature_groups else self.feature_groups.keys()
        
        for group in groups_to_generate:
            if group in self.feature_groups:
                group_features = self.feature_groups[group](df)
                features.update(group_features)
        
        return features
    
    def _generate_price_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Generate price-based features"""
        features = {}
        
        # Price lags
        for lag in [1, 5, 10, 20]:
            if len(df) > lag:
                features[f"close_lag_{lag}"] = df['close'].iloc[-lag - 1]
        
        # Returns
        for window in [5, 10, 20]:
            if len(df) > window:
                returns = df['close'].pct_change(window)
                features[f"return_{window}"] = returns.iloc[-1]
        
        # Price statistics
        if len(df) > 0:
            features["close_current"] = df['close'].iloc[-1]
            features["high_current"] = df['high'].iloc[-1]
            features["low_current"] = df['low'].iloc[-1]
        
        return features
    
    def _generate_technical_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """Generate technical indicator features"""
        features = {}
        
        # Try to use TA-Lib if available, otherwise use simple calculations
        try:
            import talib
            
            if len(df) >= 14:
                features['rsi_14'] = talib.RSI(df['close'].values, timeperiod=14)[-1]
            
            if len(df) >= 26:
                macd, signal, hist = talib.MACD(df['close'].values)
                features['macd'] = macd[-1] if len(macd) > 0 else 0
                features['macd_signal'] = signal[-1] if len(signal) > 0 else 0
                features['macd_hist'] = hist[-1] if len(hist) > 0 else 0
        except ImportError:
            # Fallback to simple indicators
            if len(df) >= 14:
                features['rsi_14'] = self._calculate_rsi(df['close'], 14)
            
            if len(df) >= 26:
                ema12 = df['close'].ewm(span=12).mean()
                ema26 = df['close'].ewm(span=26).mean()
                features['macd'] = ema12.iloc[-1] - ema26.iloc[-1]
                features['macd_signal'] = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        
        # Moving averages
        for period in [5, 10, 20, 50]:
            if len(df) >= period:
                features[f'sma_{period}'] = df['close'].rolling(period).mean().iloc[-1]
                features[f'ema_{period}'] = df['close'].ewm(span=period).mean().iloc[-1]
        
        # Bollinger Bands
        if len(df) >= 20:
            sma20 = df['close'].rolling(20).mean()
            std20 = df['close'].rolling(20).std()
            features['bb_upper'] = (sma20 + 2 * std20).iloc[-1]
            features['bb_middle'] = sma20.iloc[-1]
            features['bb_lower'] = (sma20 - 2 * std20).iloc[-1]
        
        return features
    
    def _generate_volume_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Generate volume-based features"""
        features = {}
        
        if 'volume' not in df.columns or len(df) == 0:
            return features
        
        # Volume statistics
        features['volume_current'] = df['volume'].iloc[-1]
        
        for period in [10, 20, 50]:
            if len(df) >= period:
                vol_ma = df['volume'].rolling(period).mean()
                features[f'volume_ma_{period}'] = vol_ma.iloc[-1]
                features[f'volume_ratio_{period}'] = df['volume'].iloc[-1] / vol_ma.iloc[-1]
        
        # Volume trend
        if len(df) >= 10:
            features['volume_trend'] = df['volume'].iloc[-5:].mean() / df['volume'].iloc[-10:-5].mean()
        
        return features
    
    def _generate_volatility_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Generate volatility features"""
        features = {}
        
        if len(df) == 0:
            return features
        
        # Historical volatility
        for period in [10, 20, 50]:
            if len(df) >= period:
                returns = df['close'].pct_change()
                features[f'volatility_{period}'] = returns.rolling(period).std().iloc[-1]
        
        # True Range (ATR approximation)
        if len(df) >= 14:
            high_low = df['high'] - df['low']
            features['atr_14'] = high_low.rolling(14).mean().iloc[-1]
        
        return features
    
    def _generate_momentum_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Generate momentum features"""
        features = {}
        
        if len(df) == 0:
            return features
        
        # Rate of change
        for period in [5, 10, 20]:
            if len(df) >= period:
                roc = (df['close'].iloc[-1] / df['close'].iloc[-period - 1] - 1) * 100
                features[f'roc_{period}'] = roc
        
        # Momentum
        if len(df) >= 10:
            features['momentum_10'] = df['close'].iloc[-1] - df['close'].iloc[-11]
        
        return features
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI manually"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = prices.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = -deltas.where(deltas < 0, 0)
        
        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
