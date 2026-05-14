"""
Stage 7: Notifier - 이벤트 발행
"""
import logging
import json
import time
from typing import Dict

logger = logging.getLogger(__name__)

class CandleNotifier:
    def __init__(self, redis_client, aggregator):
        self.redis = redis_client
        self.aggregator = aggregator
    
    async def notify_new_candle(self, candle: Dict):
        """Redis Pub/Sub 발행"""
        channel = f"candle:{candle['symbol']}:{candle['timeframe']}"
        msg = json.dumps({'type': 'new_candle', 'data': candle, 'timestamp': int(time.time())})
        
        await self.redis.publish(channel, msg)
        logger.debug(f"📢 이벤트: {channel}")
        
        await self.aggregator.update_aggregations(candle)
