"""
Stage 1: Checker - 데이터 존재 확인
"""
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

class DataChecker:
    def __init__(self, redis_client, timescale_client):
        self.redis = redis_client
        self.timescale = timescale_client
    
    async def check_candle_exists(self, symbol: str, timeframe: str, timestamp: int) -> bool:
        """캔들 데이터 존재 확인"""
        cache_key = f"candle:{symbol}:{timeframe}"
        if await self.redis.hexists(cache_key, str(timestamp)):
            logger.debug(f"✅ L0 캐시 히트: {symbol} {timeframe} {timestamp}")
            return True
        
        if await self.timescale.candle_exists(symbol, timeframe, timestamp):
            logger.debug(f"✅ L1 DB 히트: {symbol} {timeframe} {timestamp}")
            return True
        
        return False
    
    async def get_missing_ranges(self, symbol: str, timeframe: str, 
                                 start_time: int, end_time: int) -> List[Tuple[int, int]]:
        """누락된 시간 범위 탐지"""
        missing = []
        current = None
        
        t = start_time
        interval = self._get_interval(timeframe)
        
        while t <= end_time:
            if not await self.check_candle_exists(symbol, timeframe, t):
                if current is None:
                    current = t
            else:
                if current is not None:
                    missing.append((current, t - interval))
                    current = None
            t += interval
        
        if current is not None:
            missing.append((current, end_time))
        
        return missing
    
    def _get_interval(self, tf: str) -> int:
        """타임프레임 → 초 변환"""
        unit = tf[-1]
        val = int(tf[:-1])
        return val * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
