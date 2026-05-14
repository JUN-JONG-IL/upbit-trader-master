"""
Stage 3: Stager - 임시 저장
"""
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

class CandleStager:
    def __init__(self, timescale_client, validator):
        self.timescale = timescale_client
        self.validator = validator
        self.batch = []
        self.batch_size = 100
    
    async def stage_candle(self, candle: Dict):
        """Staging 테이블에 저장"""
        candle['staged_at'] = datetime.utcnow()
        candle['stage_status'] = 'pending'
        
        self.batch.append(candle)
        
        if len(self.batch) >= self.batch_size:
            await self._flush()
        
        await self.validator.validate(candle)
    
    async def _flush(self):
        """배치 저장"""
        if self.batch:
            await self.timescale.insert_batch("staging_candles", self.batch)
            logger.info(f"💾 배치 저장: {len(self.batch)}개")
            self.batch.clear()
