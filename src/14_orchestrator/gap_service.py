# -*- coding: utf-8 -*-
"""
Gap Consumer ?œë¹„??- Orchestrator ?µí•©??(Pylance ?¸í™˜ ?˜ì •??

?¤ëª…:
- src/data_01/gap/consumer.py??GapConsumerë¥?? í”Œë¦¬ì??´ì…˜ ?œì‘ ??ë°±ê·¸?¼ìš´?œë¡œ ?¤í–‰?˜ê³ ,
  ? í”Œë¦¬ì??´ì…˜ ì¢…ë£Œ ???ˆì „???•ë¦¬?˜ë„ë¡??„ì?ì£¼ëŠ” ? í‹¸ë¦¬í‹°?…ë‹ˆ??
- Pylance ê²½ê³ ë¥??¼í•˜?„ë¡ ëª¨ë“ˆ ?˜ì? ë³€?˜ì˜ ?€?…ì„ êµ¬ì²´ ?€???€??Anyë¡??œê¸°?ˆìŠµ?ˆë‹¤.
- start_service()???™ê¸° ì»¨í…?¤íŠ¸?ì„œ ?ˆì „?˜ê²Œ ?¸ì¶œ ê°€?¥í•˜ë©?
  start_service_async()??ë¹„ë™ê¸?ì»¨í…?¤íŠ¸?ì„œ awaitë¡??¸ì¶œ ê°€?¥í•©?ˆë‹¤.
- stop_service()???œë¹„?¤ì˜ ?ˆì „??ì¢…ë£Œ?€ ë¦¬ì†Œ???•ë¦¬ë¥??´ë‹¹?©ë‹ˆ??
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

# GapConsumer import (consumer.pyê°€ repo??ì¶”ê??˜ì–´ ?ˆì–´???©ë‹ˆ??
from src.data_01.gap.consumer import create_redis_client, create_timescale_pool, GapConsumer  # type: ignore

logger = logging.getLogger("orchestrator.gap_service")

# ëª¨ë“ˆ ?˜ì? ?íƒœ (Any ?€?…ì„ ?¬ìš©?˜ì—¬ Pylance ?€??ê²½ê³  ë°©ì?)
_service_loop: Optional[asyncio.AbstractEventLoop] = None
_service_thread: Optional[threading.Thread] = None
_service_task: Optional[Any] = None  # asyncio.Task ?ëŠ” concurrent.futures.Future
_service_consumer: Optional[Any] = None  # GapConsumer ?¸ìŠ¤?´ìŠ¤ (Anyë¡??œê¸°)
_service_redis: Optional[Any] = None
_service_pool: Optional[Any] = None


async def _run_consumer_loop(redis_url: str, timescale_dsn: Optional[str], poll_interval: float = 1.0):
    """
    ë¹„ë™ê¸??°ë„ˆ: Redis/timescale ?°ê²° ?ì„±, GapConsumer ?œì‘(?°ëª¬), ì¢…ë£Œ ?€ê¸?
    ??ì½”ë“œ???´ë²¤??ë£¨í”„(?´ë–¤ ?¤ë ˆ?œì—?œë“  ?¤í–‰ ê°€?? ?´ë??ì„œ ?™ì‘?©ë‹ˆ??
    """
    global _service_consumer, _service_redis, _service_pool
    try:
        _service_redis = await create_redis_client(redis_url)
    except Exception:
        logger.exception("[gap_service] Redis ?°ê²° ?¤íŒ¨")
        return

    try:
        _service_pool = await create_timescale_pool(timescale_dsn) if timescale_dsn else None
    except Exception:
        logger.exception("[gap_service] Timescale ?€ ?ì„± ?¤íŒ¨ (ë¬´ì‹œ?˜ê³  ì§„í–‰)")
        _service_pool = None

    _service_consumer = GapConsumer(_service_redis, _service_pool)
    logger.info("[gap_service] GapConsumer ?¸ìŠ¤?´ìŠ¤ ?ì„±, ?°ëª¬ ?œì‘")
    # GapConsumer.run?€ ì¢…ë£Œ ? í˜¸ë¥?ë°›ì„ ?Œê¹Œì§€ ë¸”ë¡œ??ë£¨í”„?´ë?ë¡??¬ê¸°???¸ì¶œ
    await _service_consumer.run(poll_interval=poll_interval)


def _start_loop_in_thread(loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """
    ???´ë²¤??ë£¨í”„ë¥?ë°›ì•„ ë³„ë„ ?°ëª¬ ?¤ë ˆ?œì—???¤í–‰?˜ê³  Thread ê°ì²´ë¥?ë°˜í™˜?©ë‹ˆ??
    """
    def _run():
        try:
            asyncio.set_event_loop(loop)
            loop.run_forever()
        except Exception:
            logger.exception("[gap_service] ?´ë²¤??ë£¨í”„ ?¤ë ˆ???ˆì™¸")
    t = threading.Thread(target=_run, name="gap_service_loop", daemon=True)
    t.start()
    return t


def start_service(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    ?™ê¸° ì»¨í…?¤íŠ¸?ì„œ ?¸ì¶œ ê°€?¥í•œ ?œë¹„???œì‘ ?¨ìˆ˜.
    - ?„ì¬ ?¤ë ˆ?œì— ?´ë²¤??ë£¨í”„ê°€ ?¤í–‰ ì¤‘ì´ë©??´ë‹¹ ë£¨í”„?ì„œ ?œìŠ¤?¬ë? ?ì„±.
    - ë£¨í”„ê°€ ?†ìœ¼ë©???ë£¨í”„ë¥?ë§Œë“¤ê³?ë³„ë„ ?¤ë ˆ?œì—???¤í–‰????run_coroutine_threadsafeë¡??œìŠ¤?¬ë? ?±ë¡.
    """
    global _service_loop, _service_thread, _service_task
    try:
        # ?„ì¬ ?¤í–‰ì¤‘ì¸ ë£¨í”„ ?•ì¸
        loop = asyncio.get_running_loop()
        loop_running_here = True
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop_running_here = False

    if loop_running_here:
        # ê°™ì? ë£¨í”„/?¤ë ˆ?œì—???¤í–‰ ì¤‘ì´ë©?create_taskë¡??¤í–‰
        if _service_task and getattr(_service_task, "done", lambda: False)():
            logger.info("[gap_service] ê¸°ì¡´ ?œë¹„???œìŠ¤?¬ê? ?¤í–‰ ì¤‘ì…?ˆë‹¤.")
            return
        _service_loop = loop
        try:
            _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
            logger.info("[gap_service] GapConsumer ?œìŠ¤?¬ë? ?„ì¬ ?´ë²¤??ë£¨í”„???ì„±?ˆìŠµ?ˆë‹¤.")
        except Exception:
            # ë°©ì–´?? run_coroutine_threadsafeë¡??œë„
            fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
            _service_task = fut
            logger.info("[gap_service] GapConsumer ?œìŠ¤?¬ë? run_coroutine_threadsafeë¡??ì„±?ˆìŠµ?ˆë‹¤.")
    else:
        # ??ë£¨í”„ë¥?ë³„ë„ ?¤ë ˆ?œì—???¤í–‰?˜ê³  ?œìŠ¤?¬ë? ?±ë¡
        _service_loop = loop
        _service_thread = _start_loop_in_thread(loop)
        fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
        _service_task = fut
        logger.info("[gap_service] GapConsumerë¥?ë³„ë„ ?¤ë ˆ???´ë²¤??ë£¨í”„?ì„œ ?¤í–‰?˜ë„ë¡??œì‘?ˆìŠµ?ˆë‹¤.")


async def start_service_async(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    ë¹„ë™ê¸??˜ê²½?ì„œ ?œë¹„???œì‘: awaitë¡??¸ì¶œ.
    """
    global _service_loop, _service_task
    loop = asyncio.get_running_loop()
    _service_loop = loop
    if _service_task and getattr(_service_task, "done", lambda: False)():
        logger.info("[gap_service] ê¸°ì¡´ ?œë¹„???œìŠ¤?¬ê? ?¤í–‰ ì¤‘ì…?ˆë‹¤.")
        return
    _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
    logger.info("[gap_service] ë¹„ë™ê¸?GapConsumer ?œìŠ¤???ì„±")


async def stop_service():
    """
    ?œë¹„???•ì?: consumer.stop() ?¸ì¶œ, task ?€ê¸? ë¦¬ì†Œ???•ë¦¬
    - start_serviceë¡??œì‘??ê²½ìš°?ë„ ??ë¹„ë™ê¸??¨ìˆ˜ë¥??¸ì¶œ?˜ì—¬ ?•ë¦¬?˜ì„¸??
    """
    global _service_task, _service_consumer, _service_redis, _service_pool, _service_loop, _service_thread
    logger.info("[gap_service] ?œë¹„??ì¤‘ì? ?œì‘")
    try:
        if _service_consumer:
            _service_consumer.stop()
        # ?œìŠ¤?¬ê? asyncio.Task??ê²½ìš°
        if isinstance(_service_task, asyncio.Task):
            try:
                await asyncio.wait_for(_service_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[gap_service] ?œë¹„??ì¢…ë£Œ ?€?„ì•„?????œìŠ¤??ì·¨ì†Œ")
                _service_task.cancel()
                try:
                    await _service_task
                except Exception:
                    pass
        else:
            # concurrent.futures.Future (run_coroutine_threadsafe ë°˜í™˜)??ê²½ìš° cancel ?œë„
            if _service_task is not None:
                try:
                    _service_task.cancel()
                except Exception:
                    logger.debug("[gap_service] concurrent future cancel ?¤íŒ¨", exc_info=True)
        # ?ˆì „??Redis/DB ì¢…ë£Œ
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
                logger.debug("[gap_service] redis ?ˆì „ì¢…ë£Œ ì¤??ˆì™¸", exc_info=True)
        if _service_pool:
            try:
                await _service_pool.close()
            except Exception:
                logger.debug("[gap_service] pool close ì¤??ˆì™¸", exc_info=True)
    finally:
        # ë³„ë„ ë£¨í”„/?¤ë ˆ?œë¡œ ?¤í–‰??ê²½ìš° ë£¨í”„ ?•ë¦¬
        if _service_loop and _service_thread:
            try:
                _service_loop.call_soon_threadsafe(_service_loop.stop)
            except Exception:
                logger.debug("[gap_service] ë³„ë„ ë£¨í”„ ?•ì? ?¸ì¶œ ?¤íŒ¨", exc_info=True)
            try:
                _service_thread.join(timeout=5.0)
            except Exception:
                logger.debug("[gap_service] ?œë¹„???¤ë ˆ??join ?¤íŒ¨", exc_info=True)
        # ?íƒœ ì´ˆê¸°??
        _service_task = None
        _service_consumer = None
        _service_redis = None
        _service_pool = None
        _service_loop = None
        _service_thread = None
        logger.info("[gap_service] ?œë¹„??ì¤‘ì? ?„ë£Œ")
