"""
Kafka Producer/Consumer 연결 팩토리

[Purpose]
환경 변수 기반으로 Kafka Producer/Consumer를 생성합니다.

환경 변수:
    KAFKA_BROKERS: 브로커 주소 (쉼표 구분, 기본값: localhost:9092)
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from kafka import KafkaProducer, KafkaConsumer  # type: ignore
    _KAFKA_AVAILABLE = True
except ImportError:
    KafkaProducer = None  # type: ignore
    KafkaConsumer = None  # type: ignore
    _KAFKA_AVAILABLE = False


def _get_brokers() -> list[str]:
    """KAFKA_BROKERS 환경 변수에서 브로커 목록을 반환합니다."""
    return os.getenv("KAFKA_BROKERS", "localhost:9092").split(",")


def get_producer() -> Optional[object]:
    """
    KafkaProducer 인스턴스를 반환합니다.

    Returns:
        KafkaProducer | None: kafka-python 미설치 시 None 반환
    """
    if not _KAFKA_AVAILABLE:
        logger.warning("kafka-python 미설치 — KafkaProducer 사용 불가")
        return None
    return KafkaProducer(bootstrap_servers=_get_brokers())


def get_consumer(topic: str, group_id: str = "upbit-trader") -> Optional[object]:
    """
    KafkaConsumer 인스턴스를 반환합니다.

    Args:
        topic:    구독할 토픽 이름
        group_id: 컨슈머 그룹 ID

    Returns:
        KafkaConsumer | None: kafka-python 미설치 시 None 반환
    """
    if not _KAFKA_AVAILABLE:
        logger.warning("kafka-python 미설치 — KafkaConsumer 사용 불가")
        return None
    return KafkaConsumer(
        topic,
        bootstrap_servers=_get_brokers(),
        group_id=group_id,
    )
