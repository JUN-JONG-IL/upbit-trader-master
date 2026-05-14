#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka → TimescaleDB 파이프라인 (Consumer 1)

목적:
    DB설계.md §5 Consumer 1:
    Kafka 캔들 토픽(candle.1m, candle.5m, candle.1h)에서 메시지를 소비하고
    TimescaleDB candles Hypertable에 1000개 단위 배치 UPSERT합니다.

사용 예:
    pipeline = KafkaToTimescale(pool=pg_pool)
    await pipeline.start()
    await pipeline.run()      # 블로킹 — Ctrl+C로 중지
    await pipeline.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TOPICS = ["candle.1m", "candle.5m", "candle.1h"]
_DEFAULT_GROUP = "timescale-writer"


class KafkaToTimescale:
    """Kafka Consumer → TimescaleDB 배치 UPSERT 파이프라인.

    Consumer 1 역할: 캔들 데이터를 TimescaleDB candles 테이블로 저장.
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
            pool:       asyncpg 연결 풀 (TimescaleDB).
            topics:     구독할 Kafka 토픽 목록.
            group_id:   Kafka Consumer 그룹 ID.
            batch_size: 배치 UPSERT 크기.
        """
        self._pool = pool
        self._topics = topics or _DEFAULT_TOPICS
        self._group_id = group_id
        self._batch_size = batch_size
        self._consumer = None
        self._writer = None
        self._running = False

    async def start(self) -> None:
        """Consumer와 CandleWriter를 초기화합니다."""
        from kafka.consumer import KafkaConsumer
        from timescale.operations.candle_writer import CandleWriter

        self._consumer = KafkaConsumer(
            topics=self._topics,
            group_id=self._group_id,
            batch_size=self._batch_size,
        )
        await self._consumer.start()

        self._writer = CandleWriter(self._pool, batch_size=self._batch_size)
        self._running = True
        logger.info("✅ KafkaToTimescale 시작 (topics=%s)", self._topics)

    async def stop(self) -> None:
        """파이프라인을 중지합니다."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._writer:
            flushed = await self._writer.flush()
            logger.info("✅ KafkaToTimescale 중지 (마지막 flush: %d)", flushed)

    async def run(self) -> None:
        """메시지를 소비하고 TimescaleDB에 저장합니다 (블로킹).

        stop()이 호출될 때까지 실행됩니다.
        """
        if not self._consumer:
            logger.warning("KafkaToTimescale이 start()되지 않았습니다")
            return

        async def _handle(msg: Dict[str, Any]) -> None:
            if self._writer:
                await self._writer.upsert(msg)

        await self._consumer.consume(_handle)

    async def run_once(self) -> int:
        """단일 배치를 소비하고 저장합니다 (테스트/수동 트리거용).

        Returns:
            저장된 캔들 수.
        """
        if not self._consumer or not self._writer:
            return 0
        batch = await self._consumer.consume_batch()
        if not batch:
            return 0
        return await self._writer.upsert_batch(batch)
