#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka → PostgreSQL Event Store 파이프라인 (Consumer 3)

목적:
    DB설계.md §5 Consumer 3:
    Kafka trading.events 토픽에서 이벤트를 소비하고
    PostgreSQL Event Store(event_store 테이블)에 Append-Only로 저장합니다.

사용 예:
    pipeline = KafkaToEventStore(pool=pg_pool)
    await pipeline.start()
    await pipeline.run()
    await pipeline.stop()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TOPICS = ["trading.events", "order.created", "order.filled"]
_DEFAULT_GROUP = "event-store-writer"


class KafkaToEventStore:
    """Kafka Consumer → PostgreSQL Event Store 파이프라인.

    Consumer 3 역할: 이벤트를 불변 로그(Append-Only)로 저장.
    """

    def __init__(
        self,
        pool=None,
        topics: Optional[List[str]] = None,
        group_id: str = _DEFAULT_GROUP,
        batch_size: int = 1_000,
    ) -> None:
        """
        Args:
            pool:       asyncpg 연결 풀 (PostgreSQL Primary).
            topics:     구독할 Kafka 토픽 목록.
            group_id:   Kafka Consumer 그룹 ID.
            batch_size: 배치 크기.
        """
        self._pool = pool
        self._topics = topics or _DEFAULT_TOPICS
        self._group_id = group_id
        self._batch_size = batch_size
        self._consumer = None
        self._store = None
        self._running = False
        self._total_stored = 0

    async def start(self) -> None:
        """Consumer와 EventStore를 초기화합니다."""
        from kafka.consumer import KafkaConsumer
        from postgres.event_store import EventStore

        self._consumer = KafkaConsumer(
            topics=self._topics,
            group_id=self._group_id,
            batch_size=self._batch_size,
        )
        await self._consumer.start()
        self._store = EventStore(self._pool)
        self._running = True
        logger.info("✅ KafkaToEventStore 시작 (topics=%s)", self._topics)

    async def stop(self) -> None:
        """파이프라인을 중지합니다."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("✅ KafkaToEventStore 중지 (총 저장: %d)", self._total_stored)

    async def run(self) -> None:
        """메시지를 소비하고 Event Store에 저장합니다 (블로킹)."""
        if not self._consumer:
            return

        async def _handle(msg: Dict[str, Any]) -> None:
            await self._store_event(msg)

        await self._consumer.consume(_handle)

    async def run_once(self) -> int:
        """단일 배치를 소비하고 저장합니다."""
        if not self._consumer or not self._store:
            return 0
        batch = await self._consumer.consume_batch()
        if not batch:
            return 0
        count = 0
        for msg in batch:
            try:
                await self._store_event(msg)
                count += 1
            except Exception as exc:
                logger.error("이벤트 저장 오류: %s", exc)
        return count

    async def _store_event(self, msg: Dict[str, Any]) -> None:
        """단일 이벤트 메시지를 Event Store에 저장합니다."""
        if not self._store:
            return
        event_type = msg.get("event_type", "Unknown")
        payload = msg.get("payload", msg)
        aggregate_id = payload.get("aggregate_id") or payload.get("order_id") or "unknown"
        aggregate_type = payload.get("aggregate_type", "Trading")

        try:
            await self._store.append(
                aggregate_id=str(aggregate_id),
                event_type=event_type,
                event_data=payload,
                aggregate_type=aggregate_type,
            )
            self._total_stored += 1
        except Exception as exc:
            logger.error("_store_event 실패 (event_type=%s): %s", event_type, exc)
