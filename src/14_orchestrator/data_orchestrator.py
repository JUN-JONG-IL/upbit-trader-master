# -*- coding: utf-8 -*-
"""
DataOrchestrator ??諛깊븘/?ㅼ떆媛?蹂묐젹 ?섏쭛 ?ㅼ??ㅽ듃?덉씠??(Phase 2)

[梨낆엫]
    REST 湲곕컲 ?곗씠???섏쭛 ?묒뾽(怨쇨굅 諛깊븘 / ?꾩옱 polling)???⑥씪 ?곗꽑?쒖쐞 ?먮줈
    ?듯빀?섍퀬, ``async_rate_limiter.AsyncRateLimiter`` 湲濡쒕쾶 ?좏겙踰꾪궥???듯빐
    Upbit ?쒕룄(REST 珥덈떦 10??/ 遺꾨떦 600??瑜??덈? ?섏? ?딅룄濡?吏곷젹?뷀븳??
    WebSocket ?ㅼ떆媛?梨꾨꼸? REST ?쒕룄? 臾닿??섎?濡?蹂??ㅼ??ㅽ듃?덉씠?곗쓽 ?곹뼢??
    諛쏆? ?딆쑝硫? 蹂꾨룄 ?(``websocket_pool``)?먯꽌 ?媛?숇맂??

[?ㅺ퀎 硫붾え]
    - ???곗꽑?쒖쐞: ``historical_high`` > ``historical_normal`` > ``realtime_polling``.
    - ?좏겙 諛곕텇: ?곗꽑?쒖쐞??鍮꾨? (high:normal:realtime = 5:3:2). 留??ъ씠?대쭏??
      ``per_second`` ?좏겙??鍮꾩쑉?濡??섎닠 媛???꾩뿉 ?덈뒗 ?묒뾽遺??泥섎━.
    - ?뚯빱???⑥씪 鍮꾨룞湲??쒖뒪?щ줈 ?숈옉(吏곷젹 ?ㅽ뻾). 媛??묒뾽 ?쒖옉 ??
      ``await limiter.acquire()`` 濡?湲濡쒕쾶 ?쒕룄 以??
    - 蹂?紐⑤뱢? **?낅┰ 異붽? 紐⑤뱢**?대ŉ 湲곗〈 RestCandleCollector / AutoBackfill
      ?먮쫫???먮룞?쇰줈 hooking ?섏? ?딅뒗?????몄텧 痢≪씠 紐낆떆?곸쑝濡?enqueue ?쒕떎.
      ?대줈???뚭? ?꾪뿕??0???섎졃?쒗궓??

[?ъ슜 ??
    >>> orch = DataOrchestrator()
    >>> await orch.start()
    >>> orch.enqueue_historical(symbol="KRW-BTC", timeframe="1m",
    ...                          start=t0, end=t1, priority="high",
    ...                          executor=fetch_func)
    >>> orch.enqueue_realtime(symbol="KRW-BTC", timeframe="1m",
    ...                       executor=poll_func)
    >>> await orch.stop()
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 湲濡쒕쾶 limiter 濡쒕뱶 (吏???덉쟾)
# ---------------------------------------------------------------------------


def _load_global_limiter():
    try:
        base = pathlib.Path(__file__).resolve().parents[1]
        path = base / "data_01" / "collectors" / "async_rate_limiter.py"
        if not path.exists():
            return None
        mod = sys.modules.get("_async_rate_limiter")
        if mod is None:
            spec = importlib.util.spec_from_file_location("_async_rate_limiter", str(path))
            if not spec or not spec.loader:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules["_async_rate_limiter"] = mod
            spec.loader.exec_module(mod)
        getter = getattr(mod, "get_global_upbit_rate_limiter", None)
        return getter() if callable(getter) else None
    except Exception as exc:  # pragma: no cover
        logger.debug("[DataOrchestrator] limiter 濡쒕뱶 ?ㅽ뙣: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Job ?뺤쓽
# ---------------------------------------------------------------------------

PRIORITY_HISTORICAL_HIGH = "historical_high"
PRIORITY_HISTORICAL_NORMAL = "historical_normal"
PRIORITY_REALTIME_POLLING = "realtime_polling"

_PRIORITY_RANK = {
    PRIORITY_HISTORICAL_HIGH: 0,
    PRIORITY_HISTORICAL_NORMAL: 1,
    PRIORITY_REALTIME_POLLING: 2,
}

# ?좏겙 諛곕텇 鍮꾩쑉 (遺꾩옄 ?⑷퀎媛 ?좏겙 1珥덈떦 遺꾨같 ?섏튂)
_TOKEN_RATIOS = {
    PRIORITY_HISTORICAL_HIGH: 5,
    PRIORITY_HISTORICAL_NORMAL: 3,
    PRIORITY_REALTIME_POLLING: 2,
}


@dataclass(order=False)
class FetchJob:
    """?⑥씪 REST ?몄텧 ?묒뾽 ?⑥쐞.

    ``executor`` ???몄옄 ?놁씠 ?몄텧 媛?ν븳 肄붾（???⑥닔?ъ빞 ?쒕떎. ?묒뾽??寃곌낵??
    ``future`` 濡??꾨떖?섎ŉ ?몄텧?먭? await ?????덈떎.
    """

    priority: str
    symbol: str
    timeframe: str
    executor: Callable[[], Awaitable[Any]]
    enqueued_at: float = field(default_factory=time.monotonic)
    future: asyncio.Future = field(default=None)  # type: ignore[assignment]

    def rank(self) -> int:
        return _PRIORITY_RANK.get(self.priority, 99)


# ---------------------------------------------------------------------------
# DataOrchestrator
# ---------------------------------------------------------------------------


class DataOrchestrator:
    """?곗꽑?쒖쐞 湲곕컲 鍮꾨룞湲?REST ?묒뾽 ?ㅼ??ㅽ듃?덉씠??

    ?⑥씪 ?뚯빱 + ?곗꽑?쒖쐞 ??deque횞3) 援ъ“. 湲濡쒕쾶 ``AsyncRateLimiter`` ?
    怨듭쑀?섎?濡?``RestCandleCollector`` / ``AutoBackfillManager`` 媛 吏곸젒 ?몄텧
    ?섎뒗 耳?댁뒪????쒕룄媛 ?⑹궛?섏뼱 ?덉쟾?섎떎.
    """

    def __init__(self, limiter: Any = None) -> None:
        self._limiter = limiter or _load_global_limiter()
        self._queues: Dict[str, Deque[FetchJob]] = {
            PRIORITY_HISTORICAL_HIGH: deque(),
            PRIORITY_HISTORICAL_NORMAL: deque(),
            PRIORITY_REALTIME_POLLING: deque(),
        }
        self._cv: Optional[asyncio.Condition] = None
        self._worker: Optional[asyncio.Task] = None
        self._running: bool = False
        self._stats: Dict[str, int] = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "rate_limited": 0,
        }
        # ?곗꽑?쒖쐞蹂??꾩쟻 泥섎━ 移댁슫????鍮꾩쑉 湲곕컲 ?쇱슫?쒕줈鍮?蹂댁젙???ъ슜
        self._served: Dict[str, int] = {p: 0 for p in _PRIORITY_RANK}

    # ------------------------------------------------------------------
    # ?쇱씠?꾩궗?댄겢
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """?뚯빱 ?쒖뒪???쒖옉. ?대? ?ㅽ뻾 以묒씠硫?臾댁떆."""
        if self._running:
            return
        self._cv = asyncio.Condition()
        self._running = True
        self._worker = asyncio.create_task(self._run(), name="data-orchestrator")
        logger.info("[DataOrchestrator] ?쒖옉")

    async def stop(self) -> None:
        """?뚯빱 ?뺤? 諛??湲?以??묒뾽 痍⑥냼."""
        if not self._running:
            return
        self._running = False
        # ?湲?以묒씤 ?뚯빱 源⑥슦湲?
        if self._cv is not None:
            async with self._cv:
                self._cv.notify_all()
        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._worker.cancel()
            finally:
                self._worker = None
        # 誘몄쿂由?future 痍⑥냼
        for q in self._queues.values():
            while q:
                job = q.popleft()
                if job.future is not None and not job.future.done():
                    job.future.cancel()
        logger.info("[DataOrchestrator] ?뺤?")

    # ------------------------------------------------------------------
    # Enqueue API
    # ------------------------------------------------------------------

    def enqueue_historical(
        self,
        *,
        symbol: str,
        timeframe: str,
        executor: Callable[[], Awaitable[Any]],
        priority: str = "normal",
    ) -> asyncio.Future:
        """怨쇨굅 諛깊븘 ?묒뾽 ?깅줉. ``priority`` ??{"high", "normal"}."""
        pri = (
            PRIORITY_HISTORICAL_HIGH
            if str(priority).lower() == "high"
            else PRIORITY_HISTORICAL_NORMAL
        )
        return self._enqueue(pri, symbol, timeframe, executor)

    def enqueue_realtime(
        self,
        *,
        symbol: str,
        timeframe: str,
        executor: Callable[[], Awaitable[Any]],
    ) -> asyncio.Future:
        """?꾩옱(?대쭅) 1罹붾뱾 ?섏쭛 ?묒뾽 ?깅줉."""
        return self._enqueue(PRIORITY_REALTIME_POLLING, symbol, timeframe, executor)

    def _enqueue(
        self,
        priority: str,
        symbol: str,
        timeframe: str,
        executor: Callable[[], Awaitable[Any]],
    ) -> asyncio.Future:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        job = FetchJob(
            priority=priority,
            symbol=symbol,
            timeframe=timeframe,
            executor=executor,
            future=fut,
        )
        self._queues[priority].append(job)
        self._stats["submitted"] += 1
        # ?뚯빱 源⑥슦湲?
        if self._cv is not None:
            async def _notify() -> None:
                async with self._cv:  # type: ignore[arg-type]
                    self._cv.notify()  # type: ignore[union-attr]
            try:
                asyncio.ensure_future(_notify())
            except Exception:
                pass
        return fut

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        try:
            while self._running:
                job = self._select_next_job()
                if job is None:
                    if self._cv is not None:
                        async with self._cv:
                            try:
                                await asyncio.wait_for(self._cv.wait(), timeout=0.5)
                            except asyncio.TimeoutError:
                                pass
                    continue

                if self._limiter is not None:
                    try:
                        await self._limiter.acquire()
                    except Exception as exc:  # pragma: no cover
                        logger.debug("[DataOrchestrator] limiter.acquire ?ㅽ뙣: %s", exc)

                try:
                    result = await job.executor()
                    if job.future is not None and not job.future.done():
                        job.future.set_result(result)
                    self._stats["completed"] += 1
                    self._served[job.priority] += 1
                except Exception as exc:
                    msg = str(exc).lower()
                    if "?붿껌 ???쒗븳" in msg or "rate limit" in msg or "429" in msg:
                        self._stats["rate_limited"] += 1
                    self._stats["failed"] += 1
                    if job.future is not None and not job.future.done():
                        job.future.set_exception(exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover
            logger.error("[DataOrchestrator] ?뚯빱 ?덉쇅: %s", exc)

    def _select_next_job(self) -> Optional[FetchJob]:
        """?곗꽑?쒖쐞 + 鍮꾩쑉 蹂댁젙?쇰줈 ?ㅼ쓬 ?묒뾽 ?좏깮.

        蹂댁젙 洹쒖튃: ???믪? ?곗꽑?쒖쐞 ?먭? 鍮꾩뼱?덉? ?딆쑝硫?洹몄そ????긽 ?곗꽑?댁?留?
        ?대떦 ?먭? ?먭린 鍮꾩쑉(`_TOKEN_RATIOS[p]`) 留뚰겮 ?곗냽 泥섎━???ㅼ뿉????踰?
        ?섏쐞 ?곗꽑?쒖쐞???묐낫?섏뿬 starvation ??諛⑹??쒕떎.
        """
        # 媛???믪? 鍮꾩뼱?덉? ?딆? ???먯깋
        for p in (PRIORITY_HISTORICAL_HIGH, PRIORITY_HISTORICAL_NORMAL, PRIORITY_REALTIME_POLLING):
            q = self._queues[p]
            if not q:
                continue
            # starvation 蹂댄샇: ?곗냽 泥섎━?됱씠 鍮꾩쑉??珥덇낵?덇퀬 ?섏쐞 ?먯뿉 ?쇱씠 ?덉쑝硫??묐낫
            served_now = self._served[p]
            ratio = _TOKEN_RATIOS[p]
            lower_has_job = any(
                self._queues[lp]
                for lp in (PRIORITY_HISTORICAL_HIGH, PRIORITY_HISTORICAL_NORMAL, PRIORITY_REALTIME_POLLING)
                if _PRIORITY_RANK[lp] > _PRIORITY_RANK[p]
            )
            if served_now > 0 and served_now % (ratio + 1) == 0 and lower_has_job:
                # ??踰??묐낫: ?ㅼ쓬 鍮꾩뼱?덉? ?딆? ?섏쐞 ?먯뿉???좏깮
                continue
            return q.popleft()
        return None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        snap: Dict[str, Any] = dict(self._stats)
        snap["queue_sizes"] = {p: len(q) for p, q in self._queues.items()}
        snap["served_by_priority"] = dict(self._served)
        if self._limiter is not None and hasattr(self._limiter, "snapshot"):
            try:
                snap["rate_limiter"] = self._limiter.snapshot()
            except Exception:
                pass
        return snap


# ---------------------------------------------------------------------------
# 湲濡쒕쾶 ?깃???(?좏깮???ъ슜)
# ---------------------------------------------------------------------------

_global_orchestrator: Optional[DataOrchestrator] = None


def get_global_orchestrator() -> DataOrchestrator:
    """?꾨줈?몄뒪 ?꾩뿭 ?⑥씪 ?ㅼ??ㅽ듃?덉씠???몄뒪?댁뒪 諛섑솚."""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = DataOrchestrator()
    return _global_orchestrator


__all__ = [
    "DataOrchestrator",
    "FetchJob",
    "PRIORITY_HISTORICAL_HIGH",
    "PRIORITY_HISTORICAL_NORMAL",
    "PRIORITY_REALTIME_POLLING",
    "get_global_orchestrator",
]

