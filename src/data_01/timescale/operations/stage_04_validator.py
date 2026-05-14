"""
Stage 4: Validator - 데이터 검증
"""
import logging
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

class CandleValidator:
    def __init__(self, isolator, finalizer):
        self.isolator = isolator
        self.finalizer = finalizer
    
    async def validate(self, candle: Dict) -> bool:
        """종합 검증"""
        if not self._validate_ohlc(candle):
            await self.isolator.isolate_invalid(candle, "OHLC 무결성 실패")
            return False
        
        gap = await self._detect_gap(candle)
        if gap:
            await self.isolator.queue_gap(candle['symbol'], gap['start'], gap['end'])
        
        if await self._detect_outlier(candle):
            candle['is_outlier'] = True
        
        await self.finalizer.finalize_candle(candle)
        return True
    
    def _validate_ohlc(self, c: Dict) -> bool:
        """OHLC 무결성"""
        o, h, l, cl = c['open'], c['high'], c['low'], c['close']
        return l <= o <= h and l <= cl <= h and h >= max(o, cl) and l <= min(o, cl)
    
    async def _detect_gap(self, candle: Dict) -> Optional[Dict]:
        """Gap 탐지"""
        # TODO: 이전 캔들과 시간 차이 확인
        return None
    
    async def _detect_outlier(self, candle: Dict) -> bool:
        """이상치 탐지 (Z-score)"""
        # TODO: 최근 100개 캔들로 Z-score 계산
        return False
