"""
Kafka 패키지

[Purpose]
Kafka Producer/Consumer 연결 관리

[Modules]
- connection: Kafka Producer/Consumer 팩토리
- health_check: Kafka 연결 상태 확인
- ui: Kafka 관리 UI
"""

try:
    from .connection import get_producer, get_consumer
except Exception:
    pass

__all__ = ["get_producer", "get_consumer"]
