#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap Fill 우선순위 큐 (Redis Sorted Set)

우선순위:
  HIGH   (score=10): 거래량 상위, 관심 종목
  MEDIUM (score=5):  일반 종목
  LOW    (score=1):  저유동성 종목

자료구조: Sorted Set (ZADD/ZPOPMAX)
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

LOG = logging.getLogger("redis.queue.gap_queue")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson  # type: ignore
    ORJSON_AVAILABLE = False

QUEUE_KEY = "gap_fill_queue"

PRIORITY_SCORES = {
    "HIGH":   10,
    "MEDIUM": 5,
    "LOW":    1,
}


class GapQueue:
    """
    Gap Fill 우선순위 큐.
    
    Redis Sorted Set 기반:
    - enqueue: ZADD (score = 우선순위)
    - dequeue: ZPOPMAX (높은 score 우선)
    - size:    ZCARD
    """

    def __init__(self, client=None, queue_key: str = QUEUE_KEY):
        self.client = client
        self.queue_key = queue_key

    async def enqueue(
        self,
        symbol: str,
        timeframe: str,
        gap_start: datetime,
        gap_end: datetime,
        priority: str = "MEDIUM",
    ) -> bool:
        """Gap Fill 태스크 큐 등록"""
        if not self.client:
            return False
        try:
            score = PRIORITY_SCORES.get(priority.upper(), 5)
            task = {
                "symbol": symbol,
                "timeframe": timeframe,
                "gap_start": gap_start.isoformat() if hasattr(gap_start, "isoformat") else str(gap_start),
                "gap_end": gap_end.isoformat() if hasattr(gap_end, "isoformat") else str(gap_end),
                "priority": priority,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if ORJSON_AVAILABLE:
                serialized = orjson.dumps(task)
            else:
                serialized = orjson.dumps(task).encode()
            await self.client.zadd(self.queue_key, {serialized: score})
            LOG.debug("Gap 큐 등록: %s %s (%s, score=%d)", symbol, timeframe, priority, score)
            return True
        except Exception as e:
            LOG.error("Gap 큐 등록 실패: %s", e)
            return False

    async def enqueue_batch(self, tasks: List[Dict[str, Any]]) -> int:
        """배치 등록"""
        count = 0
        for t in tasks:
            ok = await self.enqueue(
                symbol=t.get("symbol", ""),
                timeframe=t.get("timeframe", "1m"),
                gap_start=t.get("gap_start", datetime.now(timezone.utc)),
                gap_end=t.get("gap_end", datetime.now(timezone.utc)),
                priority=t.get("priority", "MEDIUM"),
            )
            if ok:
                count += 1
        return count

    async def dequeue(self, count: int = 1) -> List[Dict[str, Any]]:
        """높은 우선순위부터 N개 디큐 (ZPOPMAX)"""
        if not self.client:
            return []
        try:
            items = await self.client.zpopmax(self.queue_key, count)
            tasks = []
            for item_bytes, score in items:
                try:
                    task = orjson.loads(item_bytes) if ORJSON_AVAILABLE else {}
                    task["_score"] = score
                    tasks.append(task)
                except Exception:
                    continue
            return tasks
        except Exception as e:
            LOG.error("Gap 큐 디큐 실패: %s", e)
            return []

    async def size(self) -> int:
        """큐 크기"""
        if not self.client:
            return 0
        try:
            return await self.client.zcard(self.queue_key)
        except Exception:
            return 0

    async def clear(self) -> bool:
        """큐 비우기"""
        if not self.client:
            return False
        try:
            await self.client.delete(self.queue_key)
            return True
        except Exception as e:
            LOG.error("Gap 큐 초기화 실패: %s", e)
            return False
