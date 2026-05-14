# -*- coding: utf-8 -*-
"""
WebSocket 제어 컨트롤러

[책임]
- WebSocket 수동 시작 버튼 처리
- RealtimeManager 연동 (utils.get_realtime_manager())
- 우선순위 심볼 조회 (MongoDB → 하드코딩 폴백)
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[WebSocketController] PyQt5 없음 — 더미 클래스 사용")


# 하드코딩 폴백 심볼 목록 (MongoDB/API 모두 실패 시 사용)
_FALLBACK_SYMBOLS = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA", "KRW-DOGE",
    "KRW-SOL", "KRW-MATIC", "KRW-AVAX", "KRW-DOT", "KRW-LINK",
]


if _HAS_QT:
    class WebSocketController(QObject):
        """
        WebSocket 시작/중지 제어 컨트롤러

        - RealtimeManager 인스턴스를 utils 모듈에서 조회
        - MongoDB에서 우선순위 심볼 조회, 실패 시 하드코딩 폴백
        - websocket_started 시그널로 시작 결과 전달
        """

        # 시그널: (시작된 수, 전체 시도 수)
        websocket_started = pyqtSignal(int, int)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)

        # ------------------------------------------------------------------
        # 공개 메서드
        # ------------------------------------------------------------------

        def start_websockets(self, limit: int = 20) -> None:
            """우선순위 심볼에 대해 WebSocket을 시작합니다.

            Args:
                limit: 시작할 최대 심볼 수 (기본값: 20)
            """
            try:
                from ..utils import get_realtime_manager  # type: ignore
                mgr = get_realtime_manager()
                if mgr is None:
                    logger.warning("[WebSocketController] RealtimeManager 없음 — WebSocket 시작 불가")
                    return

                symbols = self._get_priority_symbols(limit)
                if not symbols:
                    logger.warning("[WebSocketController] 심볼 목록 비어있음 — WebSocket 시작 스킵")
                    return

                total = len(symbols)

                # 이벤트 루프 상태에 따라 실행 방식 결정
                async def _start() -> int:
                    started = 0
                    coros = [mgr.start_websocket(sym) for sym in symbols]
                    results = await asyncio.gather(*coros, return_exceptions=True)
                    for sym, result in zip(symbols, results):
                        if isinstance(result, Exception):
                            logger.debug(
                                "[WebSocketController] WebSocket 시작 실패 (%s): %s", sym, result
                            )
                        else:
                            started += 1
                            logger.info("[WebSocketController] ✅ WebSocket 시작: %s", sym)
                    return started

                def _on_done(future) -> None:
                    """비동기 태스크 완료 콜백 — 이벤트 루프 실행 중일 때 사용"""
                    exc = future.exception()
                    if exc:
                        logger.exception("[WebSocketController] WebSocket 태스크 실패: %s", exc)
                        return
                    started = future.result()
                    self.websocket_started.emit(started, total)
                    logger.info(
                        "[WebSocketController] ✅ WebSocket 자동 시작 완료 (%d/%d 심볼)",
                        started, total,
                    )

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 이미 실행 중인 루프에 태스크 추가하고 완료 콜백 등록
                        task = asyncio.ensure_future(_start())
                        task.add_done_callback(_on_done)
                        logger.info("[WebSocketController] WebSocket 시작 태스크 예약됨")
                        return
                    else:
                        started = loop.run_until_complete(_start())
                except RuntimeError:
                    started = asyncio.run(_start())

                self.websocket_started.emit(started, total)
                logger.info(
                    "[WebSocketController] ✅ WebSocket 자동 시작 완료 (%d/%d 심볼)",
                    started, total,
                )
            except Exception as exc:
                logger.exception("[WebSocketController] WebSocket 시작 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 헬퍼
        # ------------------------------------------------------------------

        def _get_priority_symbols(self, limit: int = 20) -> List[str]:
            """우선순위 심볼 목록을 반환합니다.

            조회 순서:
            1. MongoDB ``metadata`` 컬렉션
            2. 하드코딩 폴백

            Args:
                limit: 최대 반환 개수

            Returns:
                ["KRW-BTC", "KRW-ETH", ...] (최대 limit개)
            """
            symbols: List[str] = []

            # 1순위: MongoDB 조회
            try:
                from ..utils import get_mongo_sync_client  # type: ignore
                db = get_mongo_sync_client()
                if db is not None:
                    coll = db["metadata"]
                    docs = list(coll.find({}, {"market": 1}).limit(limit))
                    symbols = [
                        doc.get("market")
                        for doc in docs
                        if doc.get("market")
                    ]
                    if symbols:
                        logger.debug(
                            "[WebSocketController] MongoDB에서 심볼 %d개 조회 완료", len(symbols)
                        )
                        return symbols[:limit]
            except Exception as exc:
                logger.debug("[WebSocketController] MongoDB 심볼 조회 실패 (폴백 사용): %s", exc)

            # 2순위: 하드코딩 폴백
            logger.warning(
                "[WebSocketController] 심볼 조회 실패 — 하드코딩 폴백 사용 (%d개)",
                len(_FALLBACK_SYMBOLS),
            )
            return _FALLBACK_SYMBOLS[:limit]

else:
    class WebSocketController:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None) -> None:
            logger.warning("[WebSocketController] PyQt5 미설치 — 더미 인스턴스 생성")

        def start_websockets(self, limit: int = 20) -> None:
            """더미 메서드 (아무 동작도 하지 않음)"""
