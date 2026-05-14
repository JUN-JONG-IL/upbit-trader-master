"""
[Purpose]
Kafka 클라이언트

[Responsibilities]
- Kafka 연결 관리
- 메시지 발행
"""

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

import json
from typing import Optional, Dict, Any


class KafkaClient:
    """Kafka 클라이언트"""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python 패키지가 설치되지 않았습니다.")
        
        self.bootstrap_servers = bootstrap_servers
        self.producer: Optional[KafkaProducer] = None
    
    def get_producer(self) -> KafkaProducer:
        """Producer 가져오기"""
        if self.producer is None:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        return self.producer
    
    def send(self, topic: str, message: Dict[str, Any]):
        """메시지 발행"""
        producer = self.get_producer()
        producer.send(topic, message)
    
    def close(self):
        """연결 종료"""
        if self.producer:
            self.producer.close()
