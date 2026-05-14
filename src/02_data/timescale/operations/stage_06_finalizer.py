"""
Stage 6: Finalizer - 최종 저장
"""
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

class CandleFinalizer:
    def __init__(self, timescale_client, notifier):
        self.timescale = timescale_client
        self.notifier = notifier
    
    async def finalize_candle(self, candle: Dict):
        """candles 테이블에 UPSERT"""
        candle['finalized_at'] = datetime.utcnow()
        
        query = """
        INSERT INTO candles (symbol, timeframe, timestamp, open, high, low, close, volume, finalized_at, is_outlier)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE SET
            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
            close=EXCLUDED.close, volume=EXCLUDED.volume,
            finalized_at=EXCLUDED.finalized_at, is_outlier=EXCLUDED.is_outlier
        """
        
        await self.timescale.execute(
            query, candle['symbol'], candle['timeframe'], candle['timestamp'],
            candle['open'], candle['high'], candle['low'], candle['close'],
            candle['volume'], candle['finalized_at'], candle.get('is_outlier', False)
        )
        
        logger.info(f"✅ 저장: {candle['symbol']} {candle['timeframe']} {candle['timestamp']}")
        await self.notifier.notify_new_candle(candle)
