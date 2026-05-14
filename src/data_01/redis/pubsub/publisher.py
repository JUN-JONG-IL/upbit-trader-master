#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Pub/Sub 발행자

채널:
  - timescale:events : 전역 이벤트 (backfill.started, gap.detected 등)
  - candles:{symbol}:{tf}: 심볼별 실시간 캔들 업데이트
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

LOG = logging.getLogger("redis.pubsub.publisher")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson  # type: ignore
    ORJSON_AVAILABLE = False

GLOBAL_CHANNEL = "timescale:events"


class Publisher:
    """Redis Pub/Sub 발행자"""

    def __init__(self, client=None):
        self.client = client
        self._published = 0
        self._failed = 0

    async def publish_candle(
        self, symbol: str, timeframe: str, time: datetime,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """심볼별 캔들 업데이트 발행"""
        if not self.client:
            return False
        try:
            channel = f"candles:{symbol}:{timeframe}"
            payload = {
                "symbol": symbol, "timeframe": timeframe,
                "time": time.isoformat() if hasattr(time, "isoformat") else str(time),
                "data": data or {},
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
            msg = orjson.dumps(payload) if ORJSON_AVAILABLE else str(payload).encode()
            await self.client.publish(channel, msg)
            self._published += 1
            return True
        except Exception as e:
            LOG.error("캔들 발행 실패: %s", e)
            self._failed += 1
            return False

    async def publish_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """전역 이벤트 발행 (timescale:events)"""
        if not self.client:
            return False
        try:
            data = {
                "event": event_type,
                "payload": payload or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            msg = orjson.dumps(data) if ORJSON_AVAILABLE else str(data).encode()
            await self.client.publish(GLOBAL_CHANNEL, msg)
            self._published += 1
            return True
        except Exception as e:
            LOG.error("이벤트 발행 실패 (%s): %s", event_type, e)
            self._failed += 1
            return False

    async def publish_batch(self, updates: List[Dict[str, Any]]) -> int:
        """배치 발행"""
        count = 0
        for u in updates:
            ok = await self.publish_candle(
                symbol=u.get("symbol", ""),
                timeframe=u.get("timeframe", ""),
                time=u.get("time", datetime.now(timezone.utc)),
                data=u.get("data"),
            )
            if ok:
                count += 1
        return count

    def get_stats(self) -> Dict[str, int]:
        return {"published": self._published, "failed": self._failed}
