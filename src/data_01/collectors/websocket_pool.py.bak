# -*- coding: utf-8 -*-
"""
WebSocketPool — 다중 WebSocket 풀 (Phase 3)

[책임]
    Upbit WebSocket 채널을 N 개 샤드로 나누어 독립 connection 으로 운영한다.
    각 샤드는 별도 코루틴에서 메시지를 수신하고, 단일 ``asyncio.Queue`` 에
    백프레셔 정책(``drop-oldest``) 으로 푸시하므로 다운스트림 지연 시에도
    이벤트 루프가 막히지 않는다.

    REST 한도와 무관한 채널이므로 ``AsyncRateLimiter`` 를 거치지 않는다.

[설계]
    - ``shards``: 심볼 리스트를 균등 분할(round-robin), 기본 4 샤드.
    - 각 샤드는 ``WebSocketManager`` 를 그대로 활용해 연결/구독한다(기존 코드
      재사용으로 회귀 위험 최소화).
    - ``out_queue: asyncio.Queue(maxsize=N)`` — 가득 차면 가장 오래된 메시지를
      drop 후 새 메시지 push (``drop-oldest``).
    - Linux 한정으로 ``uvloop`` 가 설치되어 있다면 자동 사용. Windows/기타는
      기본 ``asyncio`` 정책 그대로.

[비파괴 보장]
    - 기존 ``websocket_manager.py`` 변경 없음.
    - 본 모듈은 명시적으로 import 되어야만 동작한다.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def maybe_install_uvloop() -> bool:
    """Linux 환경에서 uvloop 가 설치되어 있다면 활성화. 성공 시 True."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        import uvloop  # type: ignore

        # 이미 정책이 uvloop 인 경우는 건너뜀
        current = asyncio.get_event_loop_policy()
        if isinstance(current, uvloop.EventLoopPolicy):
            return True
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("[WebSocketPool] uvloop 활성화")
        return True
    except Exception:
        return False


class _BoundedQueue:
    """``asyncio.Queue`` 의 'drop-oldest' 변형.

    내부적으로 ``deque(maxlen=...)`` 를 사용하면 손쉽게 drop-oldest 를 구현할 수
    있지만, 비동기 wait 통지를 위해 별도 ``asyncio.Event`` 와 ``Lock`` 으로 동기화한다.
    """

    def __init__(self, maxsize: int = 10000) -> None:
        from collections import deque

        self._buf: "deque[Any]" = deque(maxlen=max(1, int(maxsize)))
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        self.dropped = 0

    async def put(self, item: Any) -> None:
        async with self._lock:
            if len(self._buf) >= self._buf.maxlen:  # type: ignore[arg-type]
                # drop-oldest
                self._buf.popleft()
                self.dropped += 1
            self._buf.append(item)
            self._not_empty.set()

    async def get(self) -> Any:
        while True:
            async with self._lock:
                if self._buf:
                    item = self._buf.popleft()
                    if not self._buf:
                        self._not_empty.clear()
                    return item
            await self._not_empty.wait()

    def qsize(self) -> int:
        return len(self._buf)


class WebSocketPool:
    """다중 샤드 WebSocket 풀.

    Args:
        symbols: 구독할 심볼 목록
        shards: 풀 크기 (기본 4). 심볼 수보다 많으면 자동으로 ``len(symbols)`` 로 클램프
        timeframes: 타임프레임 목록 (각 샤드의 ``WebSocketManager`` 에 전달)
        ws_manager_factory: 테스트 주입을 위한 팩토리(인자 없음, ``WebSocketManager`` 인스턴스 반환).
            기본은 ``websocket_manager.WebSocketManager`` 를 동적 import.
        queue_maxsize: 다운스트림 큐 최대 크기 (drop-oldest 적용)
    """

    def __init__(
        self,
        symbols: List[str],
        shards: int = 4,
        timeframes: Optional[List[str]] = None,
        ws_manager_factory: Optional[Callable[[], Any]] = None,
        queue_maxsize: int = 10000,
    ) -> None:
        symbols = [s for s in (symbols or []) if isinstance(s, str) and s]
        if not symbols:
            raise ValueError("symbols 가 비어 있습니다")
        n = max(1, min(int(shards or 1), len(symbols)))
        self._shards: List[List[str]] = [[] for _ in range(n)]
        for i, sym in enumerate(symbols):
            self._shards[i % n].append(sym)
        self._timeframes = list(timeframes or ["1m"])
        self._factory = ws_manager_factory or self._default_factory
        self._managers: List[Any] = []
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self.out_queue = _BoundedQueue(maxsize=queue_maxsize)
        self._stats = {
            "messages_received": 0,
            "messages_dropped": 0,
            "shard_count": n,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _default_factory() -> Any:
        # 동적 import (테스트 환경에서 PyQt/redis 미설치 회피)
        from importlib import import_module

        mod = import_module("src.02_data.collectors.websocket_manager")  # noqa: E402
        return mod.WebSocketManager()

    # ------------------------------------------------------------------
    def shard_layout(self) -> List[List[str]]:
        """현재 샤드별 심볼 분포를 반환 (디버그용)."""
        return [list(s) for s in self._shards]

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "messages_dropped": self.out_queue.dropped,
            "queue_size": self.out_queue.qsize(),
        }

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for idx, shard_symbols in enumerate(self._shards):
            try:
                mgr = self._factory()
            except Exception as exc:
                logger.error("[WebSocketPool] 샤드 %d 매니저 생성 실패: %s", idx, exc)
                continue
            self._managers.append(mgr)

            # 콜백을 통해 다운스트림 큐로 라우팅
            def _make_cb(shard_idx: int = idx):
                async def _cb(msg: Dict[str, Any]) -> None:
                    self._stats["messages_received"] += 1
                    msg_with_meta = dict(msg) if isinstance(msg, dict) else {"raw": msg}
                    msg_with_meta["__shard__"] = shard_idx
                    await self.out_queue.put(msg_with_meta)

                return _cb

            try:
                if hasattr(mgr, "set_pipeline_callback"):
                    mgr.set_pipeline_callback(_make_cb())
            except Exception as exc:
                logger.debug("[WebSocketPool] set_pipeline_callback 실패: %s", exc)

            # 비동기 start 호출 (타입에 따라 인자 다를 수 있어 try-fallback)
            task = asyncio.create_task(
                self._start_shard(mgr, shard_symbols),
                name=f"ws-pool-shard-{idx}",
            )
            self._tasks.append(task)

        logger.info(
            "[WebSocketPool] 시작: 샤드=%d, 심볼=%d, TFs=%s",
            len(self._shards), sum(len(s) for s in self._shards), self._timeframes,
        )

    async def _start_shard(self, mgr: Any, symbols: List[str]) -> None:
        try:
            if hasattr(mgr, "start"):
                # 일반적 시그니처 추정: start(symbols, timeframes)
                try:
                    res = mgr.start(symbols, self._timeframes)  # type: ignore[misc]
                except TypeError:
                    res = mgr.start(symbols)  # type: ignore[misc]
                if asyncio.iscoroutine(res):
                    await res
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[WebSocketPool] 샤드 시작 실패: %s", exc)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for mgr in self._managers:
            try:
                if hasattr(mgr, "stop"):
                    res = mgr.stop()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as exc:
                logger.debug("[WebSocketPool] 매니저 stop 실패: %s", exc)
        for t in self._tasks:
            if not t.done():
                t.cancel()
        for t in self._tasks:
            try:
                await asyncio.wait_for(t, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        self._managers.clear()
        logger.info("[WebSocketPool] 정지")


__all__ = ["WebSocketPool", "maybe_install_uvloop"]
