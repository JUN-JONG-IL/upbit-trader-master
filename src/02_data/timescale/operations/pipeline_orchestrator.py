"""
Pipeline Orchestrator - 10단계 통합 관리
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self, redis_client, timescale_client):
        from .stage_01_checker import DataChecker
        from .stage_02_receiver import CandleReceiver
        from .stage_03_stager import CandleStager
        from .stage_04_validator import CandleValidator
        from .stage_05_isolator import CandleIsolator
        from .stage_06_finalizer import CandleFinalizer
        from .stage_07_notifier import CandleNotifier
        from .stage_08_aggregator import CandleAggregator
        from .stage_09_hydrator import CacheHydrator
        from .stage_10_monitor import PipelineMonitor
        
        self.monitor = PipelineMonitor()
        self.hydrator = CacheHydrator(redis_client, timescale_client, self.monitor)
        self.aggregator = CandleAggregator(timescale_client, self.hydrator)
        self.notifier = CandleNotifier(redis_client, self.aggregator)
        self.finalizer = CandleFinalizer(timescale_client, self.notifier)
        self.isolator = CandleIsolator(timescale_client, redis_client)
        self.validator = CandleValidator(self.isolator, self.finalizer)
        self.stager = CandleStager(timescale_client, self.validator)
        self.receiver = CandleReceiver(self.stager)
        self.checker = DataChecker(redis_client, timescale_client)
    
    async def start(self, symbols: List[str], timeframe: str):
        """파이프라인 시작"""
        logger.info(f"🚀 파이프라인 시작: {len(symbols)}개 심볼")
        await self.receiver.start(symbols, timeframe)
