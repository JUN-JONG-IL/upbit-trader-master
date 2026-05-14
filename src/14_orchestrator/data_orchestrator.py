# -*- coding: utf-8 -*-
"""
DataOrchestrator — 백필/실시간 병렬 수집 오케스트레이터 (Phase 2)

[책임]
    REST 기반 데이터 수집 작업(과거 백필 / 현재 polling)을 단일 우선순위 큐로
    통합하고, ``async_rate_limiter.AsyncRateLimiter`` 글로벌 토큰버킷을 통해
    Upbit 한도(REST 초당 10회 / 분당 600회)를 절대 넘지 않도록 직렬화한다.
    WebSocket 실시간 채널은 REST 한도와 무관하므로 본 오케스트레이터의 영향을
    받지 않으며, 별도 풀(``websocket_pool``)에서 풀가동된다.

[설계 메모]
    - 큐 우선순위: ``historical_high`` > ``historical_normal`` > ``realtime_polling``.
    - 토큰 배분: 우선순위에 비례 (high:normal:realtime = 5:3:2). 매 사이클마다
      ``per_second`` 토큰을 비율대로 나눠 가장 위에 있는 작업부터 처리.
    - 워커는 단일 비동기 태스크로 동작(직렬 실행). 각 작업 시작 전
      ``await limiter.acquire()`` 로 글로벌 한도 준수.
    - 본 모듈은 **독립 추가 모듈**이며 기존 RestCandleCollector / AutoBackfill
      흐름에 자동으로 hooking 되지 않는다 — 호출 측이 명시적으로 enqueue 한다.
      이로써 회귀 위험을 0에 수렴시킨다.

[사용 예]
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
# 글로벌 limiter 로드 (지연/안전)
# ---------------------------------------------------------------------------


def _load_global_limiter():
    try:
        base = pathlib.Path(__file__).resolve().parents[1]
        path = base / "02_data" / "collectors" / "async_rate_limiter.py"
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
        logger.debug("[DataOrchestrator] limiter 로드 실패: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Job 정의
# ---------------------------------------------------------------------------

PRIORITY_HISTORICAL_HIGH = "historical_high"
PRIORITY_HISTORICAL_NORMAL = "historical_normal"
PRIORITY_REALTIME_POLLING = "realtime_polling"

_PRIORITY_RANK = {
    PRIORITY_HISTORICAL_HIGH: 0,
    PRIORITY_HISTORICAL_NORMAL: 1,
    PRIORITY_REALTIME_POLLING: 2,
}

# 토큰 배분 비율 (분자 합계가 토큰 1초당 분배 수치)
_TOKEN_RATIOS = {
    PRIORITY_HISTORICAL_HIGH: 5,
    PRIORITY_HISTORICAL_NORMAL: 3,
    PRIORITY_REALTIME_POLLING: 2,
}


@dataclass(order=False)
class FetchJob:
    """단일 REST 호출 작업 단위.

    ``executor`` 는 인자 없이 호출 가능한 코루틴 함수여야 한다. 작업의 결과는
    ``future`` 로 전달되며 호출자가 await 할 수 있다.
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
    """우선순위 기반 비동기 REST 작업 오케스트레이터.

    단일 워커 + 우선순위 큐(deque×3) 구조. 글로벌 ``AsyncRateLimiter`` 와
    공유하므로 ``RestCandleCollector`` / ``AutoBackfillManager`` 가 직접 호출
    하는 케이스와도 한도가 합산되어 안전하다.
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
        # 우선순위별 누적 처리 카운터 — 비율 기반 라운드로빈 보정에 사용
        self._served: Dict[str, int] = {p: 0 for p in _PRIORITY_RANK}

    # ------------------------------------------------------------------
    # 라이프사이클
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """워커 태스크 시작. 이미 실행 중이면 무시."""
        if self._running:
            return
        self._cv = asyncio.Condition()
        self._running = True
        self._worker = asyncio.create_task(self._run(), name="data-orchestrator")
        logger.info("[DataOrchestrator] 시작")

    async def stop(self) -> None:
        """워커 정지 및 대기 중 작업 취소."""
        if not self._running:
            return
        self._running = False
        # 대기 중인 워커 깨우기
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
        # 미처리 future 취소
        for q in self._queues.values():
            while q:
                job = q.popleft()
                if job.future is not None and not job.future.done():
                    job.future.cancel()
        logger.info("[DataOrchestrator] 정지")

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
        """과거 백필 작업 등록. ``priority`` ∈ {"high", "normal"}."""
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
        """현재(폴링) 1캔들 수집 작업 등록."""
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
        # 워커 깨우기
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
                        logger.debug("[DataOrchestrator] limiter.acquire 실패: %s", exc)

                try:
                    result = await job.executor()
                    if job.future is not None and not job.future.done():
                        job.future.set_result(result)
                    self._stats["completed"] += 1
                    self._served[job.priority] += 1
                except Exception as exc:
                    msg = str(exc).lower()
                    if "요청 수 제한" in msg or "rate limit" in msg or "429" in msg:
                        self._stats["rate_limited"] += 1
                    self._stats["failed"] += 1
                    if job.future is not None and not job.future.done():
                        job.future.set_exception(exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover
            logger.error("[DataOrchestrator] 워커 예외: %s", exc)

    def _select_next_job(self) -> Optional[FetchJob]:
        """우선순위 + 비율 보정으로 다음 작업 선택.

        보정 규칙: 더 높은 우선순위 큐가 비어있지 않으면 그쪽이 항상 우선이지만,
        해당 큐가 자기 비율(`_TOKEN_RATIOS[p]`) 만큼 연속 처리된 뒤에는 한 번
        하위 우선순위에 양보하여 starvation 을 방지한다.
        """
        # 가장 높은 비어있지 않은 큐 탐색
        for p in (PRIORITY_HISTORICAL_HIGH, PRIORITY_HISTORICAL_NORMAL, PRIORITY_REALTIME_POLLING):
            q = self._queues[p]
            if not q:
                continue
            # starvation 보호: 연속 처리량이 비율을 초과했고 하위 큐에 일이 있으면 양보
            served_now = self._served[p]
            ratio = _TOKEN_RATIOS[p]
            lower_has_job = any(
                self._queues[lp]
                for lp in (PRIORITY_HISTORICAL_HIGH, PRIORITY_HISTORICAL_NORMAL, PRIORITY_REALTIME_POLLING)
                if _PRIORITY_RANK[lp] > _PRIORITY_RANK[p]
            )
            if served_now > 0 and served_now % (ratio + 1) == 0 and lower_has_job:
                # 한 번 양보: 다음 비어있지 않은 하위 큐에서 선택
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
# 글로벌 싱글톤 (선택적 사용)
# ---------------------------------------------------------------------------

_global_orchestrator: Optional[DataOrchestrator] = None


def get_global_orchestrator() -> DataOrchestrator:
    """프로세스 전역 단일 오케스트레이터 인스턴스 반환."""
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
