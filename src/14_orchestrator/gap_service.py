# -*- coding: utf-8 -*-
"""
Gap Consumer ?쒕퉬??- Orchestrator ?듯빀??(Pylance ?명솚 ?섏젙??

?ㅻ챸:
- src/data_01/gap/consumer.py??GapConsumer瑜??좏뵆由ъ??댁뀡 ?쒖옉 ??諛깃렇?쇱슫?쒕줈 ?ㅽ뻾?섍퀬,
  ?좏뵆由ъ??댁뀡 醫낅즺 ???덉쟾???뺣━?섎룄濡??꾩?二쇰뒗 ?좏떥由ы떚?낅땲??
- Pylance 寃쎄퀬瑜??쇳븯?꾨줉 紐⑤뱢 ?섏? 蹂?섏쓽 ??낆쓣 援ъ껜 ??????Any濡??쒓린?덉뒿?덈떎.
- start_service()???숆린 而⑦뀓?ㅽ듃?먯꽌 ?덉쟾?섍쾶 ?몄텧 媛?ν븯硫?
  start_service_async()??鍮꾨룞湲?而⑦뀓?ㅽ듃?먯꽌 await濡??몄텧 媛?ν빀?덈떎.
- stop_service()???쒕퉬?ㅼ쓽 ?덉쟾??醫낅즺? 由ъ냼???뺣━瑜??대떦?⑸땲??
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

# GapConsumer import (consumer.py媛 repo??異붽??섏뼱 ?덉뼱???⑸땲??
from src.data_01.gap.consumer import create_redis_client, create_timescale_pool, GapConsumer  # type: ignore

logger = logging.getLogger("orchestrator.gap_service")

# 紐⑤뱢 ?섏? ?곹깭 (Any ??낆쓣 ?ъ슜?섏뿬 Pylance ???寃쎄퀬 諛⑹?)
_service_loop: Optional[asyncio.AbstractEventLoop] = None
_service_thread: Optional[threading.Thread] = None
_service_task: Optional[Any] = None  # asyncio.Task ?먮뒗 concurrent.futures.Future
_service_consumer: Optional[Any] = None  # GapConsumer ?몄뒪?댁뒪 (Any濡??쒓린)
_service_redis: Optional[Any] = None
_service_pool: Optional[Any] = None


async def _run_consumer_loop(redis_url: str, timescale_dsn: Optional[str], poll_interval: float = 1.0):
    """
    鍮꾨룞湲??곕꼫: Redis/timescale ?곌껐 ?앹꽦, GapConsumer ?쒖옉(?곕が), 醫낅즺 ?湲?
    ??肄붾뱶???대깽??猷⑦봽(?대뼡 ?ㅻ젅?쒖뿉?쒕뱺 ?ㅽ뻾 媛?? ?대??먯꽌 ?숈옉?⑸땲??
    """
    global _service_consumer, _service_redis, _service_pool
    try:
        _service_redis = await create_redis_client(redis_url)
    except Exception:
        logger.exception("[gap_service] Redis ?곌껐 ?ㅽ뙣")
        return

    try:
        _service_pool = await create_timescale_pool(timescale_dsn) if timescale_dsn else None
    except Exception:
        logger.exception("[gap_service] Timescale ? ?앹꽦 ?ㅽ뙣 (臾댁떆?섍퀬 吏꾪뻾)")
        _service_pool = None

    _service_consumer = GapConsumer(_service_redis, _service_pool)
    logger.info("[gap_service] GapConsumer ?몄뒪?댁뒪 ?앹꽦, ?곕が ?쒖옉")
    # GapConsumer.run? 醫낅즺 ?좏샇瑜?諛쏆쓣 ?뚭퉴吏 釉붾줈??猷⑦봽?대?濡??ш린???몄텧
    await _service_consumer.run(poll_interval=poll_interval)


def _start_loop_in_thread(loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """
    ???대깽??猷⑦봽瑜?諛쏆븘 蹂꾨룄 ?곕が ?ㅻ젅?쒖뿉???ㅽ뻾?섍퀬 Thread 媛앹껜瑜?諛섑솚?⑸땲??
    """
    def _run():
        try:
            asyncio.set_event_loop(loop)
            loop.run_forever()
        except Exception:
            logger.exception("[gap_service] ?대깽??猷⑦봽 ?ㅻ젅???덉쇅")
    t = threading.Thread(target=_run, name="gap_service_loop", daemon=True)
    t.start()
    return t


def start_service(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    ?숆린 而⑦뀓?ㅽ듃?먯꽌 ?몄텧 媛?ν븳 ?쒕퉬???쒖옉 ?⑥닔.
    - ?꾩옱 ?ㅻ젅?쒖뿉 ?대깽??猷⑦봽媛 ?ㅽ뻾 以묒씠硫??대떦 猷⑦봽?먯꽌 ?쒖뒪?щ? ?앹꽦.
    - 猷⑦봽媛 ?놁쑝硫???猷⑦봽瑜?留뚮뱾怨?蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾????run_coroutine_threadsafe濡??쒖뒪?щ? ?깅줉.
    """
    global _service_loop, _service_thread, _service_task
    try:
        # ?꾩옱 ?ㅽ뻾以묒씤 猷⑦봽 ?뺤씤
        loop = asyncio.get_running_loop()
        loop_running_here = True
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop_running_here = False

    if loop_running_here:
        # 媛숈? 猷⑦봽/?ㅻ젅?쒖뿉???ㅽ뻾 以묒씠硫?create_task濡??ㅽ뻾
        if _service_task and getattr(_service_task, "done", lambda: False)():
            logger.info("[gap_service] 湲곗〈 ?쒕퉬???쒖뒪?ш? ?ㅽ뻾 以묒엯?덈떎.")
            return
        _service_loop = loop
        try:
            _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
            logger.info("[gap_service] GapConsumer ?쒖뒪?щ? ?꾩옱 ?대깽??猷⑦봽???앹꽦?덉뒿?덈떎.")
        except Exception:
            # 諛⑹뼱?? run_coroutine_threadsafe濡??쒕룄
            fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
            _service_task = fut
            logger.info("[gap_service] GapConsumer ?쒖뒪?щ? run_coroutine_threadsafe濡??앹꽦?덉뒿?덈떎.")
    else:
        # ??猷⑦봽瑜?蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾?섍퀬 ?쒖뒪?щ? ?깅줉
        _service_loop = loop
        _service_thread = _start_loop_in_thread(loop)
        fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
        _service_task = fut
        logger.info("[gap_service] GapConsumer瑜?蹂꾨룄 ?ㅻ젅???대깽??猷⑦봽?먯꽌 ?ㅽ뻾?섎룄濡??쒖옉?덉뒿?덈떎.")


async def start_service_async(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    鍮꾨룞湲??섍꼍?먯꽌 ?쒕퉬???쒖옉: await濡??몄텧.
    """
    global _service_loop, _service_task
    loop = asyncio.get_running_loop()
    _service_loop = loop
    if _service_task and getattr(_service_task, "done", lambda: False)():
        logger.info("[gap_service] 湲곗〈 ?쒕퉬???쒖뒪?ш? ?ㅽ뻾 以묒엯?덈떎.")
        return
    _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
    logger.info("[gap_service] 鍮꾨룞湲?GapConsumer ?쒖뒪???앹꽦")


async def stop_service():
    """
    ?쒕퉬???뺤?: consumer.stop() ?몄텧, task ?湲? 由ъ냼???뺣━
    - start_service濡??쒖옉??寃쎌슦?먮룄 ??鍮꾨룞湲??⑥닔瑜??몄텧?섏뿬 ?뺣━?섏꽭??
    """
    global _service_task, _service_consumer, _service_redis, _service_pool, _service_loop, _service_thread
    logger.info("[gap_service] ?쒕퉬??以묒? ?쒖옉")
    try:
        if _service_consumer:
            _service_consumer.stop()
        # ?쒖뒪?ш? asyncio.Task??寃쎌슦
        if isinstance(_service_task, asyncio.Task):
            try:
                await asyncio.wait_for(_service_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[gap_service] ?쒕퉬??醫낅즺 ??꾩븘?????쒖뒪??痍⑥냼")
                _service_task.cancel()
                try:
                    await _service_task
                except Exception:
                    pass
        else:
            # concurrent.futures.Future (run_coroutine_threadsafe 諛섑솚)??寃쎌슦 cancel ?쒕룄
            if _service_task is not None:
                try:
                    _service_task.cancel()
                except Exception:
                    logger.debug("[gap_service] concurrent future cancel ?ㅽ뙣", exc_info=True)
        # ?덉쟾??Redis/DB 醫낅즺
        if _service_redis:
            try:
                if hasattr(_service_redis, "aclose"):
                    res = _service_redis.aclose()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(_service_redis, "close"):
                    res = _service_redis.close()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                logger.debug("[gap_service] redis ?덉쟾醫낅즺 以??덉쇅", exc_info=True)
        if _service_pool:
            try:
                await _service_pool.close()
            except Exception:
                logger.debug("[gap_service] pool close 以??덉쇅", exc_info=True)
    finally:
        # 蹂꾨룄 猷⑦봽/?ㅻ젅?쒕줈 ?ㅽ뻾??寃쎌슦 猷⑦봽 ?뺣━
        if _service_loop and _service_thread:
            try:
                _service_loop.call_soon_threadsafe(_service_loop.stop)
            except Exception:
                logger.debug("[gap_service] 蹂꾨룄 猷⑦봽 ?뺤? ?몄텧 ?ㅽ뙣", exc_info=True)
            try:
                _service_thread.join(timeout=5.0)
            except Exception:
                logger.debug("[gap_service] ?쒕퉬???ㅻ젅??join ?ㅽ뙣", exc_info=True)
        # ?곹깭 珥덇린??
        _service_task = None
        _service_consumer = None
        _service_redis = None
        _service_pool = None
        _service_loop = None
        _service_thread = None
        logger.info("[gap_service] ?쒕퉬??以묒? ?꾨즺")
