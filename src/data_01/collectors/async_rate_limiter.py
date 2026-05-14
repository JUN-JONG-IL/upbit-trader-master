# -*- coding: utf-8 -*-
"""
鍮꾨룞湲?湲濡쒕쾶 Rate Limiter (Upbit REST ?꾩슜)

?ㅺ퀎 硫붾え
---------
- Upbit 怨듦컻 REST ?쒕룄: 珥덈떦 10?? 遺꾨떦 600??
- ?ㅼ쨷 ?щ낵 횞 ?ㅼ쨷 ??꾪봽?덉엫 ?숈떆 ?몄텧 ??湲곗〈 ``asyncio.Semaphore`` + 怨좎젙
  ``request_delay`` 留뚯쑝濡쒕뒗 利됱떆 ?쒕룄瑜?珥덇낵?섏뿬 ``?붿껌 ???쒗븳??珥덇낵?덉뒿?덈떎``
  寃쎄퀬媛 諛쒖깮?? (rest_candle_collector / auto_backfill_manager ?묒そ???쒕룄瑜?
  怨듭쑀?섏? ?딅뒗 ?먯씠 洹쇰낯 ?먯씤)
- 蹂?紐⑤뱢? ???덈룄??珥?遺?瑜??숈떆??留뚯”?쒗궎??鍮꾨룞湲??좏겙踰꾪궥???쒓났?섎ŉ,
  ?좏뵆由ъ??댁뀡 ???곸뿭?먯꽌 ?⑥씪 ?몄뒪?댁뒪瑜?怨듭쑀?????덈룄濡?
  ``get_global_upbit_rate_limiter()`` ?깃??ㅼ쓣 ?몄텧??
- ?덉쟾留덉쭊: per-second=9 (?쒕룄 10 ?鍮?-1), per-minute=550 (?쒕룄 600 ?鍮?-50).

??紐⑤뱢? ?좉퇋 異붽? 紐⑤뱢?대ŉ 湲곗〈 ``rate_limiter.py`` (?숆린 踰꾩쟾)瑜?蹂寃쏀븯吏
?딅뒗?? ?몄텧?먭? ?먯쭊?곸쑝濡?留덉씠洹몃젅?댁뀡?????덈룄濡??쒕떎.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Deque, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "AsyncRateLimiter",
    "get_global_upbit_rate_limiter",
    "is_rate_limit_error",
    "rate_limit_backoff_delays",
    "UPBIT_REST_PER_SECOND_LIMIT",
    "UPBIT_REST_PER_MINUTE_LIMIT",
]

# Upbit 怨듭떇 REST API ?쒕룄 ???대옩??寃利앹쓽 ?⑥씪 吏꾩떎 ?뚯뒪
UPBIT_REST_PER_SECOND_LIMIT = 10   # 怨듭떇 ?쒕룄 (珥?
UPBIT_REST_PER_MINUTE_LIMIT = 600  # 怨듭떇 ?쒕룄 (遺?
UPBIT_REST_PER_SECOND_FLOOR = 1
UPBIT_REST_PER_MINUTE_FLOOR = 10


class AsyncRateLimiter:
    """鍮꾨룞湲??ㅼ쨷 ?덈룄???좏겙踰꾪궥 Rate Limiter.

    ?щ윭 肄붾（?댁씠 ?숈떆??``acquire()`` 瑜??몄텧?대룄 ?덉쟾?섍쾶 吏곷젹?뷀븳??
    珥?遺??덈룄????媛쒕? ?숈떆??留뚯”?쒗궗 ?뚭퉴吏 sleep ?쒕떎.

    Args:
        per_second: 1珥??덈룄????理쒕? ?몄텧 ??
        per_minute: 60珥??덈룄????理쒕? ?몄텧 ??
    """

    def __init__(self, per_second: int = 9, per_minute: int = 550) -> None:
        if per_second <= 0 or per_minute <= 0:
            raise ValueError("per_second/per_minute must be positive")
        self._per_second = int(per_second)
        self._per_minute = int(per_minute)
        self._sec_calls: Deque[float] = deque()
        self._min_calls: Deque[float] = deque()
        self._lock = asyncio.Lock()

    @property
    def per_second(self) -> int:
        return self._per_second

    @property
    def per_minute(self) -> int:
        return self._per_minute

    async def acquire(self) -> None:
        """?몄텧 ?덇?瑜??띾뱷???뚭퉴吏 ?湲?

        珥?遺??덈룄???????ъ쑀媛 ?덉쓣 ?뚮쭔 利됱떆 ?듦낵?쒗궎怨? 洹몃젃吏 ?딆쑝硫?
        媛??媛源뚯슫 留뚮즺 ?쒖젏源뚯? sleep ?쒕떎. ?쎌쓣 ?≪? 梨?sleep ?섎?濡??몄텧
        ?쒖꽌媛 ?먯뿰?ㅻ읇寃?吏곷젹?붾맂??
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                self._evict(now)

                wait_sec = 0.0
                if len(self._sec_calls) >= self._per_second:
                    wait_sec = max(wait_sec, self._sec_calls[0] + 1.0 - now)
                if len(self._min_calls) >= self._per_minute:
                    wait_sec = max(wait_sec, self._min_calls[0] + 60.0 - now)

                if wait_sec <= 0.0:
                    self._sec_calls.append(now)
                    self._min_calls.append(now)
                    return

                # ?쎄컙??jitter 瑜??뷀빐 thundering herd ?뚰뵾
                await asyncio.sleep(wait_sec + 0.005)

    def _evict(self, now: float) -> None:
        sec_cut = now - 1.0
        min_cut = now - 60.0
        while self._sec_calls and self._sec_calls[0] <= sec_cut:
            self._sec_calls.popleft()
        while self._min_calls and self._min_calls[0] <= min_cut:
            self._min_calls.popleft()

    def snapshot(self) -> dict:
        """?붾쾭洹몄슜 ?꾩옱 ?ъ슜???ㅻ깄??"""
        now = time.monotonic()
        self._evict(now)
        return {
            "per_second_used": len(self._sec_calls),
            "per_second_limit": self._per_second,
            "per_minute_used": len(self._min_calls),
            "per_minute_limit": self._per_minute,
        }


# ---------------------------------------------------------------------------
# 湲濡쒕쾶 ?깃?????REST ?섏쭛湲?/ 諛깊븘?ш? 怨듭쑀
# ---------------------------------------------------------------------------

_global_limiter: Optional[AsyncRateLimiter] = None


def _load_ssot_rate_limits() -> tuple:
    """performance_settings.py SSOT ?먯꽌 (per_sec, per_min) ???쎈뒗??

    ?깅뒫 ?ㅼ젙 紐⑤뱢? ``14_orchestrator`` ?⑦궎吏(?レ옄 ?쒖옉)???덉뼱 ?쒖?
    import 媛 遺덇??ν븯誘濡??뚯씪 湲곕컲 ?숈쟻 濡쒕뱶濡??묎렐?쒕떎. ?ㅽ뙣 ??None 諛섑솚.
    """
    try:
        import importlib.util
        import pathlib
        import sys
        _key = "_perf_settings_for_arl"
        if _key in sys.modules:
            mod = sys.modules[_key]
        else:
            here = pathlib.Path(__file__).resolve()
            # src/data_01/collectors/async_rate_limiter.py ??src/
            src_root = here.parents[2]
            ps_path = src_root / "14_orchestrator" / "backfill" / "performance_settings.py"
            if not ps_path.exists():
                return None, None
            spec = importlib.util.spec_from_file_location(_key, str(ps_path))
            if spec is None or spec.loader is None:
                return None, None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[_key] = mod
            spec.loader.exec_module(mod)
        per_sec_fn = getattr(mod, "get_rest_rate_per_second", None)
        per_min_fn = getattr(mod, "get_rest_rate_per_minute", None)
        per_sec = int(per_sec_fn()) if callable(per_sec_fn) else None
        per_min = int(per_min_fn()) if callable(per_min_fn) else None
        return per_sec, per_min
    except Exception as exc:
        logger.debug("[AsyncRateLimiter] SSOT 濡쒕뱶 ?ㅽ뙣: %s", exc)
        return None, None


def get_global_upbit_rate_limiter() -> AsyncRateLimiter:
    """?꾩뿭 Upbit REST Rate Limiter ?몄뒪?댁뒪瑜?諛섑솚?쒕떎.

    ?쒕룄 寃곗젙 ?곗꽑?쒖쐞:
        1) MongoDB ui_settings.backfill_scheduler.performance.rest_rate_per_*
           (performance_settings.py SSOT)
        2) ?섍꼍蹂??UPBIT_REST_RATE_PER_SECOND / UPBIT_REST_RATE_PER_MINUTE
        3) ?뺤쟻 湲곕낯媛?(9 / 550)
    """
    global _global_limiter
    if _global_limiter is None:
        # 1) SSOT ?곗꽑
        per_sec, per_min = _load_ssot_rate_limits()
        # 2) env ?대갚
        if per_sec is None:
            try:
                per_sec = int(os.getenv("UPBIT_REST_RATE_PER_SECOND", "9"))
            except (TypeError, ValueError):
                per_sec = 9
        if per_min is None:
            try:
                per_min = int(os.getenv("UPBIT_REST_RATE_PER_MINUTE", "550"))
            except (TypeError, ValueError):
                per_min = 550
        # 3) ?덉쟾 踰붿쐞 ?대옩??(Upbit 怨듭떇 ?쒕룄 珥덇낵 諛⑹?)
        per_sec = max(UPBIT_REST_PER_SECOND_FLOOR, min(int(per_sec), UPBIT_REST_PER_SECOND_LIMIT))
        per_min = max(UPBIT_REST_PER_MINUTE_FLOOR, min(int(per_min), UPBIT_REST_PER_MINUTE_LIMIT))
        _global_limiter = AsyncRateLimiter(per_second=per_sec, per_minute=per_min)
        logger.info(
            "[AsyncRateLimiter] 湲濡쒕쾶 ?몄뒪?댁뒪 ?앹꽦: %d req/s, %d req/min",
            per_sec, per_min,
        )
    return _global_limiter


# ---------------------------------------------------------------------------
# 怨듯넻 ?좏떥: 429 / ?쒕룄 珥덇낵 硫붿떆吏 媛먯? & 諛깆삤???쒗??
# ---------------------------------------------------------------------------

# Upbit ?쒓뎅???곷Ц ?쒕룄 硫붿떆吏瑜?紐⑤몢 而ㅻ쾭.
_RATE_LIMIT_TOKENS = (
    "?붿껌 ???쒗븳",
    "too many requests",
    "rate limit",
    "429",
)


def is_rate_limit_error(exc: BaseException | str | None) -> bool:
    """二쇱뼱吏??덉쇅/臾몄옄?댁씠 ?덉씠?몃━諛?愿?⑥씤吏 ?먯젙?쒕떎."""
    if exc is None:
        return False
    msg = str(exc).lower()
    return any(tok.lower() in msg for tok in _RATE_LIMIT_TOKENS)


def rate_limit_backoff_delays() -> tuple:
    """吏??諛깆삤???쒗??(珥?. 0.5 ??1 ??2 ??4 (理쒕? 4???湲?."""
    return (0.5, 1.0, 2.0, 4.0)

