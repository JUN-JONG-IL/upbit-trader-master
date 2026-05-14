"""
Stage 10: Monitor - 메트릭 수집
"""
import logging
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

class PipelineMonitor:
    def __init__(self):
        self.candles_processed = Counter('candles_processed_total', 'Processed', ['symbol', 'tf', 'stage'])
        self.validation_failures = Counter('validation_failures_total', 'Failures', ['symbol', 'tf', 'reason'])
        self.processing_time = Histogram('candle_processing_seconds', 'Time', ['stage'])
        self.gap_queue_size = Gauge('gap_queue_size', 'Gaps')
        self.cache_hit_rate = Gauge('cache_hit_rate', 'Hit rate', ['level'])
    
    async def record_pipeline_metrics(self, symbol: str, timeframe: str):
        """메트릭 기록"""
        self.candles_processed.labels(symbol=symbol, tf=timeframe, stage='complete').inc()
