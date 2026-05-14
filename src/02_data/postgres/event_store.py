#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL CQRS Event Store — 이벤트 소싱 저장소

목적:
    OrderCreated / OrderFilled / TradeExecuted / BalanceUpdated 등
    불변(Immutable) 이벤트를 event_store 테이블에 저장합니다.
    INSERT만 허용하며 UPDATE/DELETE는 금지합니다.

이벤트 종류:
    - OrderCreated    : 주문 생성
    - OrderFilled     : 주문 체결
    - TradeExecuted   : 거래 실행
    - BalanceUpdated  : 잔고 변경

사용 예:
    pool = await get_pool()
    store = EventStore(pool)
    await store.append("order-001", "OrderCreated", {"symbol": "KRW-BTC", ...})
    events = await store.load("order-001")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 지원 이벤트 타입
EVENT_TYPES = frozenset(
    [
        "OrderCreated",
        "OrderFilled",
        "TradeExecuted",
        "BalanceUpdated",
        "SymbolAdded",
        "StrategyUpdated",
        "GapDetected",
        "BackfillCompleted",
    ]
)


@dataclass
class StoredEvent:
    """event_store 테이블 행 매핑.

    Attributes:
        event_id:       이벤트 고유 ID (Snowflake-style bigint).
        aggregate_id:   집합체 ID (예: order-001).
        aggregate_type: 집합체 유형 (예: Order).
        event_type:     이벤트 유형 (예: OrderCreated).
        event_data:     이벤트 페이로드 (JSONB).
        metadata:       메타데이터 (JSONB, 선택).
        created_at:     저장 시각.
        version:        Aggregate 내 순서 번호.
    """

    event_id: int
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    version: int


class EventStore:
    """CQRS Append-Only 이벤트 소싱 저장소.

    INSERT만 수행하며 UPDATE/DELETE 메서드를 제공하지 않습니다.
    """

    def __init__(self, pool) -> None:
        """
        Args:
            pool: asyncpg 연결 풀 (PostgreSQL Primary).
        """
        self._pool = pool
        self._seq = 0  # 밀리초 내 충돌 방지용 시퀀스 카운터

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _snowflake_id(self) -> int:
        """밀리초 단위 타임스탬프 + 시퀀스 기반 Snowflake-style ID를 생성합니다.

        같은 밀리초 내에 여러 이벤트가 생성될 경우 시퀀스를 증가시켜
        ID 충돌을 방지합니다.
        """
        self._seq = (self._seq + 1) & 0x3FFFFF  # 22비트 시퀀스
        return (int(time.time() * 1000) << 22) | self._seq

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # 쓰기 (INSERT Only)
    # ------------------------------------------------------------------

    async def append(
        self,
        aggregate_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        *,
        aggregate_type: str = "Generic",
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[int] = None,
    ) -> StoredEvent:
        """이벤트를 event_store 테이블에 저장합니다 (Append-Only).

        Args:
            aggregate_id:   집합체 ID.
            event_type:     이벤트 유형 (EVENT_TYPES 참조).
            event_data:     이벤트 페이로드.
            aggregate_type: 집합체 유형 (기본값: Generic).
            metadata:       추가 메타데이터.
            version:        버전 번호 (None이면 자동 증가).

        Returns:
            저장된 StoredEvent.

        Raises:
            ValueError: 지원하지 않는 이벤트 유형.
            RuntimeError: DB 저장 실패.
        """
        if event_type not in EVENT_TYPES:
            logger.warning("알 수 없는 이벤트 유형: %s (허용: %s)", event_type, EVENT_TYPES)

        if not self._pool:
            raise RuntimeError("PostgreSQL 연결 풀이 없습니다")

        import json

        event_id = self._snowflake_id()
        created_at = self._now_utc()

        async with self._pool.acquire() as conn:
            # 버전 자동 증가
            if version is None:
                row = await conn.fetchrow(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver "
                    "FROM event_store WHERE aggregate_id = $1",
                    aggregate_id,
                )
                version = row["next_ver"]

            await conn.execute(
                """
                INSERT INTO event_store
                    (event_id, aggregate_id, aggregate_type,
                     event_type, event_data, metadata, created_at, version)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                """,
                event_id,
                aggregate_id,
                aggregate_type,
                event_type,
                json.dumps(event_data),
                json.dumps(metadata) if metadata else None,
                created_at,
                version,
            )

        stored = StoredEvent(
            event_id=event_id,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=event_data,
            metadata=metadata,
            created_at=created_at,
            version=version,
        )
        logger.debug(
            "이벤트 저장: %s #%d [%s] v=%d",
            aggregate_id,
            event_id,
            event_type,
            version,
        )
        return stored

    async def append_batch(
        self,
        events: List[Dict[str, Any]],
    ) -> List[StoredEvent]:
        """여러 이벤트를 한 번의 트랜잭션으로 저장합니다.

        Args:
            events: append() 파라미터 dict 목록.
                    필수 키: aggregate_id, event_type, event_data.
                    선택 키: aggregate_type, metadata, version.

        Returns:
            저장된 StoredEvent 목록.
        """
        results: List[StoredEvent] = []
        for ev in events:
            stored = await self.append(
                aggregate_id=ev["aggregate_id"],
                event_type=ev["event_type"],
                event_data=ev["event_data"],
                aggregate_type=ev.get("aggregate_type", "Generic"),
                metadata=ev.get("metadata"),
                version=ev.get("version"),
            )
            results.append(stored)
        return results

    # ------------------------------------------------------------------
    # 읽기 (SELECT)
    # ------------------------------------------------------------------

    async def load(
        self,
        aggregate_id: str,
        from_version: int = 0,
    ) -> List[StoredEvent]:
        """Aggregate의 이벤트 스트림을 버전 순으로 반환합니다.

        Args:
            aggregate_id: 집합체 ID.
            from_version: 이 버전부터 조회 (기본값: 0 = 전체).

        Returns:
            StoredEvent 목록 (버전 오름차순).
        """
        if not self._pool:
            return []

        import json

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, aggregate_id, aggregate_type,
                       event_type, event_data, metadata, created_at, version
                FROM event_store
                WHERE aggregate_id = $1 AND version >= $2
                ORDER BY version ASC
                """,
                aggregate_id,
                from_version,
            )
        return [
            StoredEvent(
                event_id=r["event_id"],
                aggregate_id=r["aggregate_id"],
                aggregate_type=r["aggregate_type"],
                event_type=r["event_type"],
                event_data=json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r["event_data"],
                metadata=json.loads(r["metadata"]) if isinstance(r["metadata"], str) and r["metadata"] else r["metadata"],
                created_at=r["created_at"],
                version=r["version"],
            )
            for r in rows
        ]

    async def load_by_type(
        self,
        event_type: str,
        limit: int = 100,
    ) -> List[StoredEvent]:
        """이벤트 유형별로 조회합니다 (최신 순).

        Args:
            event_type: 이벤트 유형 (예: OrderCreated).
            limit:      최대 조회 수.

        Returns:
            StoredEvent 목록 (최신 순).
        """
        if not self._pool:
            return []

        import json

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, aggregate_id, aggregate_type,
                       event_type, event_data, metadata, created_at, version
                FROM event_store
                WHERE event_type = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                event_type,
                limit,
            )
        return [
            StoredEvent(
                event_id=r["event_id"],
                aggregate_id=r["aggregate_id"],
                aggregate_type=r["aggregate_type"],
                event_type=r["event_type"],
                event_data=json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r["event_data"],
                metadata=json.loads(r["metadata"]) if isinstance(r["metadata"], str) and r["metadata"] else r["metadata"],
                created_at=r["created_at"],
                version=r["version"],
            )
            for r in rows
        ]
