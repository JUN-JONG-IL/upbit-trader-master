#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL Event Store → MongoDB Read Model 파이프라인 (Consumer 4)

목적:
    DB설계.md §5 Consumer 4:
    PostgreSQL NOTIFY(event_store_channel)를 수신하거나
    Kafka trading.events를 소비하여 MongoDB CQRS Read Model
    (orders_view, trades_view)을 갱신합니다.

CQRS 패턴:
    Write Side: PostgreSQL Event Store (Append-Only)
    Read Side:  MongoDB Projection (orders_view, trades_view)

사용 예:
    builder = EventToMongo(db=mongo_db)
    await builder.start()
    await builder.run()
    await builder.stop()
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TOPICS = ["trading.events", "order.created", "order.filled"]
_DEFAULT_GROUP = "mongo-projection-builder"

# MongoDB Read Model 컬렉션
_COL_ORDERS = "orders_view"
_COL_TRADES = "trades_view"


class EventToMongo:
    """PostgreSQL Event → MongoDB Projection 빌더 (CQRS Consumer 4).

    이벤트 유형별 핸들러:
        OrderCreated  → orders_view 생성
        OrderFilled   → orders_view 갱신, trades_view 생성
        TradeExecuted → trades_view 갱신
        BalanceUpdated → (향후 balance_view 반영)
    """

    def __init__(
        self,
        db=None,
        topics: Optional[List[str]] = None,
        group_id: str = _DEFAULT_GROUP,
        batch_size: int = 1_000,
    ) -> None:
        """
        Args:
            db:         motor AsyncIOMotorDatabase 인스턴스.
            topics:     구독할 Kafka 토픽 목록.
            group_id:   Kafka Consumer 그룹 ID.
            batch_size: 배치 크기.
        """
        self._db = db
        self._topics = topics or _DEFAULT_TOPICS
        self._group_id = group_id
        self._batch_size = batch_size
        self._consumer = None
        self._running = False
        self._total_projected = 0

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
        logger.info("✅ EventToMongo 시작 (topics=%s)", self._topics)

    async def stop(self) -> None:
        """파이프라인을 중지합니다."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("✅ EventToMongo 중지 (총 프로젝션: %d)", self._total_projected)

    async def run(self) -> None:
        """이벤트를 소비하고 MongoDB Read Model을 갱신합니다 (블로킹)."""
        if not self._consumer:
            return

        async def _handle(msg: Dict[str, Any]) -> None:
            await self._project(msg)

        await self._consumer.consume(_handle)

    async def run_once(self) -> int:
        """단일 배치를 소비하고 프로젝션합니다."""
        if not self._consumer:
            return 0
        batch = await self._consumer.consume_batch()
        count = 0
        for msg in batch:
            try:
                await self._project(msg)
                count += 1
            except Exception as exc:
                logger.error("프로젝션 오류: %s", exc)
        return count

    async def project_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """단일 이벤트를 MongoDB Read Model에 반영합니다.

        Args:
            event_type: 이벤트 유형.
            payload:    이벤트 페이로드.

        Returns:
            성공 여부.
        """
        msg = {"event_type": event_type, "payload": payload}
        try:
            await self._project(msg)
            return True
        except Exception as exc:
            logger.error("project_event 실패 (%s): %s", event_type, exc)
            return False

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    async def _project(self, msg: Dict[str, Any]) -> None:
        """이벤트 유형에 따라 적절한 핸들러를 호출합니다."""
        event_type = msg.get("event_type", "")
        payload = msg.get("payload", msg)

        handlers = {
            "OrderCreated": self._on_order_created,
            "OrderFilled": self._on_order_filled,
            "TradeExecuted": self._on_trade_executed,
            "BalanceUpdated": self._on_balance_updated,
        }
        handler = handlers.get(event_type)
        if handler:
            await handler(payload)
            self._total_projected += 1
        else:
            logger.debug("미처리 이벤트 유형: %s", event_type)

    async def _on_order_created(self, payload: Dict[str, Any]) -> None:
        """OrderCreated → orders_view 생성."""
        if not self._db:
            return
        order_id = str(payload.get("order_id") or payload.get("aggregate_id", ""))
        doc = {
            "order_id": order_id,
            "symbol": payload.get("symbol", ""),
            "side": payload.get("side", ""),
            "order_type": payload.get("order_type", ""),
            "status": "pending",
            "price": payload.get("price"),
            "quantity": payload.get("quantity", 0),
            "filled_qty": 0,
            "is_paper": payload.get("is_paper", False),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            await self._db[_COL_ORDERS].update_one(
                {"order_id": order_id},
                {"$set": doc, "$setOnInsert": {"_created": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except Exception as exc:
            logger.error("orders_view 생성 실패: %s", exc)

    async def _on_order_filled(self, payload: Dict[str, Any]) -> None:
        """OrderFilled → orders_view 갱신."""
        if not self._db:
            return
        order_id = str(payload.get("order_id") or payload.get("aggregate_id", ""))
        try:
            await self._db[_COL_ORDERS].update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "filled",
                        "filled_qty": payload.get("filled_qty", 0),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
        except Exception as exc:
            logger.error("orders_view 갱신(filled) 실패: %s", exc)

    async def _on_trade_executed(self, payload: Dict[str, Any]) -> None:
        """TradeExecuted → trades_view 생성."""
        if not self._db:
            return
        trade_id = str(payload.get("trade_id") or payload.get("aggregate_id", ""))
        doc = {
            "trade_id": trade_id,
            "order_id": str(payload.get("order_id", "")),
            "symbol": payload.get("symbol", ""),
            "side": payload.get("side", ""),
            "price": payload.get("price", 0),
            "quantity": payload.get("quantity", 0),
            "fee": payload.get("fee", 0),
            "is_paper": payload.get("is_paper", False),
            "executed_at": datetime.now(timezone.utc),
        }
        try:
            await self._db[_COL_TRADES].update_one(
                {"trade_id": trade_id},
                {"$set": doc, "$setOnInsert": {"_created": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except Exception as exc:
            logger.error("trades_view 생성 실패: %s", exc)

    async def _on_balance_updated(self, payload: Dict[str, Any]) -> None:
        """BalanceUpdated — 향후 balance_view 반영 (현재 로그만)."""
        logger.debug("BalanceUpdated 수신 (미구현): %s", payload)
