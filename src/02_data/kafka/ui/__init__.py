"""Kafka UI 패키지"""

from .kafka_settings_dialog import KafkaSettingsDialog
from .widget_kafka_settings import KafkaBrokersTab

__all__ = ["KafkaSettingsDialog", "KafkaBrokersTab"]

# 모니터링 다이얼로그 안전 로드
try:
    from .kafka_monitor import KafkaMonitorDialog  # noqa: F401
    __all__.append("KafkaMonitorDialog")
except Exception:
    pass
