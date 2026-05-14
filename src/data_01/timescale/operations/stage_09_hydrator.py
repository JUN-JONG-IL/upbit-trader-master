"""
Stage 9: Hydrator - 캐시 갱신
"""
import logging
import json
from typing import Dict

logger = logging.getLogger(__name__)

class CacheHydrator:
    def __init__(self, redis_client, timescale_client, monitor):
        self.redis = redis_client
        self.timescale = timescale_client
        self.monitor = monitor
    
    async def hydrate_cache(self, symbol: str, timeframe: str):
        """Redis 캐시 갱신"""
        candles = await self.timescale.fetch_recent_candles(symbol, timeframe, 100)
        
        cache_key = f"cache:candles:{symbol}:{timeframe}"
        mapping = {str(c['timestamp']): json.dumps(c) for c in candles}
        
        pipe = self.redis.pipeline()
        pipe.delete(cache_key)
        pipe.hset(cache_key, mapping=mapping)
        pipe.expire(cache_key, 3600)
        await pipe.execute()
        
        logger.debug(f"💾 캐시 갱신: {symbol} {timeframe} ({len(candles)}개)")
        await self.monitor.record_pipeline_metrics(symbol, timeframe)
