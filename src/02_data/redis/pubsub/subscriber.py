#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Pub/Sub 구독자

UI 실시간 업데이트 및 AI 추론 트리거.
"""
import asyncio
import logging
from typing import Optional, Dict, List, Callable, Any

LOG = logging.getLogger("redis.pubsub.subscriber")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson  # type: ignore
    ORJSON_AVAILABLE = False


class Subscriber:
    """Redis Pub/Sub 구독자"""

    def __init__(self, client=None):
        self.client = client
        self._pubsub = None
        self._handlers: Dict[str, List[Callable]] = {}
        self._running = False

    async def subscribe(self, pattern: str, handler: Callable) -> bool:
        """패턴 구독 등록"""
        if not self.client:
            return False
        try:
            if self._pubsub is None:
                self._pubsub = self.client.pubsub()
            await self._pubsub.psubscribe(pattern)
            if pattern not in self._handlers:
                self._handlers[pattern] = []
            self._handlers[pattern].append(handler)
            LOG.info("✅ 구독 등록: %s", pattern)
            return True
        except Exception as e:
            LOG.error("구독 실패: %s", e)
            return False

    async def unsubscribe(self, pattern: str) -> bool:
        """구독 해제"""
        if not self._pubsub:
            return False
        try:
            await self._pubsub.punsubscribe(pattern)
            self._handlers.pop(pattern, None)
            return True
        except Exception as e:
            LOG.error("구독 해제 실패: %s", e)
            return False

    async def listen(self):
        """메시지 수신 루프"""
        if not self._pubsub:
            return
        self._running = True
        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                if message.get("type") == "pmessage":
                    pattern = message.get("pattern", b"")
                    if isinstance(pattern, bytes):
                        pattern = pattern.decode()
                    data = message.get("data", b"")
                    try:
                        parsed = orjson.loads(data) if ORJSON_AVAILABLE else {}
                    except Exception:
                        parsed = {}
                    for pat, handlers in self._handlers.items():
                        if pat == pattern:
                            for h in handlers:
                                try:
                                    await h(message.get("channel", b"").decode(), parsed)
                                except Exception as e:
                                    LOG.error("핸들러 실행 실패: %s", e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOG.error("수신 루프 에러: %s", e)

    async def close(self):
        self._running = False
        if self._pubsub:
            await self._pubsub.close()
