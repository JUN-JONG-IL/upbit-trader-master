#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 비동기 Consumer (aiokafka 기반)

목적:
    DB설계.md §5 Consumer 구성에 따라 Kafka 토픽을 구독하고
    콜백 핸들러로 메시지를 처리합니다.

Consumer 구성 (DB설계.md):
    Consumer 1: TimescaleDB Writer (배치 1000개)
    Consumer 2: ClickHouse Writer
    Consumer 3: PostgreSQL Event Store Writer
    Consumer 4: MongoDB Projection Builder

환경 변수:
    KAFKA_BROKERS:            브로커 주소 (쉼표 구분)
    KAFKA_GROUP_ID:           컨슈머 그룹 ID
    KAFKA_AUTO_OFFSET_RESET:  오프셋 리셋 정책 (earliest/latest)

사용 예:
    consumer = KafkaConsumer(topics=["candle.1m"], group_id="timescale-writer")
    await consumer.start()
    async for msg in consumer:
        await handle(msg)
    await consumer.stop()
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaConsumer, ConsumerRecord  # type: ignore
    _AIOKAFKA_AVAILABLE = True
except ImportError:
    AIOKafkaConsumer = None  # type: ignore
    ConsumerRecord = None    # type: ignore
    _AIOKAFKA_AVAILABLE = False

try:
    import orjson
    def _deserialize(data: bytes) -> Any:
        return orjson.loads(data) if data else None
except ImportError:
    import json
    def _deserialize(data: bytes) -> Any:
        return json.loads(data) if data else None

MessageHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


def _get_brokers() -> str:
    return os.getenv("KAFKA_BROKERS", "localhost:9092")


class KafkaConsumer:
    """aiokafka 기반 비동기 Kafka Consumer.

    배치 소비(1000개 단위)와 콜백 핸들러를 지원합니다.
    """

    def __init__(
        self,
        topics: List[str],
        group_id: Optional[str] = None,
        brokers: Optional[str] = None,
        auto_offset_reset: str = "earliest",
        batch_size: int = 1_000,
        batch_timeout_ms: int = 5_000,
    ) -> None:
        """
        Args:
            topics:            구독할 토픽 목록.
            group_id:          컨슈머 그룹 ID. None이면 환경 변수 사용.
            brokers:           브로커 주소. None이면 환경 변수 사용.
            auto_offset_reset: 오프셋 리셋 정책.
            batch_size:        배치 최대 크기 (기본값: 1000).
            batch_timeout_ms:  배치 대기 최대 시간(ms) (기본값: 5000).
        """
        self._topics = topics
        self._group_id = group_id or os.getenv("KAFKA_GROUP_ID", "upbit-trader")
        self._brokers = brokers or _get_brokers()
        self._auto_offset_reset = auto_offset_reset
        self._batch_size = batch_size
        self._batch_timeout_ms = batch_timeout_ms
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

    async def start(self) -> None:
        """Consumer를 초기화하고 브로커에 연결합니다."""
        if not _AIOKAFKA_AVAILABLE:
            logger.warning("aiokafka 미설치 — KafkaConsumer 비활성화")
            return
        if self._consumer:
            return
        try:
            self._consumer = AIOKafkaConsumer(
                *self._topics,
                bootstrap_servers=self._brokers,
                group_id=self._group_id,
                auto_offset_reset=self._auto_offset_reset,
                value_deserializer=_deserialize,
                enable_auto_commit=True,
                auto_commit_interval_ms=1000,
            )
            await self._consumer.start()
            self._running = True
            logger.info(
                "✅ KafkaConsumer 시작 (topics=%s, group=%s)",
                self._topics,
                self._group_id,
            )
        except Exception as exc:
            logger.error("❌ KafkaConsumer 시작 실패: %s", exc)
            self._consumer = None

    async def stop(self) -> None:
        """Consumer를 종료합니다."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            logger.info("✅ KafkaConsumer 종료 (group=%s)", self._group_id)

    async def consume(self, handler: MessageHandler) -> None:
        """메시지를 연속 소비하며 핸들러에 전달합니다.

        Args:
            handler: async 메시지 처리 콜백.
                     인자: 역직렬화된 메시지 dict.

        이 메서드는 `stop()`이 호출될 때까지 블로킹합니다.
        """
        if not self._consumer:
            logger.warning("KafkaConsumer가 시작되지 않았습니다")
            return
        while self._running:
            try:
                data = await self._consumer.getmany(
                    timeout_ms=self._batch_timeout_ms,
                    max_records=self._batch_size,
                )
                for _tp, records in data.items():
                    for record in records:
                        try:
                            await handler(record.value)
                        except Exception as exc:
                            logger.error(
                                "메시지 처리 오류 (topic=%s, offset=%d): %s",
                                record.topic,
                                record.offset,
                                exc,
                            )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("KafkaConsumer 오류: %s", exc)
                await asyncio.sleep(1)

    async def consume_batch(self) -> List[Dict[str, Any]]:
        """배치 크기만큼 메시지를 소비하고 반환합니다.

        Returns:
            역직렬화된 메시지 dict 목록.
        """
        if not self._consumer:
            return []
        try:
            data = await self._consumer.getmany(
                timeout_ms=self._batch_timeout_ms,
                max_records=self._batch_size,
            )
            result: List[Dict[str, Any]] = []
            for _tp, records in data.items():
                for record in records:
                    if record.value is not None:
                        result.append(record.value)
            return result
        except Exception as exc:
            logger.error("consume_batch 오류: %s", exc)
            return []

    def __aiter__(self):
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if not self._consumer or not self._running:
            raise StopAsyncIteration
        try:
            record = await self._consumer.getone()
            return record.value
        except Exception:
            raise StopAsyncIteration

    @property
    def is_connected(self) -> bool:
        """Consumer가 연결된 상태인지 반환합니다."""
        return self._consumer is not None and self._running

    async def __aenter__(self) -> "KafkaConsumer":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
