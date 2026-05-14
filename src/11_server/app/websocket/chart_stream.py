#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
차트 WebSocket 스트림 - ui.chart 패치 메시지 브로드캐스트

[Responsibilities]
- WebSocket 연결 관리
- 심볼/타임프레임별 구독 관리
- throttle 500ms로 패치 메시지 전송
- Redis Pub/Sub으로 Compute 프로세스 결과 수신
"""

import time
import asyncio
import logging
from typing import Dict, Set, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# 모듈 전용 로거
logger = logging.getLogger("server.websocket.chart_stream")
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)


class ChartStream:
    """차트 WebSocket 스트림"""

    def __init__(self):
        # {websocket: set((symbol, timeframe))}
        self.connections: Dict[WebSocket, Set[Tuple[str, str]]] = {}

        # Throttle 관리
        self.last_broadcast: Dict[Tuple[str, str], float] = {}
        self.throttle_ms = 500  # 500ms throttle

    async def connect(self, websocket: WebSocket):
        """
        WebSocket 연결

        Args:
            websocket: FastAPI WebSocket 인스턴스
        """
        await websocket.accept()
        self.connections[websocket] = set()
        logger.debug("ChartStream: Client connected, total=%d", len(self.connections))

    def disconnect(self, websocket: WebSocket):
        """
        WebSocket 연결 해제

        Args:
            websocket: FastAPI WebSocket 인스턴스
        """
        if websocket in self.connections:
            try:
                del self.connections[websocket]
            except Exception:
                logger.exception("ChartStream: Error removing websocket from connections")
            logger.debug("ChartStream: Client disconnected, total=%d", len(self.connections))

    async def subscribe(self, websocket: WebSocket, symbol: str, timeframe: str):
        """
        구독 추가

        Args:
            websocket: FastAPI WebSocket 인스턴스
            symbol: 심볼 (예: "KRW-BTC")
            timeframe: 타임프레임 (예: "min_1")
        """
        if websocket in self.connections:
            self.connections[websocket].add((symbol, timeframe))
            logger.debug("ChartStream: Subscribed %s %s (client_total=%d)", symbol, timeframe, len(self.connections))

    async def unsubscribe(self, websocket: WebSocket, symbol: str, timeframe: str):
        """
        구독 해제

        Args:
            websocket: FastAPI WebSocket 인스턴스
            symbol: 심볼
            timeframe: 타임프레임
        """
        if websocket in self.connections:
            self.connections[websocket].discard((symbol, timeframe))
            logger.debug("ChartStream: Unsubscribed %s %s", symbol, timeframe)

    async def broadcast_patch(self, symbol: str, timeframe: str, patch_data: dict):
        """
        ui.chart 패치 브로드캐스트 (throttled)

        Args:
            symbol: 심볼
            timeframe: 타임프레임
            patch_data: 패치 데이터
        """
        # Throttle 체크
        key = (symbol, timeframe)
        current_time = time.time() * 1000

        if key in self.last_broadcast:
            elapsed = current_time - self.last_broadcast[key]
            if elapsed < self.throttle_ms:
                logger.debug("ChartStream: Throttled %s %s (elapsed=%.1fms)", symbol, timeframe, elapsed)
                return  # Skip

        self.last_broadcast[key] = current_time

        # 구독자에게 전송
        disconnected = []

        for ws, subscriptions in list(self.connections.items()):
            if (symbol, timeframe) in subscriptions:
                try:
                    await ws.send_json(patch_data)
                except Exception as e:
                    logger.debug("ChartStream: Send error to client: %s", e, exc_info=True)
                    disconnected.append(ws)

        # 연결 끊긴 클라이언트 제거
        for ws in disconnected:
            self.disconnect(ws)

    async def send_snapshot(self, websocket: WebSocket, symbol: str, timeframe: str, snapshot_data: dict):
        """
        초기 스냅샷 전송

        Args:
            websocket: FastAPI WebSocket 인스턴스
            symbol: 심볼
            timeframe: 타임프레임
            snapshot_data: 스냅샷 데이터
        """
        try:
            message = {
                "type": "ui.chart.snapshot",
                "ts": int(time.time() * 1000),
                "symbol": symbol,
                "timeframe": timeframe,
                "data": snapshot_data,
            }
            await websocket.send_json(message)
        except Exception as e:
            logger.debug("ChartStream: Snapshot send error: %s", e, exc_info=True)

    def get_active_subscriptions(self) -> Set[Tuple[str, str]]:
        """
        활성 구독 목록 조회

        Returns:
            set((symbol, timeframe))
        """
        all_subscriptions = set()
        for subscriptions in self.connections.values():
            all_subscriptions.update(subscriptions)

        return all_subscriptions

    def get_connection_count(self) -> int:
        """연결 수 조회"""
        return len(self.connections)