"""
[Purpose]
가벼운 메트릭스 수집 시스템

[Responsibilities]
- 성능 지표 수집 (지연, 처리량, 오류율)
- Redis 저장
- /metrics-lite 엔드포인트용 데이터 제공

[Main Flow]
1. 메트릭스 수집 (gauge, counter)
2. Redis에 저장
3. FastAPI에서 조회
"""

import time
import json
from typing import Dict, Any
from collections import deque
import threading

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class MetricsLite:
    """경량 메트릭스 수집기"""
    
    def __init__(
        self,
        service_name: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        window_size: int = 100
    ):
        self.service_name = service_name
        self.redis_key = f"rt:metrics:{service_name}"
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True
                )
                self.redis_client.ping()
                self.redis_enabled = True
            except:
                self.redis_enabled = False
        else:
            self.redis_enabled = False
        
        self.latencies = deque(maxlen=window_size)
        self.msg_count = 0
        self.error_count = 0
        self.reconnect_count = 0
        
        # Compute 프로세스 메트릭스
        self.compute_latencies = deque(maxlen=window_size)
        self.candle_count = 0
        self.indicator_count = 0
        
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def record_latency(self, latency_ms: float):
        """지연 시간 기록"""
        with self.lock:
            self.latencies.append(latency_ms)
    
    def increment_message(self):
        """메시지 카운트 증가"""
        with self.lock:
            self.msg_count += 1
    
    def increment_error(self):
        """오류 카운트 증가"""
        with self.lock:
            self.error_count += 1
    
    def increment_reconnect(self):
        """재연결 카운트 증가"""
        with self.lock:
            self.reconnect_count += 1
    
    def record_compute_latency(self, latency_ms: float):
        """Compute 프로세스 지연 시간 기록"""
        with self.lock:
            self.compute_latencies.append(latency_ms)
    
    def increment_candle_aggregation(self):
        """캔들 집계 카운트 증가"""
        with self.lock:
            self.candle_count += 1
    
    def increment_indicator_calculation(self):
        """지표 계산 카운트 증가"""
        with self.lock:
            self.indicator_count += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """메트릭스 조회"""
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_update
            
            msg_per_sec = self.msg_count / elapsed if elapsed > 0 else 0
            
            latencies_list = list(self.latencies)
            if latencies_list:
                latencies_sorted = sorted(latencies_list)
                p50_idx = len(latencies_sorted) // 2
                p95_idx = int(len(latencies_sorted) * 0.95)
                
                latency_p50 = latencies_sorted[p50_idx]
                latency_p95 = latencies_sorted[p95_idx]
                latency_max = max(latencies_sorted)
            else:
                latency_p50 = latency_p95 = latency_max = 0
            
            error_rate = (self.error_count / self.msg_count * 100) if self.msg_count > 0 else 0
            
            # Compute 메트릭스
            compute_latencies_list = list(self.compute_latencies)
            if compute_latencies_list:
                compute_sorted = sorted(compute_latencies_list)
                compute_p50 = compute_sorted[len(compute_sorted) // 2]
                compute_p95 = compute_sorted[int(len(compute_sorted) * 0.95)]
            else:
                compute_p50 = compute_p95 = 0
            
            metrics = {
                "service": self.service_name,
                "timestamp": current_time,
                "ws_msg_per_sec": round(msg_per_sec, 2),
                "queue_length": 0,
                "latency_p50_ms": round(latency_p50, 2),
                "latency_p95_ms": round(latency_p95, 2),
                "latency_max_ms": round(latency_max, 2),
                "reconnect_count": self.reconnect_count,
                "error_count": self.error_count,
                "error_rate": round(error_rate, 2),
                "compute_latency_p50_ms": round(compute_p50, 2),
                "compute_latency_p95_ms": round(compute_p95, 2),
                "candle_count": self.candle_count,
                "indicator_count": self.indicator_count
            }
            
            if self.redis_enabled:
                try:
                    self.redis_client.setex(
                        self.redis_key,
                        60,
                        json.dumps(metrics)
                    )
                except:
                    pass
            
            return metrics
