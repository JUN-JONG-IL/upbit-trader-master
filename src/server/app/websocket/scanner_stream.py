#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
스캐너 WebSocket 스트림 - scanner.results delta 메시지 브로드캐스트

[Responsibilities]
- WebSocket 연결 관리
- scanner 결과 delta 전송 (add/remove)
- 200~500ms 주기로 delta coalesce 및 전송
"""

import time
import asyncio
import logging
from typing import Set, List, Dict
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# 모듈 전용 로거
logger = logging.getLogger("server.websocket.scanner_stream")
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)


class ScannerStream:
    """스캐너 WebSocket 스트림"""

    def __init__(self):
        # WebSocket 연결 목록
        self.connections: Set[WebSocket] = set()

        # Delta 큐 (coalesce용)
        self.pending_deltas: Dict[str, List[dict]] = {"add": [], "remove": []}

        # 플러시 간격
        self.flush_interval_ms = 500  # 500ms
        self.last_flush = time.time() * 1000

    async def connect(self, websocket: WebSocket):
        """
        WebSocket 연결

        Args:
            websocket: FastAPI WebSocket 인스턴스
        """
        await websocket.accept()
        self.connections.add(websocket)
        logger.debug("ScannerStream: Client connected, total=%d", len(self.connections))

    def disconnect(self, websocket: WebSocket):
        """
        WebSocket 연결 해제

        Args:
            websocket: FastAPI WebSocket 인스턴스
        """
        self.connections.discard(websocket)
        logger.debug("ScannerStream: Client disconnected, total=%d", len(self.connections))

    def queue_delta(self, add_list: List[dict], remove_list: List[dict]):
        """
        delta 큐에 추가 (coalesce)

        Args:
            add_list: 추가된 종목 리스트
            remove_list: 제거된 종목 리스트
        """
        if add_list:
            self.pending_deltas["add"].extend(add_list)
        if remove_list:
            self.pending_deltas["remove"].extend(remove_list)
        logger.debug("ScannerStream: Queued delta add=%d remove=%d", len(add_list), len(remove_list))

    async def flush_deltas(self):
        """
        delta 전송 (200~500ms 주기)

        pending_deltas를 모아서 한 번에 전송
        """
        current_time = time.time() * 1000

        # 플러시 간격 체크
        if current_time - self.last_flush < self.flush_interval_ms:
            return

        # 전송할 delta 없으면 스킵
        if not self.pending_deltas["add"] and not self.pending_deltas["remove"]:
            return

        message = {
            "type": "scanner.delta",
            "ts": int(current_time),
            "add": list(self.pending_deltas["add"]),
            "remove": list(self.pending_deltas["remove"]),
        }

        # 모든 연결에 전송
        disconnected = []

        for ws in list(self.connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug("ScannerStream: Send error to client: %s", e, exc_info=True)
                disconnected.append(ws)

        # 연결 끊긴 클라이언트 제거
        for ws in disconnected:
            self.disconnect(ws)

        # 큐 초기화
        add_count = len(self.pending_deltas["add"])
        remove_count = len(self.pending_deltas["remove"])
        self.pending_deltas = {"add": [], "remove": []}
        self.last_flush = current_time

        logger.info("ScannerStream: Flushed delta: add=%d, remove=%d", add_count, remove_count)

    async def send_full_results(self, websocket: WebSocket, results: List[dict]):
        """
        전체 스캔 결과 전송 (초기 연결 시)

        Args:
            websocket: FastAPI WebSocket 인스턴스
            results: 전체 스캔 결과
        """
        try:
            message = {"type": "scanner.full", "ts": int(time.time() * 1000), "results": results}
            await websocket.send_json(message)
            logger.debug("ScannerStream: Sent full results: %d items", len(results))
        except Exception as e:
            logger.debug("ScannerStream: Full results send error: %s", e, exc_info=True)

    async def broadcast_message(self, message: dict):
        """
        일반 메시지 브로드캐스트

        Args:
            message: 전송할 메시지
        """
        disconnected = []

        for ws in list(self.connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug("ScannerStream: Broadcast error: %s", e, exc_info=True)
                disconnected.append(ws)

        # 연결 끊긴 클라이언트 제거
        for ws in disconnected:
            self.disconnect(ws)

    def get_connection_count(self) -> int:
        """연결 수 조회"""
        return len(self.connections)

    def has_pending_deltas(self) -> bool:
        """대기 중인 delta 존재 여부"""
        return bool(self.pending_deltas["add"] or self.pending_deltas["remove"])