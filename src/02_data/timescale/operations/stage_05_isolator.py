"""
Stage 5: Isolator - 이상 데이터 격리
"""
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CandleIsolator:
    def __init__(self, timescale_client, redis_client):
        self.timescale = timescale_client
        self.redis = redis_client
    
    async def isolate_invalid(self, candle: Dict, reason: str):
        """검증 실패 데이터 격리"""
        record = {**candle, 'isolation_reason': reason, 'isolated_at': datetime.utcnow()}
        await self.timescale.insert("isolated_candles", record)
        logger.warning(f"🔒 격리: {candle['symbol']} - {reason}")
    
    async def queue_gap(self, symbol: str, start: int, end: int):
        """Gap 큐잉"""
        key = f"{symbol}:{start}:{end}"
        await self.redis.zadd("gap_queue", {key: datetime.utcnow().timestamp()})
        logger.info(f"📝 Gap 큐잉: {symbol} [{start}~{end}]")
