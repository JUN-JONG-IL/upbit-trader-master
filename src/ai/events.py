"""
src/ai/events.py

CQRS + Event Sourcing 구현

이벤트 소싱 저장소 (PostgreSQL) + Kafka 발행
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CandleCreatedEvent:
    """캔들 생성 이벤트"""

    aggregate_id: str       # symbol (예: "KRW-BTC")
    timestamp: datetime
    data: dict[str, Any]
    version: int


@dataclass
class CandleUpdatedEvent:
    """캔들 업데이트 이벤트"""

    aggregate_id: str
    timestamp: datetime
    data: dict[str, Any]
    version: int


@dataclass
class TradeExecutedEvent:
    """거래 체결 이벤트"""

    aggregate_id: str       # trade_id
    timestamp: datetime
    data: dict[str, Any]
    version: int


class EventStore:
    """
    이벤트 소싱 저장소 (PostgreSQL)

    - event_store 테이블에 불변(Immutable) 이벤트 기록
    - Kafka trade_events 토픽에 비동기 발행
    """

    def __init__(self, db, kafka_producer):
        """
        Args:
            db: asyncpg 연결 풀
            kafka_producer: aiokafka AIOKafkaProducer 인스턴스
        """
        self.db = db
        self.kafka_producer = kafka_producer

    async def append(self, event: CandleCreatedEvent | CandleUpdatedEvent | TradeExecutedEvent) -> None:
        """이벤트 저장 + Kafka 발행 (트랜잭션)"""
        import json

        async with self.db.transaction():
            await self.db.execute(
                """
                INSERT INTO event_store (aggregate_id, event_type, data, version, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                event.aggregate_id,
                type(event).__name__,
                json.dumps(event.data),
                event.version,
                event.timestamp,
            )

        # Kafka 발행 (트랜잭션 외부 → 최소 1회 전달 보장)
        await self.kafka_producer.send(
            "trade_events",
            key=event.aggregate_id.encode(),
            value=json.dumps(event.data).encode(),
        )

    async def get_events(self, aggregate_id: str) -> list[dict[str, Any]]:
        """특정 집합체(aggregate)의 이벤트 이력 조회"""
        rows = await self.db.fetch(
            """
            SELECT event_type, data, version, created_at
            FROM event_store
            WHERE aggregate_id = $1
            ORDER BY version ASC
            """,
            aggregate_id,
        )
        return [dict(row) for row in rows]
