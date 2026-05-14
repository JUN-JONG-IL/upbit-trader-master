"""
Stage 8: Aggregator - CAGG 및 지표 계산
"""
import logging
from typing import Dict
import numpy as np

logger = logging.getLogger(__name__)

class CandleAggregator:
    def __init__(self, timescale_client, hydrator):
        self.timescale = timescale_client
        self.hydrator = hydrator
    
    async def update_aggregations(self, candle: Dict):
        """CAGG 갱신 및 지표 계산"""
        await self._refresh_cagg(candle['symbol'], candle['timeframe'])
        await self._calculate_indicators(candle['symbol'], candle['timeframe'])
        await self.hydrator.hydrate_cache(candle['symbol'], candle['timeframe'])
    
    async def _refresh_cagg(self, symbol: str, tf: str):
        """CAGG 갱신"""
        if tf == '1m':
            await self.timescale.execute("CALL refresh_continuous_aggregate('cagg_candles_5m', NULL, NULL)")
    
    async def _calculate_indicators(self, symbol: str, tf: str):
        """지표 계산"""
        # TODO: SMA, EMA, RSI, MACD 계산
        pass
