#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 비동기 Producer (aiokafka 기반)

목적:
    DB설계.md §2 Kafka 토픽으로 캔들/호가/체결/이벤트 메시지를 전송합니다.
    - LZ4 압축으로 50% 크기 감소
    - 배치 전송 (linger_ms=10ms, batch_size=16KB)
    - orjson 직렬화로 고성능 JSON 인코딩

지원 토픽:
    ticker.raw, orderbook.raw, trade.raw
    candle.1m, candle.5m, candle.1h
    trading.events, order.created, order.filled

환경 변수:
    KAFKA_BROKERS:          브로커 주소 (쉼표 구분, 기본값: localhost:9092)
    KAFKA_COMPRESSION_TYPE: 압축 방식 (기본값: lz4)

사용 예:
    producer = KafkaProducer()
    await producer.start()
    await producer.send_candle("candle.1m", candle_dict)
    await producer.stop()
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaProducer  # type: ignore
    _AIOKAFKA_AVAILABLE = True
except ImportError:
    AIOKafkaProducer = None  # type: ignore
    _AIOKAFKA_AVAILABLE = False

try:
    import orjson
    def _serialize(obj: Any) -> bytes:
        return orjson.dumps(obj)
except ImportError:
    import json
    def _serialize(obj: Any) -> bytes:
        return json.dumps(obj, default=str).encode()


def _get_brokers() -> str:
    return os.getenv("KAFKA_BROKERS", "localhost:9092")


class KafkaProducer:
    """aiokafka 기반 비동기 Kafka Producer.

    LZ4 압축 및 배치 전송으로 고처리량(>10,000 msg/sec)을 달성합니다.
    """

    def __init__(
        self,
        brokers: Optional[str] = None,
        compression: str = "lz4",
        linger_ms: int = 10,
        batch_size: int = 16_384,
    ) -> None:
        """
        Args:
            brokers:     카프카 브로커 주소 (쉼표 구분). None이면 환경 변수 사용.
            compression: 압축 방식 (기본값: lz4).
            linger_ms:   배치 대기 시간(ms) (기본값: 10).
            batch_size:  배치 최대 크기(bytes) (기본값: 16KB).
        """
        self._brokers = brokers or _get_brokers()
        self._compression = os.getenv("KAFKA_COMPRESSION_TYPE", compression)
        self._linger_ms = linger_ms
        self._batch_size = batch_size
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        """Producer를 초기화하고 브로커에 연결합니다."""
        if not _AIOKAFKA_AVAILABLE:
            logger.warning("aiokafka 미설치 — KafkaProducer 비활성화")
            return
        if self._producer:
            return
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._brokers,
                value_serializer=_serialize,
                compression_type=self._compression,
                linger_ms=self._linger_ms,
                batch_size=self._batch_size,
            )
            await self._producer.start()
            logger.info("✅ KafkaProducer 시작 (brokers=%s, compression=%s)", self._brokers, self._compression)
        except Exception as exc:
            logger.error("❌ KafkaProducer 시작 실패: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        """Producer를 종료합니다."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("✅ KafkaProducer 종료")

    async def send(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> bool:
        """메시지를 지정 토픽으로 전송합니다.

        Args:
            topic: 대상 토픽.
            value: 전송할 데이터 dict.
            key:   파티션 키 (선택).

        Returns:
            전송 성공 여부.
        """
        if not self._producer:
            return False
        try:
            key_bytes = key.encode() if isinstance(key, str) else key
            await self._producer.send(topic, value=value, key=key_bytes)
            return True
        except Exception as exc:
            logger.error("Kafka 전송 실패 (topic=%s): %s", topic, exc)
            return False

    async def send_and_wait(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> bool:
        """메시지를 전송하고 브로커 확인(ack)을 기다립니다.

        Args:
            topic: 대상 토픽.
            value: 전송할 데이터 dict.
            key:   파티션 키 (선택).

        Returns:
            전송 성공 여부.
        """
        if not self._producer:
            return False
        try:
            key_bytes = key.encode() if isinstance(key, str) else key
            await self._producer.send_and_wait(topic, value=value, key=key_bytes)
            return True
        except Exception as exc:
            logger.error("Kafka send_and_wait 실패 (topic=%s): %s", topic, exc)
            return False

    # ------------------------------------------------------------------
    # 편의 메서드 (도메인별)
    # ------------------------------------------------------------------

    async def send_candle(self, topic: str, candle: Dict[str, Any]) -> bool:
        """캔들 데이터를 전송합니다. 키는 symbol/timeframe 조합입니다.

        Args:
            topic:  candle.1m / candle.5m / candle.1h 등.
            candle: 캔들 dict.
        """
        key = f"{candle.get('symbol', '')}:{candle.get('timeframe', '')}"
        return await self.send(topic, candle, key=key)

    async def send_ticker(self, ticker: Dict[str, Any]) -> bool:
        """틱 데이터를 ticker.raw 토픽으로 전송합니다."""
        return await self.send("ticker.raw", ticker, key=ticker.get("symbol"))

    async def send_orderbook(self, orderbook: Dict[str, Any]) -> bool:
        """호가 데이터를 orderbook.raw 토픽으로 전송합니다."""
        return await self.send("orderbook.raw", orderbook, key=orderbook.get("symbol"))

    async def send_trade(self, trade: Dict[str, Any]) -> bool:
        """체결 데이터를 trade.raw 토픽으로 전송합니다."""
        return await self.send("trade.raw", trade, key=trade.get("symbol"))

    async def send_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """거래 이벤트를 trading.events 토픽으로 전송합니다.

        Args:
            event_type: 이벤트 유형 (예: OrderCreated).
            payload:    이벤트 페이로드.
        """
        message = {"event_type": event_type, "payload": payload}
        return await self.send("trading.events", message, key=payload.get("aggregate_id"))

    @property
    def is_connected(self) -> bool:
        """Producer가 연결된 상태인지 반환합니다."""
        return self._producer is not None

    async def __aenter__(self) -> "KafkaProducer":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
