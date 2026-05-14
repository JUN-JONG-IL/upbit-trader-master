# -*- coding: utf-8 -*-
"""
WebSocketPool ???ㅼ쨷 WebSocket ? (Phase 3)

[梨낆엫]
    Upbit WebSocket 梨꾨꼸??N 媛??ㅻ뱶濡??섎늻???낅┰ connection ?쇰줈 ?댁쁺?쒕떎.
    媛??ㅻ뱶??蹂꾨룄 肄붾（?댁뿉??硫붿떆吏瑜??섏떊?섍퀬, ?⑥씪 ``asyncio.Queue`` ??
    諛깊봽?덉뀛 ?뺤콉(``drop-oldest``) ?쇰줈 ?몄떆?섎?濡??ㅼ슫?ㅽ듃由?吏???쒖뿉??
    ?대깽??猷⑦봽媛 留됲엳吏 ?딅뒗??

    REST ?쒕룄? 臾닿???梨꾨꼸?대?濡?``AsyncRateLimiter`` 瑜?嫄곗튂吏 ?딅뒗??

[?ㅺ퀎]
    - ``shards``: ?щ낵 由ъ뒪?몃? 洹좊벑 遺꾪븷(round-robin), 湲곕낯 4 ?ㅻ뱶.
    - 媛??ㅻ뱶??``WebSocketManager`` 瑜?洹몃?濡??쒖슜???곌껐/援щ룆?쒕떎(湲곗〈 肄붾뱶
      ?ъ궗?⑹쑝濡??뚭? ?꾪뿕 理쒖냼??.
    - ``out_queue: asyncio.Queue(maxsize=N)`` ??媛??李⑤㈃ 媛???ㅻ옒??硫붿떆吏瑜?
      drop ????硫붿떆吏 push (``drop-oldest``).
    - Linux ?쒖젙?쇰줈 ``uvloop`` 媛 ?ㅼ튂?섏뼱 ?덈떎硫??먮룞 ?ъ슜. Windows/湲고???
      湲곕낯 ``asyncio`` ?뺤콉 洹몃?濡?

[鍮꾪뙆愿?蹂댁옣]
    - 湲곗〈 ``websocket_manager.py`` 蹂寃??놁쓬.
    - 蹂?紐⑤뱢? 紐낆떆?곸쑝濡?import ?섏뼱?쇰쭔 ?숈옉?쒕떎.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def maybe_install_uvloop() -> bool:
    """Linux ?섍꼍?먯꽌 uvloop 媛 ?ㅼ튂?섏뼱 ?덈떎硫??쒖꽦?? ?깃났 ??True."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        import uvloop  # type: ignore

        # ?대? ?뺤콉??uvloop ??寃쎌슦??嫄대꼫?
        current = asyncio.get_event_loop_policy()
        if isinstance(current, uvloop.EventLoopPolicy):
            return True
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("[WebSocketPool] uvloop ?쒖꽦??)
        return True
    except Exception:
        return False


class _BoundedQueue:
    """``asyncio.Queue`` ??'drop-oldest' 蹂??

    ?대??곸쑝濡?``deque(maxlen=...)`` 瑜??ъ슜?섎㈃ ?먯돺寃?drop-oldest 瑜?援ы쁽????
    ?덉?留? 鍮꾨룞湲?wait ?듭?瑜??꾪빐 蹂꾨룄 ``asyncio.Event`` ? ``Lock`` ?쇰줈 ?숆린?뷀븳??
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
    """?ㅼ쨷 ?ㅻ뱶 WebSocket ?.

    Args:
        symbols: 援щ룆???щ낵 紐⑸줉
        shards: ? ?ш린 (湲곕낯 4). ?щ낵 ?섎낫??留롮쑝硫??먮룞?쇰줈 ``len(symbols)`` 濡??대옩??
        timeframes: ??꾪봽?덉엫 紐⑸줉 (媛??ㅻ뱶??``WebSocketManager`` ???꾨떖)
        ws_manager_factory: ?뚯뒪??二쇱엯???꾪븳 ?⑺넗由??몄옄 ?놁쓬, ``WebSocketManager`` ?몄뒪?댁뒪 諛섑솚).
            湲곕낯? ``websocket_manager.WebSocketManager`` 瑜??숈쟻 import.
        queue_maxsize: ?ㅼ슫?ㅽ듃由???理쒕? ?ш린 (drop-oldest ?곸슜)
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
            raise ValueError("symbols 媛 鍮꾩뼱 ?덉뒿?덈떎")
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
        # ?숈쟻 import (?뚯뒪???섍꼍?먯꽌 PyQt/redis 誘몄꽕移??뚰뵾)
        from importlib import import_module

        mod = import_module("src.data_01.collectors.websocket_manager")  # noqa: E402
        return mod.WebSocketManager()

    # ------------------------------------------------------------------
    def shard_layout(self) -> List[List[str]]:
        """?꾩옱 ?ㅻ뱶蹂??щ낵 遺꾪룷瑜?諛섑솚 (?붾쾭洹몄슜)."""
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
                logger.error("[WebSocketPool] ?ㅻ뱶 %d 留ㅻ땲? ?앹꽦 ?ㅽ뙣: %s", idx, exc)
                continue
            self._managers.append(mgr)

            # 肄쒕갚???듯빐 ?ㅼ슫?ㅽ듃由??먮줈 ?쇱슦??
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
                logger.debug("[WebSocketPool] set_pipeline_callback ?ㅽ뙣: %s", exc)

            # 鍮꾨룞湲?start ?몄텧 (??낆뿉 ?곕씪 ?몄옄 ?ㅻ? ???덉뼱 try-fallback)
            task = asyncio.create_task(
                self._start_shard(mgr, shard_symbols),
                name=f"ws-pool-shard-{idx}",
            )
            self._tasks.append(task)

        logger.info(
            "[WebSocketPool] ?쒖옉: ?ㅻ뱶=%d, ?щ낵=%d, TFs=%s",
            len(self._shards), sum(len(s) for s in self._shards), self._timeframes,
        )

    async def _start_shard(self, mgr: Any, symbols: List[str]) -> None:
        try:
            if hasattr(mgr, "start"):
                # ?쇰컲???쒓렇?덉쿂 異붿젙: start(symbols, timeframes)
                try:
                    res = mgr.start(symbols, self._timeframes)  # type: ignore[misc]
                except TypeError:
                    res = mgr.start(symbols)  # type: ignore[misc]
                if asyncio.iscoroutine(res):
                    await res
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[WebSocketPool] ?ㅻ뱶 ?쒖옉 ?ㅽ뙣: %s", exc)

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
                logger.debug("[WebSocketPool] 留ㅻ땲? stop ?ㅽ뙣: %s", exc)
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
        logger.info("[WebSocketPool] ?뺤?")


__all__ = ["WebSocketPool", "maybe_install_uvloop"]

