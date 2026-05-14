# -*- coding: utf-8 -*-
"""
REST API 다중 타임프레임 캔들 수집기 (Upbit 공식 API) v8
+ WebSocket 우선(hybrid/ws/rest) 통합 버전

주요 개선:
- 전역/모듈 레이트 리미터 적용 (aiolimiter 또는 내장 SimpleRateLimiter)
- 지수 백오프 + 재시도 로직 강화
- 동시성 제어(세마포어) 유지
- pipeline 콜백 동기/비동기 안전 처리 (executor 사용)
- 요청 간 소량의 jitter 추가로 burst 완화
"""
import asyncio
import logging
import os
import random
import time
import inspect
from datetime import datetime, timezone
from typing import Optional, Callable, Iterable, List, Any

logger = logging.getLogger(__name__)

try:
    import aiopyupbit
    _HAS_AIOPYUPBIT = True
except ImportError:
    _HAS_AIOPYUPBIT = False
    logger.warning("[RestCandleCollector] aiopyupbit 미설치 — pip install aiopyupbit")

# -- WebSocket 매니저(선택적) --
try:
    from .ws_candle_manager import get_ws_manager  # type: ignore
    _HAS_WS_MANAGER = True
except Exception:
    get_ws_manager = None  # type: ignore
    _HAS_WS_MANAGER = False

# -- 외부 async_rate_limiter 연동 시도 (옵션) --
try:
    from .async_rate_limiter import (
        get_global_upbit_rate_limiter,
        is_rate_limit_error,
        rate_limit_backoff_delays,
    )
    _HAS_EXTERNAL_RATE_LIMITER = True
except Exception:
    get_global_upbit_rate_limiter = None  # type: ignore
    is_rate_limit_error = None  # type: ignore
    rate_limit_backoff_delays = None  # type: ignore
    _HAS_EXTERNAL_RATE_LIMITER = False

# -- aiolimiter 선택 사용(있으면) --
try:
    from aiolimiter import AsyncLimiter  # type: ignore
    _HAS_AIOLIMITER = True
except Exception:
    AsyncLimiter = None  # type: ignore
    _HAS_AIOLIMITER = False

# ----------------------------
# 내장 SimpleRateLimiter (aiolimiter가 없을 때 폴백)
# ----------------------------
class SimpleRateLimiter:
    """단순 토큰버킷 기반 비동기 레이트 리미터.
    rate: 초당 토큰 수, per: 기준 간격(초)
    """
    def __init__(self, rate: int = 10, per: float = 1.0):
        self._rate = max(1, int(rate))
        self._per = float(per)
        self._tokens = float(self._rate)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed > 0:
                # refill
                self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._per))
                self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            # need to wait until token available
            # compute wait time for next token
            need = 1 - self._tokens
            wait = need * (self._per / self._rate)
        # release lock before sleeping
        await asyncio.sleep(wait)
        # recursive attempt (cheap)
        await self.acquire()

# 모듈 레벨 전역 레이터 생성기 (싱글톤 스타일)
_rate_limiter_singleton: Optional[Any] = None

def _get_or_create_rate_limiter() -> Any:
    """외부 리미터가 없다면 내부 SimpleRateLimiter 또는 AsyncLimiter를 생성해서 반환."""
    global _rate_limiter_singleton
    if _rate_limiter_singleton is not None:
        return _rate_limiter_singleton

    # 환경변수: 초당 요청 수 허용
    rps = int(os.getenv("REST_COLLECTOR_RATE_PER_SEC", os.getenv("UPBIT_RATE_PER_SEC", "5")))
    if _HAS_AIOLIMITER and AsyncLimiter is not None:
        _rate_limiter_singleton = AsyncLimiter(rps, time_period=1)
        logger.debug("[RestCandleCollector] aiolimiter 사용: rate=%d/sec", rps)
    else:
        _rate_limiter_singleton = SimpleRateLimiter(rate=rps, per=1.0)
        logger.debug("[RestCandleCollector] SimpleRateLimiter 사용: rate=%d/sec", rps)
    return _rate_limiter_singleton

# 백오프 델레이 기본 (외부 모듈이 제공하지 않으면 사용)
def _default_backoff_delays():
    return (0.5, 1.0, 2.0, 4.0)

def _default_is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg

# ----------------------------
# RestCandleCollector
# ----------------------------
class RestCandleCollector:
    """설정된 타임프레임의 최신 OHLCV 캔들을 REST API로 수집합니다."""

    _INTERVAL_MAP = {
        "1m": "minute1",
        "3m": "minute3",
        "5m": "minute5",
        "10m": "minute10",
        "15m": "minute15",
        "30m": "minute30",
        "1h": "minute60",
        "4h": "minute240",
        "1d": "day",
    }

    def __init__(
        self,
        symbols: Iterable[str],
        interval_seconds: int = 60,
        timeframes: Optional[Iterable[str]] = None,
        collect_mode: str = "hybrid",  # "hybrid" | "ws" | "rest"
    ):
        """
        Args:
            symbols: 수집할 심볼 리스트 (예: ['KRW-BTC', 'KRW-ETH'])
            interval_seconds: 수집 주기 (초, 기본 60초)
            timeframes: 수집할 타임프레임 목록 (예: ['1m', '5m', '1h'])
            collect_mode: 'hybrid'|'ws'|'rest' - 수집 우선 방식
        """
        self._symbols = list(symbols)
        self._interval = interval_seconds
        self._timeframes = self._normalize_timeframes(timeframes)
        self._collect_mode = str(collect_mode or "hybrid").lower()
        if self._collect_mode not in ("hybrid", "ws", "rest"):
            self._collect_mode = "hybrid"

        # 동시성 & 레이트 제어: 환경변수 ��선
        self._max_concurrent = max(1, int(os.getenv("REST_COLLECTOR_MAX_CONCURRENT", "8")))
        self._request_delay = max(0.0, float(os.getenv("REST_COLLECTOR_REQUEST_DELAY", "0.05")))
        # 외부 전역 레이팅 리미터(모듈 제공시) 또는 내부 생성
        self._rate_limiter = None
        try:
            if _HAS_EXTERNAL_RATE_LIMITER and callable(get_global_upbit_rate_limiter):
                self._rate_limiter = get_global_upbit_rate_limiter()
            else:
                self._rate_limiter = _get_or_create_rate_limiter()
        except Exception as e:
            logger.debug("[RestCandleCollector] rate_limiter init failed, using fallback: %s", e)
            self._rate_limiter = _get_or_create_rate_limiter()

        # 백오프/레이트 판별 함수 준비
        self._rate_limit_checker = is_rate_limit_error if (is_rate_limit_error is not None) else _default_is_rate_limit_error
        self._backoff_policy = rate_limit_backoff_delays() if (callable(rate_limit_backoff_delays)) else _default_backoff_delays()

        self._pipeline_callback: Optional[Callable] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._df_logged = False  # DataFrame 구조 로그 플래그

        self._stats = {
            "total_collected": 0,
            "total_errors": 0,
            "last_collect_time": None,
        }

        # WebSocket manager 인스턴스(있을 때만 사용)
        self._ws_mgr = None
        if _HAS_WS_MANAGER and get_ws_manager is not None:
            try:
                self._ws_mgr = get_ws_manager()
            except Exception:
                self._ws_mgr = None

    @classmethod
    def _normalize_timeframes(cls, timeframes: Optional[Iterable[str]]) -> List[str]:
        resolved: List[str] = []
        for tf in list(timeframes or ["1m"]):
            tf = str(tf).strip()
            if tf in cls._INTERVAL_MAP and tf not in resolved:
                resolved.append(tf)
        return resolved or ["1m"]

    def set_pipeline_callback(self, callback: Callable) -> None:
        """Pipeline 콜백 등록"""
        self._pipeline_callback = callback
        logger.info("[RestCandleCollector] ✅ Pipeline 콜백 등록 완료")

    async def start(self) -> None:
        """수집 시작"""
        if not _HAS_AIOPYUPBIT:
            logger.error("[RestCandleCollector] aiopyupbit 없음 — 시작 불가")
            return

        if self._running:
            logger.warning("[RestCandleCollector] 이미 실행 중")
            return

        # WS 매니저 시작 시도 (hybrid/ws 모드인 경우)
        if self._collect_mode in ("hybrid", "ws") and self._ws_mgr is not None:
            try:
                await self._ws_mgr.start()
                logger.info("[RestCandleCollector] WS 매니저 시작 시도 (collect_mode=%s)", self._collect_mode)
            except Exception as exc:
                logger.debug("[RestCandleCollector] WS 매니저 시작 실패: %s", exc)

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info(
            "[RestCandleCollector] ✅ 시작 (%d개 심볼, TF=%s, %d초 주기, 동시요청=%d, mode=%s)",
            len(self._symbols), ",".join(self._timeframes), self._interval, self._max_concurrent, self._collect_mode
        )

    async def stop(self) -> None:
        """수집 중지"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[RestCandleCollector] 🛑 중지")

    async def _collect_loop(self) -> None:
        """주기적 수집 루프"""
        while self._running:
            try:
                await self._collect_once()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("[RestCandleCollector] 수집 루프 에러: %s", exc)
                await asyncio.sleep(self._interval)

    async def _collect_once(self) -> None:
        """1회 수집 (모든 심볼 × 활성 타임프레임)"""
        collected = 0
        errors = 0
        sem = asyncio.Semaphore(self._max_concurrent)

        async def _fetch_one(symbol: str, timeframe: str):
            nonlocal collected, errors
            try:
                async with sem:
                    # optional rate limiter acquire
                    try:
                        if self._rate_limiter is not None:
                            await self._acquire_rate_limit()
                    except Exception as rl_exc:
                        # rate limiter 내부 문제라도 REST 시도 계속하도록 경고 로깅
                        logger.debug("[RestCandleCollector] rate_limiter acquire failed (ignored): %s", rl_exc)

                    candles = await self._fetch_candle(symbol, timeframe)
                    # 약간의 지연 + 소량의 jitter로 burst 완화
                    if self._request_delay:
                        jitter = random.uniform(0, self._request_delay * 0.5)
                        await asyncio.sleep(self._request_delay + jitter)

                if candles:
                    # pipeline 콜백을 안전하게 실행 (sync/async 모두 지��)
                    for candle in candles:
                        await self._dispatch_pipeline_callback_safe(candle)
                    collected += len(candles)
                return
            except Exception as exc:
                logger.warning("[RestCandleCollector] %s/%s 수집 실패: %s", symbol, timeframe, exc)
                errors += 1
                return

        tasks = [
            asyncio.create_task(_fetch_one(symbol, timeframe))
            for timeframe in self._timeframes
            for symbol in self._symbols
        ]

        # await all tasks and handle exceptions per-task
        for fut in asyncio.as_completed(tasks):
            try:
                await fut
            except Exception as exc:
                logger.debug("[RestCandleCollector] task exception (ignored): %s", exc)

        self._stats["total_collected"] += collected
        self._stats["total_errors"] += errors
        self._stats["last_collect_time"] = datetime.now(timezone.utc)

        logger.info(
            "[RestCandleCollector] 수집 완료: %d개 캔들 (에러 %d개, Pipeline 전송 완료)",
            collected, errors
        )

    async def _fetch_candle(self, symbol: str, timeframe: str) -> list:
        """단일 심볼/타임프레임의 최신 캔들을 가져오기."""

        # 0) WebSocket 우선 체크: hybrid/ws 모드이면 WS에서 최신값 사용 시도
        try:
            if self._collect_mode in ("hybrid", "ws") and self._ws_mgr is not None:
                try:
                    if self._ws_mgr.is_subscribed(symbol, timeframe):
                        latest = self._ws_mgr.get_latest(symbol, timeframe)
                        if latest:
                            logger.debug("[RestCandleCollector] WS에서 최신 캔들 사용: %s %s", symbol, timeframe)
                            return [latest]
                        else:
                            if self._collect_mode == "ws":
                                logger.debug("[RestCandleCollector] WS 전용 모드 및 데이터 미수신: %s %s", symbol, timeframe)
                                return []
                except Exception as ws_exc:
                    logger.debug("[RestCandleCollector] WS 체크 중 오류(무시): %s", ws_exc)
        except Exception:
            pass

        # REST 경로: 백오프 + 레이트 리밋 적용
        try:
            interval = self._INTERVAL_MAP.get(timeframe)
            if interval is None:
                logger.debug("[RestCandleCollector] 지원하지 않는 timeframe 스킵: %s", timeframe)
                return []

            # choose limiter and backoff policy
            limiter = self._rate_limiter
            backoffs = tuple(self._backoff_policy) if self._backoff_policy else tuple(_default_backoff_delays())
            last_exc: Optional[BaseException] = None
            df = None

            for attempt in range(len(backoffs) + 1):
                # acquire rate limiter if provided
                if limiter is not None:
                    try:
                        # aiolimiter AsyncLimiter supports async with
                        if _HAS_AIOLIMITER and AsyncLimiter is not None and isinstance(limiter, AsyncLimiter):
                            async with limiter:
                                df = await aiopyupbit.get_ohlcv(symbol, interval=interval, count=1)
                        else:
                            # our SimpleRateLimiter supports await limiter.acquire()
                            await limiter.acquire()
                            df = await aiopyupbit.get_ohlcv(symbol, interval=interval, count=1)
                        last_exc = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        # rate-limit 판단
                        is_rl = False
                        try:
                            is_rl = bool(self._rate_limit_checker(exc))
                        except Exception:
                            is_rl = _default_is_rate_limit_error(exc)
                        if attempt < len(backoffs) and is_rl:
                            delay = backoffs[attempt]
                            logger.info(
                                "[RestCandleCollector] %s/%s 레이트리밋 감지 — %.1fs 후 재시도(%d/%d)",
                                symbol, timeframe, delay, attempt + 1, len(backoffs),
                            )
                            await asyncio.sleep(delay)
                            continue
                        # not a rate-limit or retries exhausted => re-raise below
                        logger.debug("[RestCandleCollector] REST call failed (attempt=%d): %s", attempt + 1, exc, exc_info=True)
                        # if not rate limit, break to outer raise
                        if not is_rl:
                            break
                else:
                    # no limiter (shouldn't happen) -> direct call
                    df = await aiopyupbit.get_ohlcv(symbol, interval=interval, count=1)
                    last_exc = None
                    break

            if last_exc is not None:
                raise last_exc

            if df is None or getattr(df, "empty", False):
                return []

            # DataFrame 구조 로그 (한 번)
            if not self._df_logged:
                try:
                    logger.info(
                        "[RestCandleCollector] DataFrame 구조: columns=%s, index=%s, index_dtype=%s",
                        list(df.columns), getattr(df.index, "tolist", lambda: None)(), getattr(df.index, "dtype", None)
                    )
                except Exception:
                    logger.debug("[RestCandleCollector] DataFrame 구조 로그 실패", exc_info=True)
                self._df_logged = True

            # DataFrame → dict 변환
            candles: List[dict] = []
            for idx, row in df.iterrows():
                candle_time = None

                # timestamp 우선 처리
                if "timestamp" in row and row["timestamp"] is not None:
                    try:
                        ts = row["timestamp"]
                        if isinstance(ts, (int, float)):
                            if ts < 10000000000:
                                candle_time = datetime.fromtimestamp(ts, tz=timezone.utc)
                            elif ts < 10000000000000:
                                candle_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            else:
                                candle_time = datetime.fromtimestamp(ts / 1000000, tz=timezone.utc)
                        elif hasattr(ts, "to_pydatetime"):
                            candle_time = ts.to_pydatetime()
                            if candle_time.tzinfo is None:
                                candle_time = candle_time.replace(tzinfo=timezone.utc)
                    except Exception as e:
                        logger.debug("[RestCandleCollector] timestamp 컬럼 파싱 실패: %s", e)

                if candle_time is None and "time" in row and row["time"] is not None:
                    try:
                        t = row["time"]
                        if hasattr(t, "to_pydatetime"):
                            candle_time = t.to_pydatetime()
                            if candle_time.tzinfo is None:
                                candle_time = candle_time.replace(tzinfo=timezone.utc)
                        elif isinstance(t, str):
                            candle_time = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    except Exception as e:
                        logger.debug("[RestCandleCollector] time 컬럼 파싱 실패: %s", e)

                if candle_time is None and hasattr(idx, "to_pydatetime"):
                    try:
                        candle_time = idx.to_pydatetime()
                        if candle_time.tzinfo is None:
                            candle_time = candle_time.replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

                if candle_time is None and isinstance(idx, (int, float)) and idx != 0:
                    try:
                        if idx < 10000000000:
                            candle_time = datetime.fromtimestamp(idx, tz=timezone.utc)
                        elif idx < 10000000000000:
                            candle_time = datetime.fromtimestamp(idx / 1000, tz=timezone.utc)
                        elif idx < 10000000000000000:
                            candle_time = datetime.fromtimestamp(idx / 1000000, tz=timezone.utc)
                        else:
                            candle_time = datetime.fromtimestamp(idx / 1000000000, tz=timezone.utc)
                    except Exception:
                        pass

                if candle_time is None:
                    logger.warning(
                        "[RestCandleCollector] %s/%s: 시간 필드를 찾을 수 없음! idx=%s (type=%s), row.keys=%s - 현재 시간 사용",
                        symbol, timeframe, idx, type(idx).__name__, list(row.keys())
                    )
                    candle_time = datetime.now(timezone.utc)

                if candle_time.year == 1970:
                    logger.error(
                        "[RestCandleCollector] %s/%s: 1970년 시간 감지! idx=%s (type=%s) - 현재 시간으로 대체",
                        symbol, timeframe, idx, type(idx).__name__
                    )
                    candle_time = datetime.now(timezone.utc)

                candle = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": candle_time,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "quote_volume": float(row.get("value", 0)),
                    "exchange": "upbit",
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
                candles.append(candle)

                if len(candles) <= 1:
                    logger.debug(
                        "[RestCandleCollector] %s/%s: idx=%s (type=%s) → time=%s (close=%.2f)",
                        symbol, timeframe, idx, type(idx).__name__, candle_time, candle["close"]
                    )

            return candles

        except Exception as exc:
            # 레이트리밋 판단 시도
            try:
                is_rl = bool(self._rate_limit_checker(exc))
            except Exception:
                is_rl = _default_is_rate_limit_error(exc)

            if is_rl:
                logger.warning(
                    "[RestCandleCollector] %s/%s API 호출 실패: 요청 수 제한을 초과했습니다 (재시도 소진)",
                    symbol, timeframe,
                )
            else:
                logger.warning(
                    "[RestCandleCollector] %s/%s API 호출 실패: %s",
                    symbol, timeframe, str(exc),
                )
            return []

    async def _acquire_rate_limit(self):
        """rate limiter acquire 추상화(다양한 리미터 호환)"""
        limiter = self._rate_limiter
        if limiter is None:
            return
        # aiolimiter AsyncLimiter supports async with
        if _HAS_AIOLIMITER and AsyncLimiter is not None and isinstance(limiter, AsyncLimiter):
            # handled in caller via async with
            return
        # our SimpleRateLimiter
        await limiter.acquire()

    async def _dispatch_pipeline_callback_safe(self, candle: dict) -> None:
        """pipeline 콜백을 동기/비동기 모두 안전하게 호출. 예외는 로깅 후 무시."""
        if not self._pipeline_callback:
            return
        try:
            res = self._pipeline_callback(candle)
            # awaitable이면 await
            if inspect.isawaitable(res):
                await res  # type: ignore
            else:
                # 동기 콜백은 executor에서 실행
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._pipeline_callback, candle)
        except Exception as cb_exc:
            logger.warning("[RestCandleCollector] Pipeline 콜백 실행 중 예외: %s", cb_exc)

    def get_stats(self) -> dict:
        """통계 조회"""
        return self._stats.copy()