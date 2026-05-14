"""
[Purpose]
메트릭스 엔드포인트

[Responsibilities]
- 성능 지표 조회
- Redis에서 메트릭스 로드
"""

import os
from fastapi import APIRouter
from typing import Dict, Any
import json

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

router = APIRouter()


def _get_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import pathlib as _pl
        import importlib.util as _ilu
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_metrics", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


@router.get("/metrics-lite")
async def get_metrics() -> Dict[str, Any]:
    """메트릭스 조회"""
    if not REDIS_AVAILABLE:
        return {
            "error": "Redis not available",
            "message": "Redis 패키지가 설치되지 않았습니다."
        }
    
    try:
        redis_url = _get_redis_url()
        redis_client = redis.from_url(redis_url, decode_responses=True)
        
        metrics_data = redis_client.get("rt:metrics:ws:upbit")
        
        if metrics_data:
            metrics = json.loads(metrics_data)
        else:
            metrics = {
                "service": "ws:upbit",
                "ws_msg_per_sec": 0,
                "queue_length": 0,
                "latency_p50_ms": 0,
                "latency_p95_ms": 0,
                "latency_max_ms": 0,
                "reconnect_count": 0,
                "error_count": 0,
                "error_rate": 0
            }
        
        return metrics
    
    except Exception as e:
        return {
            "error": str(e),
            "message": "메트릭스 조회 실패"
        }
