#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
WebSocket 연결 관리

[Responsibilities]
- 클라이언트 연결 추적 (심볼/타임프레임별)
- 실시간 데이터 발행 (Redis Pub/Sub 구독)
- 자동 재연결 지원
- 스로틀링 (500ms 간격)

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 9.1, 9.2

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Set, Tuple

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket 연결 관리자

    Redis Pub/Sub 채널에서 메시지를 수신하여
    구독 중인 클라이언트에게 브로드캐스트합니다.

    Attributes:
        connections: {WebSocket: set((symbol, timeframe))}
        throttle_ms: 브로드캐스트 스로틀 간격 (밀리초)
        redis_host: Redis 호스트
        redis_port: Redis 포트
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        throttle_ms: int = 500,
    ) -> None:
        self.redis_host: str = os.getenv("REDIS_HOST", redis_host)
        try:
            self.redis_port: int = int(os.getenv("REDIS_PORT", str(redis_port)))
        except ValueError:
            self.redis_port = redis_port
        self.throttle_ms: int = throttle_ms

        # {WebSocket: set((symbol, timeframe))}
        self.connections: Dict[WebSocket, Set[Tuple[str, str]]] = {}
        # 마지막 브로드캐스트 시각 추적
        self.last_broadcast: Dict[Tuple[str, str], float] = {}

        self._redis: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._listener_task: Optional[asyncio.Task] = None

    # ── 라이프사이클 ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Redis Pub/Sub 구독 시작 및 리스너 태스크 생성"""
        try:
            import redis as redis_lib  # type: ignore
        except ImportError:
            logger.warning("[WebSocketManager] redis 패키지 없음 - Pub/Sub 비활성화")
            return

        try:
            self._redis = redis_lib.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
            )
            self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._pubsub.subscribe("ws:chart", "ws:scanner")
            self._listener_task = asyncio.create_task(self._redis_listener())
            logger.info("[WebSocketManager] Started (Redis %s:%s)", self.redis_host, self.redis_port)
        except Exception as exc:
            logger.warning("[WebSocketManager] Redis 연결 실패: %s", exc)
            self._redis = None

    async def stop(self) -> None:
        """리스너 태스크 취소 및 Redis 연결 종료"""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listener_task = None

        if self._pubsub:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None

        logger.info("[WebSocketManager] Stopped")

    # ── 연결 관리 ─────────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        """
        WebSocket 클라이언트 연결 수락

        연결 후 클라이언트가 보내는 JSON 메시지를 처리합니다:
        - ``{"action": "subscribe", "symbol": "KRW-BTC", "timeframe": "1m"}``
        - ``{"action": "unsubscribe", "symbol": "KRW-BTC", "timeframe": "1m"}``

        Args:
            websocket: FastAPI WebSocket 인스턴스
        """
        await websocket.accept()
        self.connections[websocket] = set()
        logger.debug("[WebSocketManager] 연결됨 (총 %d개)", len(self.connections))

        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                symbol = data.get("symbol", "")
                timeframe = data.get("timeframe", "")

                if action == "subscribe" and symbol and timeframe:
                    await self.subscribe(websocket, symbol, timeframe)
                elif action == "unsubscribe" and symbol and timeframe:
                    await self.unsubscribe(websocket, symbol, timeframe)

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as exc:
            logger.debug("[WebSocketManager] 처리 오류: %s", exc)
            self.disconnect(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """클라이언트 연결 해제"""
        self.connections.pop(websocket, None)
        logger.debug("[WebSocketManager] 연결 해제 (총 %d개)", len(self.connections))

    async def subscribe(self, websocket: WebSocket, symbol: str, timeframe: str) -> None:
        """특정 심볼/타임프레임 구독 추가"""
        if websocket in self.connections:
            self.connections[websocket].add((symbol, timeframe))
            logger.debug("[WebSocketManager] 구독 추가: %s %s", symbol, timeframe)

    async def unsubscribe(self, websocket: WebSocket, symbol: str, timeframe: str) -> None:
        """특정 심볼/타임프레임 구독 제거"""
        if websocket in self.connections:
            self.connections[websocket].discard((symbol, timeframe))
            logger.debug("[WebSocketManager] 구독 제거: %s %s", symbol, timeframe)

    # ── 브로드캐스트 ──────────────────────────────────────────────────────────

    async def broadcast(self, symbol: str, timeframe: str, message: dict) -> None:
        """
        특정 심볼/타임프레임 구독자에게 메시지 브로드캐스트 (스로틀링 적용)

        Args:
            symbol: 코인 심볼 (예: "KRW-BTC")
            timeframe: 타임프레임 (예: "1m")
            message: 전송할 JSON 직렬화 가능한 딕셔너리
        """
        key = (symbol, timeframe)
        now_ms = time.time() * 1000

        if key in self.last_broadcast:
            if (now_ms - self.last_broadcast[key]) < self.throttle_ms:
                return

        self.last_broadcast[key] = now_ms
        await self._broadcast_to_subscribers(symbol, timeframe, message)

    async def broadcast_all(self, message: dict) -> None:
        """모든 연결된 클라이언트에게 메시지 브로드캐스트"""
        disconnected = []
        for ws in list(self.connections.keys()):
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug("[WebSocketManager] 전송 실패: %s", exc)
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def _broadcast_to_subscribers(
        self, symbol: str, timeframe: str, message: dict
    ) -> None:
        """심볼/타임프레임 구독자에게만 전송"""
        disconnected = []
        for ws, subs in list(self.connections.items()):
            if (symbol, timeframe) in subs:
                try:
                    await ws.send_json(message)
                except Exception as exc:
                    logger.debug("[WebSocketManager] 구독자 전송 실패: %s", exc)
                    disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    # ── Redis 리스너 ──────────────────────────────────────────────────────────

    async def _redis_listener(self) -> None:
        """Redis Pub/Sub 메시지를 수신하여 WebSocket 클라이언트에 배포"""
        logger.info("[WebSocketManager] Redis 리스너 시작")
        if not self._pubsub:
            return

        try:
            while True:
                try:
                    message = self._pubsub.get_message(timeout=0.1)
                    if message and message.get("type") == "message":
                        channel = message.get("channel", "")
                        raw = message.get("data", "")
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw) if raw else None
                        except Exception:
                            data = None

                        if data is not None:
                            if channel == "ws:chart":
                                symbol = data.get("symbol", "")
                                tf = data.get("timeframe", "")
                                if symbol and tf:
                                    await self.broadcast(symbol, tf, data)
                            elif channel == "ws:scanner":
                                await self.broadcast_all(data)

                    await asyncio.sleep(0.05)

                except Exception as exc:
                    logger.debug("[WebSocketManager] 리스너 오류: %s", exc)
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug("[WebSocketManager] 리스너 취소됨")
        except Exception as exc:
            logger.warning("[WebSocketManager] 리스너 중단: %s", exc)
        finally:
            logger.info("[WebSocketManager] Redis 리스너 종료")

    # ── 속성 ──────────────────────────────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        """현재 연결된 클라이언트 수"""
        return len(self.connections)

    @property
    def is_redis_connected(self) -> bool:
        """Redis 연결 상태"""
        return self._redis is not None


# 전역 인스턴스
_env_host = os.getenv("REDIS_HOST", "localhost")
try:
    _env_port = int(os.getenv("REDIS_PORT", "6379"))
except ValueError:
    _env_port = 6379

websocket_manager = WebSocketManager(redis_host=_env_host, redis_port=_env_port)
