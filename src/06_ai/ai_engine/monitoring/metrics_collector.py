"""
Metrics Collector - Collects and exports Prometheus-style metrics
"""

import time
import logging
from typing import Dict, List, Optional
from collections import defaultdict, deque
from datetime import datetime

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects inference metrics for monitoring"""
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        
        # Metrics storage
        self.inference_counts = defaultdict(int)  # model_name -> count
        self.inference_latencies = defaultdict(lambda: deque(maxlen=max_history))  # model_name -> [latencies]
        self.inference_errors = defaultdict(int)  # model_name -> error_count
        self.request_timestamps = deque(maxlen=max_history)  # Global request timestamps
        
        self.start_time = time.time()
    
    def record_inference(
        self,
        model_name: str,
        latency_ms: float,
        success: bool = True,
        error_type: Optional[str] = None
    ):
        """
        Record an inference request
        
        Args:
            model_name: Name of the model
            latency_ms: Inference latency in milliseconds
            success: Whether inference succeeded
            error_type: Type of error if failed
        """
        self.inference_counts[model_name] += 1
        self.inference_latencies[model_name].append(latency_ms)
        self.request_timestamps.append(time.time())
        
        if not success:
            self.inference_errors[model_name] += 1
            logger.warning(f"Inference error for {model_name}: {error_type}")
    
    def get_metrics(self, model_name: Optional[str] = None) -> Dict:
        """
        Get collected metrics
        
        Args:
            model_name: Optional model name to filter
            
        Returns:
            Dictionary of metrics
        """
        if model_name:
            return self._get_model_metrics(model_name)
        else:
            return self._get_global_metrics()
    
    def _get_model_metrics(self, model_name: str) -> Dict:
        """Get metrics for a specific model"""
        latencies = list(self.inference_latencies[model_name])
        
        if not latencies:
            return {
                "model_name": model_name,
                "total_requests": 0,
                "total_errors": 0,
                "error_rate": 0.0
            }
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        return {
            "model_name": model_name,
            "total_requests": self.inference_counts[model_name],
            "total_errors": self.inference_errors[model_name],
            "error_rate": self.inference_errors[model_name] / max(1, self.inference_counts[model_name]),
            "latency_p50_ms": sorted_latencies[int(n * 0.50)] if n > 0 else 0,
            "latency_p95_ms": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
            "latency_p99_ms": sorted_latencies[int(n * 0.99)] if n > 0 else 0,
            "latency_avg_ms": sum(latencies) / n if n > 0 else 0,
            "latency_min_ms": min(latencies) if latencies else 0,
            "latency_max_ms": max(latencies) if latencies else 0
        }
    
    def _get_global_metrics(self) -> Dict:
        """Get global metrics across all models"""
        total_requests = sum(self.inference_counts.values())
        total_errors = sum(self.inference_errors.values())
        
        # Compute throughput (requests per second)
        if len(self.request_timestamps) > 1:
            time_window = self.request_timestamps[-1] - self.request_timestamps[0]
            throughput_rps = len(self.request_timestamps) / max(1, time_window)
        else:
            throughput_rps = 0.0
        
        # Aggregate latencies
        all_latencies = []
        for latencies in self.inference_latencies.values():
            all_latencies.extend(latencies)
        
        sorted_latencies = sorted(all_latencies)
        n = len(sorted_latencies)
        
        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": total_errors / max(1, total_requests),
            "throughput_rps": throughput_rps,
            "uptime_seconds": time.time() - self.start_time,
            "models_active": len(self.inference_counts),
            "latency_p50_ms": sorted_latencies[int(n * 0.50)] if n > 0 else 0,
            "latency_p95_ms": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
            "latency_p99_ms": sorted_latencies[int(n * 0.99)] if n > 0 else 0,
            "latency_avg_ms": sum(all_latencies) / n if n > 0 else 0
        }
    
    def get_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus format
        
        Returns:
            Metrics in Prometheus text format
        """
        lines = []
        timestamp = int(time.time() * 1000)
        
        # Global metrics
        global_metrics = self._get_global_metrics()
        lines.append(f"# HELP ai_inference_total Total number of inference requests")
        lines.append(f"# TYPE ai_inference_total counter")
        lines.append(f'ai_inference_total {global_metrics["total_requests"]} {timestamp}')
        
        lines.append(f"# HELP ai_inference_errors_total Total number of inference errors")
        lines.append(f"# TYPE ai_inference_errors_total counter")
        lines.append(f'ai_inference_errors_total {global_metrics["total_errors"]} {timestamp}')
        
        lines.append(f"# HELP ai_throughput_rps Current throughput in requests per second")
        lines.append(f"# TYPE ai_throughput_rps gauge")
        lines.append(f'ai_throughput_rps {global_metrics["throughput_rps"]:.2f} {timestamp}')
        
        # Per-model metrics
        for model_name in self.inference_counts.keys():
            metrics = self._get_model_metrics(model_name)
            
            lines.append(f"# HELP ai_model_latency_p95_ms 95th percentile latency in milliseconds")
            lines.append(f"# TYPE ai_model_latency_p95_ms gauge")
            lines.append(f'ai_model_latency_p95_ms{{model="{model_name}"}} {metrics["latency_p95_ms"]:.2f} {timestamp}')
        
        return "\n".join(lines)
    
    def reset(self):
        """Reset all metrics"""
        self.inference_counts.clear()
        self.inference_latencies.clear()
        self.inference_errors.clear()
        self.request_timestamps.clear()
        self.start_time = time.time()
        logger.info("Metrics reset")


# Global instance
global_metrics_collector = MetricsCollector()
