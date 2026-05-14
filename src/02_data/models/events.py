"""
CQRS + Event Sourcing 구현

Write Model: Event Store (PostgreSQL)
Read Model:  Redis + ClickHouse

이벤트 타입:
  - CandleCreatedEvent  : 캔들 생성
  - GapDetectedEvent    : Gap 발견
  - OrderPlacedEvent    : 주문 생성
  - OrderFilledEvent    : 주문 체결
  - OrderCancelledEvent : 주문 취소
"""
from __future__ import annotations

import json as _json
import logging as _logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import orjson

    def _dumps(obj: Any) -> bytes:
        return orjson.dumps(obj, default=str)

    def _loads(data: bytes | str) -> Any:
        return orjson.loads(data)

except ImportError:  # orjson이 설치되지 않은 경우 표준 라이브러리 사용

    def _dumps(obj: Any) -> bytes:  # type: ignore[misc]
        return _json.dumps(obj, default=str).encode()

    def _loads(data: bytes | str) -> Any:  # type: ignore[misc]
        return _json.loads(data)


# ---------------------------------------------------------------------------
# Base Event
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """기본 이벤트"""

    aggregate_id: str   # 집합체 식별자 (예: symbol 또는 order_id)
    event_type: str     # 이벤트 유형
    version: int        # 이벤트 버전 (낙관적 잠금)
    timestamp: datetime # 발생 시각 (UTC)
    data: dict          # 이벤트 페이로드 (구 필드명, 호환 유지)

    # v9.0 CQRS Event Store 추가 필드
    event_id: Optional[int] = None
    aggregate_type: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    @property
    def payload(self) -> Dict[str, Any]:
        """event_data 우선, 없으면 data를 반환 (직렬화 중복 방지용 헬퍼)"""
        return self.event_data if self.event_data is not None else self.data

    def to_dict(self) -> Dict[str, Any]:
        """직렬화 딕셔너리 반환"""
        return {
            'event_id':       self.event_id,
            'aggregate_id':   self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'event_type':     self.event_type,
            'event_data':     self.payload,
            'metadata':       self.metadata,
            'created_at':     (self.created_at or self.timestamp).isoformat()
                              if (self.created_at or self.timestamp) else None,
            'version':        self.version,
        }

    def to_json(self) -> str:
        return _json.dumps(self.to_dict(), default=str)


# ---------------------------------------------------------------------------
# Concrete Events — 캔들 / Gap (기존 유지)
# ---------------------------------------------------------------------------

class CandleCreatedEvent(Event):
    """캔들 생성 이벤트"""

    def __init__(self, symbol: str, candle_data: dict, version: int):
        super().__init__(
            aggregate_id=symbol,
            event_type="CandleCreated",
            version=version,
            timestamp=datetime.utcnow(),
            data=candle_data,
            aggregate_type="Candle",
            event_data=candle_data,
        )


class GapDetectedEvent(Event):
    """Gap 발견 이벤트"""

    def __init__(self, symbol: str, gap_info: dict, version: int):
        super().__init__(
            aggregate_id=symbol,
            event_type="GapDetected",
            version=version,
            timestamp=datetime.utcnow(),
            data=gap_info,
            aggregate_type="Candle",
            event_data=gap_info,
        )


# ---------------------------------------------------------------------------
# Concrete Events — 주문 (v9.0 신규)
# ---------------------------------------------------------------------------

class OrderPlacedEvent(Event):
    """주문 생성 이벤트"""

    def __init__(self, event_id: int, order_id: str, symbol: str,
                 side: str, price: float, quantity: float, **kwargs):
        payload: Dict[str, Any] = {
            'symbol':   symbol,
            'side':     side,
            'price':    price,
            'quantity': quantity,
        }
        super().__init__(
            event_id=event_id,
            aggregate_id=order_id,
            aggregate_type='Order',
            event_type='OrderPlaced',
            version=kwargs.pop('version', 1),
            timestamp=kwargs.pop('timestamp', datetime.utcnow()),
            data=payload,
            event_data=payload,
            **kwargs,
        )


class OrderFilledEvent(Event):
    """주문 체결 이벤트"""

    def __init__(self, event_id: int, order_id: str, filled_quantity: float,
                 filled_price: float, **kwargs):
        payload: Dict[str, Any] = {
            'filled_quantity': filled_quantity,
            'filled_price':    filled_price,
        }
        super().__init__(
            event_id=event_id,
            aggregate_id=order_id,
            aggregate_type='Order',
            event_type='OrderFilled',
            version=kwargs.pop('version', 1),
            timestamp=kwargs.pop('timestamp', datetime.utcnow()),
            data=payload,
            event_data=payload,
            **kwargs,
        )


class OrderCancelledEvent(Event):
    """주문 취소 이벤트"""

    def __init__(self, event_id: int, order_id: str, reason: str, **kwargs):
        payload: Dict[str, Any] = {'reason': reason}
        super().__init__(
            event_id=event_id,
            aggregate_id=order_id,
            aggregate_type='Order',
            event_type='OrderCancelled',
            version=kwargs.pop('version', 1),
            timestamp=kwargs.pop('timestamp', datetime.utcnow()),
            data=payload,
            event_data=payload,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Event Store
# ---------------------------------------------------------------------------

_logger = _logging.getLogger(__name__)


class EventStore:
    """
    이벤트 소싱 저장소

    - 쓰기: PostgreSQL event_store 테이블 (Append-Only)
    - 스트리밍: Kafka trade_events 토픽 (실패 시 경고 후 계속 진행)
    """

    def __init__(self, db_pool: Any, kafka_producer: Any = None):
        self.db = db_pool
        self.kafka = kafka_producer

    async def append(self, event: Event) -> None:
        """이벤트 저장 + Kafka 발행 (Kafka 실패 시 경고 후 계속 진행)"""
        async with self.db.acquire() as conn:
            # PostgreSQL Event Store (Append-Only)
            await conn.execute(
                """
                INSERT INTO event_store
                    (aggregate_id, event_type, version, timestamp, data)
                VALUES ($1, $2, $3, $4, $5)
                """,
                event.aggregate_id,
                event.event_type,
                event.version,
                event.timestamp,
                _dumps(event.data).decode(),
            )

        # Kafka 스트림 발행 (Optional — 실패해도 PostgreSQL 저장은 유지)
        if self.kafka:
            try:
                await self.kafka.send(
                    "trade_events",
                    key=event.aggregate_id.encode(),
                    value=_dumps(asdict(event)),
                )
            except Exception as exc:
                _logger.warning("Kafka 발행 실패 (이벤트는 PostgreSQL에 저장됨): %s", exc)

    def save_event(self, event: Event) -> None:
        """이벤트 저장 — 동기 인터페이스 (동기 db 연결 전용)

        Note: self.db는 .execute(query, params) 메서드를 가진 동기 연결이어야 합니다.
              비동기 asyncpg 풀과 함께 사용할 경우에는 append() 메서드를 사용하세요.
        """
        query = """
            INSERT INTO event_store
                (event_id, aggregate_id, aggregate_type, event_type, event_data, metadata, version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.db.execute(query, (
            event.event_id,
            event.aggregate_id,
            event.aggregate_type,
            event.event_type,
            _json.dumps(event.payload, default=str),
            _json.dumps(event.metadata, default=str) if event.metadata else None,
            event.version,
        ))

    async def get_events(
        self, aggregate_id: str, from_version: int = 0
    ) -> list[dict]:
        """집합체의 이벤트 히스토리 조회"""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_type, version, timestamp, data
                FROM   event_store
                WHERE  aggregate_id = $1
                  AND  version      >= $2
                ORDER  BY version ASC
                """,
                aggregate_id,
                from_version,
            )
            return [dict(row) for row in rows]

    async def get_latest_version(self, aggregate_id: str) -> int:
        """집합체의 최신 버전 번호 조회"""
        async with self.db.acquire() as conn:
            version = await conn.fetchval(
                """
                SELECT COALESCE(MAX(version), 0)
                FROM   event_store
                WHERE  aggregate_id = $1
                """,
                aggregate_id,
            )
            return version
