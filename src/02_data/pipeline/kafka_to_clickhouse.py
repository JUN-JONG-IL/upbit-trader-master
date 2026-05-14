#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka → ClickHouse 파이프라인 (Consumer 2)

목적:
    DB설계.md §5 Consumer 2:
    Kafka 캔들 토픽에서 메시지를 소비하고
    ClickHouse candle_events 테이블에 배치 INSERT합니다.

사용 예:
    pipeline = KafkaToClickHouse()
    await pipeline.start()
    await pipeline.run()
    await pipeline.stop()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TOPICS = ["candle.1m", "candle.5m", "candle.1h"]
_DEFAULT_GROUP = "clickhouse-writer"

_INSERT_SQL = """
INSERT INTO candle_events
    (event_id, event_time, symbol, timeframe, open, high, low, close, volume)
VALUES
"""


class KafkaToClickHouse:
    """Kafka Consumer → ClickHouse 배치 INSERT 파이프라인.

    Consumer 2 역할: 캔들 데이터를 ClickHouse COLD Tier로 전달.
    """

    def __init__(
        self,
        ch_client=None,
        topics: Optional[List[str]] = None,
        group_id: str = _DEFAULT_GROUP,
        batch_size: int = 1_000,
    ) -> None:
        """
        Args:
            ch_client:  ClickHouse 클라이언트 (clickhouse_driver.Client).
            topics:     구독할 Kafka 토픽 목록.
            group_id:   Kafka Consumer 그룹 ID.
            batch_size: 배치 INSERT 크기.
        """
        self._ch = ch_client
        self._topics = topics or _DEFAULT_TOPICS
        self._group_id = group_id
        self._batch_size = batch_size
        self._consumer = None
        self._running = False
        self._total_inserted = 0

    async def start(self) -> None:
        """Consumer를 초기화합니다."""
        from kafka.consumer import KafkaConsumer

        self._consumer = KafkaConsumer(
            topics=self._topics,
            group_id=self._group_id,
            batch_size=self._batch_size,
        )
        await self._consumer.start()
        self._running = True
        logger.info("✅ KafkaToClickHouse 시작 (topics=%s)", self._topics)

    async def stop(self) -> None:
        """파이프라인을 중지합니다."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("✅ KafkaToClickHouse 중지 (총 삽입: %d)", self._total_inserted)

    async def run(self) -> None:
        """메시지를 소비하고 ClickHouse에 저장합니다 (블로킹)."""
        if not self._consumer:
            return

        async def _handle(msg: Dict[str, Any]) -> None:
            await self._insert_one(msg)

        await self._consumer.consume(_handle)

    async def run_once(self) -> int:
        """단일 배치를 소비하고 저장합니다."""
        if not self._consumer:
            return 0
        batch = await self._consumer.consume_batch()
        if not batch:
            return 0
        return await self._insert_batch(batch)

    async def _insert_one(self, candle: Dict[str, Any]) -> None:
        await self._insert_batch([candle])

    async def _insert_batch(self, candles: List[Dict[str, Any]]) -> int:
        """ClickHouse에 배치 INSERT합니다."""
        if not self._ch or not candles:
            return 0
        import time
        ts_ms = int(time.time() * 1000)
        rows = []
        for seq, c in enumerate(candles):
            event_time = c.get("time") or c.get("timestamp")
            if hasattr(event_time, "isoformat"):
                event_time = event_time.isoformat()
            # 밀리초 타임스탬프 + 22비트 시퀀스로 고유 ID 생성
            event_id = (ts_ms << 22) | (seq & 0x3FFFFF)
            rows.append({
                "event_id": event_id,
                "event_time": str(event_time),
                "symbol": c.get("symbol", ""),
                "timeframe": c.get("timeframe", "1m"),
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
            })
        try:
            self._ch.execute(
                "INSERT INTO candle_events VALUES",
                rows,
                types_check=True,
            )
            self._total_inserted += len(rows)
            logger.debug("ClickHouse INSERT: %d행", len(rows))
            return len(rows)
        except Exception as exc:
            logger.error("ClickHouse INSERT 오류: %s", exc)
            return 0
