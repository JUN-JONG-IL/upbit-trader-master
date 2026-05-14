"""
[Purpose]
- Scanner 룰 정의 및 관리

[Responsibilities]
- 각 룰의 로직을 클래스로 정의
- 룰 등록 및 실행 인터페이스 제공

[Author] Copilot
[Created] 2026-02-03
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict
import pandas as pd

try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False


class RuleBase(ABC):
    """Scanner 룰 베이스 클래스"""
    
    @abstractmethod
    def check(self, df: pd.DataFrame, settings: Dict[str, Any]) -> float:
        """
        룰 체크
        
        Args:
            df: OHLCV 데이터 (pandas DataFrame)
            settings: 사용자 설정
        
        Returns:
            0.0 ~ 1.0 (스코어)
        """
        pass


class RSIRule(RuleBase):
    """RSI 룰"""
    
    def check(self, df: pd.DataFrame, settings: Dict[str, Any]) -> float:
        try:
            if HAS_TALIB:
                rsi = talib.RSI(df['close'], timeperiod=14)
            else:
                # 간단한 RSI 계산
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
            
            if pd.notna(rsi.iloc[-1]) and rsi.iloc[-1] < settings.get('rsi_threshold', 30):
                return 1.0
            return 0.0
        except Exception:
            return 0.0


class GoldenCrossRule(RuleBase):
    """골든크로스 룰"""
    
    def check(self, df: pd.DataFrame, settings: Dict[str, Any]) -> float:
        try:
            ma_short = df['close'].rolling(window=settings.get('ma_short', 5)).mean()
            ma_long = df['close'].rolling(window=settings.get('ma_long', 20)).mean()
            
            if len(ma_short) < 2 or len(ma_long) < 2:
                return 0.0
            
            if settings.get('golden_dead') == "골든크로스":
                if ma_short.iloc[-2] < ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]:
                    return 1.0
            elif settings.get('golden_dead') == "데드크로스":
                if ma_short.iloc[-2] > ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]:
                    return 1.0
            elif settings.get('golden_dead') == "둘 다":
                if (ma_short.iloc[-2] < ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]) or \
                   (ma_short.iloc[-2] > ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]):
                    return 1.0
            
            return 0.0
        except Exception:
            return 0.0


class VolumeRule(RuleBase):
    """거래량 룰"""
    
    def check(self, df: pd.DataFrame, settings: Dict[str, Any]) -> float:
        try:
            avg_volume = df['volume'].rolling(window=20).mean()
            current_volume = df['volume'].iloc[-1]
            
            threshold = settings.get('volume_threshold', 150) / 100
            if pd.notna(avg_volume.iloc[-1]) and pd.notna(current_volume):
                if current_volume > avg_volume.iloc[-1] * threshold:
                    return 1.0
            return 0.0
        except Exception:
            return 0.0


class OHLCRule(RuleBase):
    """OHLC 임계값 룰"""
    
    def check(self, df: pd.DataFrame, settings: Dict[str, Any]) -> float:
        try:
            change_pct = (df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1] * 100
            
            if change_pct > settings.get('close_threshold', 50):
                return 1.0
            return 0.0
        except Exception:
            return 0.0


# 룰 레지스트리
RULES = {
    'rsi': RSIRule(),
    'golden_cross': GoldenCrossRule(),
    'volume': VolumeRule(),
    'ohlc': OHLCRule(),
}
