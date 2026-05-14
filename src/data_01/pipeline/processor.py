# -*- coding: utf-8 -*-
"""
PipelineProcessor (v3.1 - 以묒븰 asyncio ?대깽?몃（???꾩엯, ?ㅻ젅???덉쟾 ?ㅼ?以꾨쭅)

蹂寃쎌궗??v3.1 (2026-05-10):
- 以묒븰 asyncio ?대깽??猷⑦봽(loop thread)瑜??꾩엯?섏뿬 紐⑤뱺 鍮꾨룞湲?肄붾（?댁쓣 ?대떦 猷⑦봽?먯꽌 ?ㅽ뻾?섎룄濡??듭씪.
- ?뚯빱 ?ㅻ젅?쒖뿉???덈줈??猷⑦봽瑜?留뚮뱶??諛⑹떇 ?쒓굅 ??asyncio.run_coroutine_threadsafe瑜??ъ슜??以묒븰 猷⑦봽???묒뾽 ?쒖텧.
- Stager/Finalizer 二쇨린??flush??以묒븰 猷⑦봽?먯꽌 ?ㅼ?以꾨쭅?섎룄濡?蹂寃?
- WebSocket ?숆린 肄쒕갚(process_candle_sync)? 以묒븰 猷⑦봽??肄붾（?댁쑝濡??쒖텧(?쇰툝濡쒗궧).
- stop/醫낅즺 ??以묒븰 猷⑦봽 ?덉쟾 醫낅즺 濡쒖쭅 異붽?.
- ?대젃寃??섎㈃ "attached to a different loop" ?ㅻ쪟瑜??쒓굅?섍퀬 motor/pymongo ?숈옉 ?덉젙?깆쓣 ?믪엫.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import uuid
import threading
import queue
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Set
from pathlib import Path
import concurrent.futures

logger = logging.getLogger(__name__)

# ============================================================
# ?숈쟻 紐⑤뱢 濡쒕뜑 (?⑦궎吏 import ?ㅽ뙣 ???뚯씪 寃쎈줈 ?대갚)
# ============================================================
def _load_module_by_path(path: Path, name: Optional[str] = None):
    """?뚯씪 寃쎈줈 湲곕컲 紐⑤뱢 濡쒕뜑"""
    try:
        spec = importlib.util.spec_from_file_location(name or path.stem, str(path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception:
        logger.debug("?뚯씪寃쎈줈 紐⑤뱢濡쒕뱶 ?ㅽ뙣: %s", path, exc_info=True)
    return None


# ============================================================
# validator 紐⑤뱢 濡쒕뱶 (?곷? import ?곗꽑, ?뚯씪 寃쎈줈 ?대갚)
# ============================================================
CandleValidator = None
ValidationError = None
GapExceededException = None

try:
    from .validator import (  # type: ignore
        CandleValidator as _CV,
        ValidationError as _VE,
        GapExceededException as _GE,
    )
    CandleValidator = _CV
    ValidationError = _VE
    GapExceededException = _GE
except Exception:
    base = Path(__file__).resolve().parent
    vpath = base / "validator.py"
    mod = _load_module_by_path(vpath, "pipeline_validator_fallback")
    if mod:
        CandleValidator = getattr(mod, "CandleValidator", None)
        ValidationError = getattr(mod, "ValidationError", None)
        GapExceededException = getattr(mod, "GapExceededException", None)
    else:
        CandleValidator = None
        ValidationError = Exception
        GapExceededException = Exception


# ============================================================
# invalid_store 紐⑤뱢 濡쒕뱶 (?뚯씪 寃쎈줈 湲곕컲 ?대갚)
# ============================================================
store_invalid_candle = None

try:
    pkg = importlib.import_module("src.data_01.pipeline.invalid_store")
    store_invalid_candle = getattr(pkg, "store_invalid_candle", None)
except Exception:
    base = Path(__file__).resolve().parent
    is_path = base / "invalid_store.py"
    if is_path.exists():
        m = _load_module_by_path(is_path, "invalid_store")
        store_invalid_candle = getattr(m, "store_invalid_candle", None)

if store_invalid_candle is None:
    def store_invalid_candle(*args, **kwargs):
        """?붾? ?⑥닔 (invalid_store 濡쒕뱶 ?ㅽ뙣 ??"""
        return None


def _now_utc() -> datetime:
    """UTC ?꾩옱 ?쒓컖"""
    return datetime.now(timezone.utc)


# ============================================================
# PipelineProcessor ?대옒??
# ============================================================
class PipelineProcessor:
    """
    Pipeline ?곗씠??泥섎━ ?붿쭊

    ?ㅺ퀎 蹂寃??붿?:
    - 以묒븰 asyncio ?대깽??猷⑦봽瑜?蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾(run_forever).
    - 紐⑤뱺 肄붾（?댁? asyncio.run_coroutine_threadsafe瑜??듯빐 以묒븰 猷⑦봽???쒖텧.
    - ?뚯빱 ?ㅻ젅?쒕뒗 以묒븰 猷⑦봽???쒖텧??Future.result(timeout=...)濡??숆린 ?湲고븯嫄곕굹 ?쇰툝濡쒗궧?쇰줈 諛섑솚.
    """

    def __init__(
        self,
        validator: Optional[Any] = None,
        stager: Optional[Any] = None,
        finalizer: Optional[Any] = None,
        writer: Optional[Any] = None,
        isolator: Optional[Any] = None,
        metadata: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        kafka_producer: Optional[Any] = None,
        concurrency: int = 32,
        publish_to_redis: bool = True,
        publish_to_kafka: bool = False,
        redis_channel_tpl: str = "market:ticker:{symbol}",
        kafka_topic_tpl: str = "market.raw.candle.{timeframe}",
        queue_maxsize: int = 50000,
    ) -> None:
        # 而댄룷?뚰듃
        self.validator = validator or (CandleValidator() if CandleValidator else None)
        self.stager = stager
        self.finalizer = finalizer
        self.writer = writer
        self.isolator = isolator
        self.metadata = metadata
        self.redis = redis_client
        self.kafka = kafka_producer

        # ?숈떆???쒖뼱
        self._concurrency = concurrency
        self._sem: Optional[asyncio.Semaphore] = None
        self._sem_loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: Set[asyncio.Task] = set()
        self._running = False

        # 以묒븰 asyncio 猷⑦봽 (蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        # ?쇰툝由ъ떛 ?ㅼ젙
        self.publish_to_redis = publish_to_redis
        self.publish_to_kafka = publish_to_kafka
        self.redis_channel_tpl = redis_channel_tpl
        self.kafka_topic_tpl = kafka_topic_tpl

        # REST API???숆린 ??
        self._queue: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self._workers: list = []

        # ?듦퀎 移댁슫??
        self._stats = {
            "total_received": 0,
            "total_processed": 0,
            "total_errors": 0,
            "queue_size": 0,
        }

        # 泥섎━ ?꾨즺 肄쒕갚 紐⑸줉 (QPS 移댁슫?????몃? 紐⑤땲?곕쭅??
        self._on_processed_callbacks: list = []

        # ?대? ?숆린 fut timeout (?뚯빱媛 以묒븰 猷⑦봽?먯꽌 ?ㅽ뻾???쒖뒪??寃곌낵瑜?湲곕떎由???
        self._worker_task_timeout = 30.0  # seconds

    def add_on_processed(self, callback) -> None:
        """泥섎━ ?꾨즺 肄쒕갚 ?깅줉."""
        if callable(callback) and callback not in self._on_processed_callbacks:
            self._on_processed_callbacks.append(callback)

    def _fire_on_processed(self, symbol: str, timeframe: str, candle: dict) -> None:
        """?깅줉??泥섎━ ?꾨즺 肄쒕갚??紐⑤몢 ?몄텧?⑸땲??(?덉쇅 臾댁떆)."""
        for cb in list(self._on_processed_callbacks):
            try:
                cb(symbol, timeframe, candle)
            except Exception as _cb_exc:
                logger.debug("[Pipeline] on_processed 肄쒕갚 ?먮윭: %s", _cb_exc)

    # ============================================================
    # 以묒븰 猷⑦봽 愿由?
    # ============================================================
    def _ensure_loop_thread(self) -> None:
        """以묒븰 asyncio ?대깽??猷⑦봽? 猷⑦봽 ?ㅻ젅?쒕? 珥덇린???대? ?덉쓣 寃쎌슦 臾댁떆)."""
        if self._loop is not None and self._loop_thread is not None and self._loop_thread.is_alive():
            return

        # ???대깽??猷⑦봽 ?앹꽦 諛??ㅻ젅???쒖옉
        loop = asyncio.new_event_loop()

        def _run_loop():
            try:
                asyncio.set_event_loop(loop)
                logger.info("[Pipeline] 以묒븰 asyncio 猷⑦봽 ?쒖옉 (蹂꾨룄 ?ㅻ젅??")
                loop.run_forever()
            except Exception as exc:
                logger.exception("[Pipeline] 以묒븰 ?대깽??猷⑦봽 ?ㅽ뻾 以??덉쇅: %s", exc)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
                logger.info("[Pipeline] 以묒븰 asyncio 猷⑦봽 醫낅즺")

        t = threading.Thread(target=_run_loop, name="PipelineAsyncLoopThread", daemon=True)
        t.start()

        self._loop = loop
        self._loop_thread = t

    def _stop_loop_thread(self) -> None:
        """以묒븰 ?대깽??猷⑦봽瑜??덉쟾??以묒??섍퀬 ?ㅻ젅?쒕? 議곗씤?⑸땲??"""
        if self._loop is None or self._loop_thread is None:
            return
        try:
            loop = self._loop
            # ?붿껌 ?ㅻ젅?쒖뿉 ?덉쟾?섍쾶 以묒? 肄?
            def _stop():
                try:
                    loop.stop()
                except Exception:
                    pass

            loop.call_soon_threadsafe(_stop)
            # 猷⑦봽 ?ㅻ젅?쒓? 醫낅즺???뚭퉴吏 ?湲?吏㏃? ??꾩븘??
            self._loop_thread.join(timeout=5.0)
        except Exception as exc:
            logger.debug("[Pipeline] 以묒븰 猷⑦봽 ?뺤? ?ㅽ뙣: %s", exc)
        finally:
            self._loop = None
            self._loop_thread = None

    # ============================================================
    # ?쒖옉/醫낅즺
    # ============================================================
    def start(self) -> None:
        """Pipeline ?쒖옉 (?숆린)"""
        if self._running:
            logger.warning("[Pipeline] ?대? ?ㅽ뻾 以묒엯?덈떎")
            return

        self._running = True

        logger.info(
            "[Pipeline] ?? ?쒖옉 (concurrency=%d, queue_maxsize=%d)",
            self._concurrency,
            self._queue.maxsize,
        )

        # 以묒븰 asyncio 猷⑦봽 蹂댁옣(紐⑤뱺 鍮꾨룞湲??묒뾽? ??猷⑦봽?먯꽌 ?ㅽ뻾)
        try:
            self._ensure_loop_thread()
        except Exception as exc:
            logger.warning("[Pipeline] 以묒븰 猷⑦봽 珥덇린???ㅽ뙣: %s", exc)

        # Worker ?ㅻ젅???쒖옉 (REST 泥섎━)
        for i in range(self._concurrency):
            thread = threading.Thread(
                target=self._worker,
                name=f"PipelineWorker-{i}",
                daemon=True,
            )
            thread.start()
            self._workers.append(thread)
            logger.info("[Pipeline] ?뚯빱 ?ㅻ젅???쒖옉: %s", thread.name)

        logger.info("[Pipeline] ??%d媛??뚯빱 ?ㅻ젅???쒖옉 ?꾨즺", len(self._workers))

        # Stager/Finalizer 二쇨린??flush??以묒븰 猷⑦봽???ㅼ?以?
        self._start_stager_flush()
        self._start_finalizer_flush()

    def _start_stager_flush(self) -> None:
        """Stager 二쇨린??flush ?쒖옉 (以묒븰 猷⑦봽?먯꽌 肄붾（?댁쑝濡??ㅼ?以?"""
        if self.stager and hasattr(self.stager, "start_periodic_flush"):
            try:
                if self._loop is None:
                    self._ensure_loop_thread()
                # ?ㅼ?以?coroutine) ?쒖텧 (鍮꾨룞湲??ㅽ뻾)
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.stager.start_periodic_flush(interval_seconds=30),
                        self._loop,
                    )
                    # don't block here; the periodic flush coroutine can run in background
                    logger.info("[Pipeline] ??Stager 二쇨린??flush ?ㅼ?以??붿껌 ??)
                except Exception as e:
                    logger.error("[Pipeline] Stager flush ?ㅼ?以??ㅽ뙣: %s", e)
            except Exception as e:
                logger.warning("[Pipeline] Stager 二쇨린??flush ?쒖옉 ?ㅽ뙣: %s", e)

    def _start_finalizer_flush(self) -> None:
        """Finalizer 二쇨린??flush ?쒖옉 (以묒븰 猷⑦봽?먯꽌 肄붾（?댁쑝濡??ㅼ?以?"""
        if self.finalizer and hasattr(self.finalizer, "start_periodic_flush"):
            try:
                if self._loop is None:
                    self._ensure_loop_thread()
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.finalizer.start_periodic_flush(),
                        self._loop,
                    )
                    logger.info("[Pipeline] ??Finalizer 二쇨린??flush ?ㅼ?以??붿껌 ??)
                except Exception as e:
                    logger.error("[Pipeline] Finalizer flush ?ㅼ?以??ㅽ뙣: %s", e)
            except Exception as e:
                logger.warning("[Pipeline] Finalizer 二쇨린??flush ?쒖옉 ?ㅽ뙣: %s", e)

    async def stop(self) -> None:
        """Pipeline 醫낅즺 (鍮꾨룞湲?"""
        self._running = False

        # ?뚯빱 ?ㅻ젅?쒓? ?먮? 鍮꾩슦?꾨줉 ?좎떆 ?湲?
        try:
            # ?⑥? ?쒖뒪???湲?(以묒븰 猷⑦봽???쒖뒪??
            if self._tasks:
                logger.info("[Pipeline] ?⑥? ?쒖뒪???湲? %d", len(self._tasks))
                # 鍮꾨룞湲??섍꼍?먯꽌 ?湲?
                await asyncio.wait(self._tasks, timeout=10.0)
        except Exception as exc:
            logger.warning("[Pipeline] 醫낅즺 ???쒖뒪???湲?以??ㅻ쪟: %s", exc)

        # 理쒖쥌 flush: 以묒븰 猷⑦봽?먯꽌 ?ㅽ뻾
        try:
            if self._loop is not None:
                # schedule flush coroutines on central loop and wait
                futs = []
                if self.stager:
                    try:
                        f = asyncio.run_coroutine_threadsafe(self.stager.flush(), self._loop)
                        futs.append(f)
                    except Exception:
                        pass
                if self.writer and hasattr(self.writer, "flush"):
                    try:
                        f = asyncio.run_coroutine_threadsafe(self.writer.flush(), self._loop)
                        futs.append(f)
                    except Exception:
                        pass
                if self.finalizer and hasattr(self.finalizer, "stop_periodic_flush"):
                    try:
                        f = asyncio.run_coroutine_threadsafe(self.finalizer.stop_periodic_flush(), self._loop)
                        futs.append(f)
                    except Exception:
                        pass
                # wait for futures (sync wait)
                for f in futs:
                    try:
                        f.result(timeout=10.0)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("[Pipeline] 醫낅즺 ??flush 以??ㅻ쪟: %s", exc)

        # 以묒븰 猷⑦봽 ?뺤?
        try:
            self._stop_loop_thread()
        except Exception as exc:
            logger.debug("[Pipeline] 以묒븰 猷⑦봽 ?뺤? ?ㅽ뙣: %s", exc)

    # ============================================================
    # REST API???숆린 enqueue 硫붿꽌??
    # ============================================================
    def enqueue(self, candle: dict) -> None:
        """?숆린?곸쑝濡?罹붾뱾???먯뿉 異붽? (REST API?먯꽌 ?몄텧)"""
        if not self._running:
            logger.info("[Pipeline] ?? enqueue() 理쒖큹 ?몄텧 - ?뚯빱 ?ㅻ젅???먮룞 ?쒖옉")
            self.start()

        logger.debug(
            "[Pipeline] ?뱿 enqueue() ?몄텧: %s %s (time=%s)",
            candle.get("symbol"),
            candle.get("timeframe"),
            candle.get("time"),
        )

        try:
            self._queue.put_nowait(candle)
            self._stats["total_received"] += 1
            self._stats["queue_size"] = self._queue.qsize()

            logger.debug(
                "[Pipeline] ????異붽? ?깃났 (???ш린: %d, ?꾩쟻 ?섏떊: %d)",
                self._stats["queue_size"],
                self._stats["total_received"],
            )
        except queue.Full:
            logger.error(
                "[Pipeline] ???먭? 媛??李쇱뒿?덈떎! (max_size=%d) - 罹붾뱾 踰꾨┝: %s",
                self._queue.maxsize,
                candle.get("symbol"),
            )
            self._stats["total_errors"] += 1
        except Exception as exc:
            logger.error(
                "[Pipeline] ??enqueue ?ㅽ뙣: %s (罹붾뱾: %s)",
                exc,
                candle.get("symbol"),
            )
            self._stats["total_errors"] += 1

    # ============================================================
    # WebSocket???숆린 肄쒕갚 硫붿꽌??
    # ============================================================
    def process_candle_sync(self, candle: dict) -> None:
        """
        ?숆린 罹붾뱾 泥섎━ (WebSocket 肄쒕갚??

        WebSocket?먯꽌 ?숆린 ?⑥닔濡??몄텧?섎?濡?
        以묒븰 ?대깽??猷⑦봽??鍮꾨룞湲??묒뾽???ㅼ?以꾨쭅(?쇰툝濡쒗궧)?⑸땲??
        """
        self._stats["total_received"] += 1

        try:
            if self._loop is None:
                self._ensure_loop_thread()

            # submit coroutine to central loop (non-blocking)
            try:
                asyncio.run_coroutine_threadsafe(self.process_candle(candle), self._loop)
            except Exception as exc:
                self._stats["total_errors"] += 1
                logger.error("[Pipeline] ?숆린 肄쒕갚 泥섎━ ?ㅽ뙣 (?ㅼ?以?: %s", exc, exc_info=True)

            # 1000媛쒕쭏?ㅻ쭔 INFO 濡쒓렇 (?곕???異쒕젰 理쒖냼??
            if self._stats["total_received"] % 1000 == 0:
                logger.info(
                    "[Pipeline] ?꾩쟻 ?섏떊: %d媛?(泥섎━: %d, ?먮윭: %d)",
                    self._stats["total_received"],
                    self._stats["total_processed"],
                    self._stats["total_errors"],
                )
        except Exception as exc:
            self._stats["total_errors"] += 1
            logger.error("[Pipeline] ?숆린 肄쒕갚 泥섎━ ?ㅽ뙣: %s", exc, exc_info=True)

    # ============================================================
    # ?뚯빱 ?ㅻ젅??(REST API 罹붾뱾 泥섎━)
    # ============================================================
    def _worker(self) -> None:
        """?뚯빱 ?ㅻ젅??(REST API 罹붾뱾 泥섎━)"""
        thread_name = threading.current_thread().name
        logger.info("[Pipeline] ?뚯빱 ?ㅻ젅???쒖옉: %s", thread_name)

        while self._running:
            try:
                try:
                    candle = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                logger.debug(
                    "[Pipeline] ?뵩 ?뚯빱(%s) 泥섎━ ?쒖옉: %s %s (time=%s)",
                    thread_name,
                    candle.get("symbol"),
                    candle.get("timeframe"),
                    candle.get("time"),
                )

                # Submit the processing coroutine to the central loop and wait for result
                if self._loop is None:
                    self._ensure_loop_thread()

                try:
                    future = asyncio.run_coroutine_threadsafe(self._process_task(candle), self._loop)
                    # Block waiting for result up to timeout, so worker behaves synchronously
                    try:
                        future.result(timeout=self._worker_task_timeout)
                        logger.debug(
                            "[Pipeline] ???뚯빱(%s) 泥섎━ ?꾨즺: %s",
                            thread_name,
                            candle.get("symbol"),
                        )
                    except concurrent.futures.TimeoutError:
                        logger.warning("[Pipeline] ?뚯빱(%s) 泥섎━ ??꾩븘?? %s", thread_name, candle.get("symbol"))
                        # let task continue in central loop; worker moves on
                    except Exception as exc:
                        logger.error(
                            "[Pipeline] ???뚯빱(%s) 泥섎━ ?ㅽ뙣: %s (symbol=%s)",
                            thread_name,
                            exc,
                            candle.get("symbol"),
                            exc_info=True,
                        )
                        self._stats["total_errors"] += 1
                except Exception as exc:
                    logger.error("[Pipeline] ?뚯빱 ?쒖텧 ?ㅽ뙣: %s", exc, exc_info=True)
                    self._stats["total_errors"] += 1
                finally:
                    try:
                        self._queue.task_done()
                    except Exception:
                        pass

            except Exception as exc:
                logger.error(
                    "[Pipeline] ???뚯빱(%s) 猷⑦봽 ?먮윭: %s",
                    thread_name,
                    exc,
                    exc_info=True,
                )

        logger.info("[Pipeline] ?뚯빱 ?ㅻ젅??醫낅즺: %s", thread_name)

    # ============================================================
    # 鍮꾨룞湲?罹붾뱾 泥섎━ (以묒븰 猷⑦봽)
    # ============================================================
    async def process_candle(self, candle: dict) -> None:
        """鍮꾨룞湲?罹붾뱾 泥섎━ (以묒븰 猷⑦봽?먯꽌 ?ㅽ뻾)"""
        if not self._running:
            # NOTE: avoid re-entrant calling of start() from central loop
            pass

        self._standardize_headers(candle)
        logger.debug("[Pipeline] 罹붾뱾 ?섏떊: symbol=%s", candle.get("symbol", ""))

        task = asyncio.create_task(self._process_task(candle))
        self._tasks.add(task)

        def _done_cb(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.exception("[Pipeline] ?쒖뒪???덉쇅: %s", exc)

        task.add_done_callback(_done_cb)

    # ============================================================
    # ?ㅻ뜑 ?쒖???
    # ============================================================
    def _standardize_headers(self, candle: dict) -> None:
        """罹붾뱾 ?ㅻ뜑 ?쒖???(trace_id, ingest_ts, idempotency_key)"""
        if "trace_id" not in candle or not candle.get("trace_id"):
            candle["trace_id"] = str(uuid.uuid4())

        candle["ingest_ts"] = candle.get("ingest_ts") or _now_utc()
        candle.setdefault("schema_version", candle.get("schema_version", "v1"))

        if "idempotency_key" not in candle:
            seq = candle.get("exchange_sequence_id") or candle.get("seq")
            if seq:
                candle["idempotency_key"] = f"{candle.get('symbol','')}/{seq}"
            else:
                t = (
                    candle.get("time")
                    or candle.get("timestamp")
                    or candle.get("_parsed_time")
                )
                if isinstance(t, datetime):
                    t_iso = t.isoformat()
                else:
                    t_iso = str(t)
                candle["idempotency_key"] = f"{candle.get('symbol','')}|{t_iso}"

    # ============================================================
    # ?듭떖 泥섎━ ?쒖뒪??
    # ============================================================
    async def _process_task(self, candle: dict) -> None:
        """?듭떖 泥섎━ ?쒖뒪??(寃利?????????쇰툝由ъ떛)"""
        # Semaphore 珥덇린?붾뒗 以묒븰 猷⑦봽 臾몃㎘?먯꽌 ?섑뻾
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        if self._sem is None or self._sem_loop is not loop:
            self._sem = asyncio.Semaphore(self._concurrency)
            self._sem_loop = loop

        async with self._sem:
            symbol = candle.get("symbol", "")
            timeframe = candle.get("timeframe", candle.get("tf", "1m"))

            try:
                # Step 1: 硫뷀??곗씠??議고쉶
                last_snap_time = await self._get_last_snapshot(symbol, timeframe)

                # Step 2: 寃利?
                validation_result = await self._validate_candle(
                    candle, last_snap_time, symbol
                )
                if not validation_result:
                    return  # 寃利??ㅽ뙣 ??醫낅즺

                # Step 3: ???
                await self._save_candle(candle, symbol)

                # Step 4: 硫뷀??곗씠??媛깆떊
                await self._update_metadata(candle, symbol, timeframe)

                # Step 5: ?쇰툝由ъ떛
                await self._maybe_publish(candle)

                self._stats["total_processed"] += 1

                # 泥섎━ ?꾨즺 肄쒕갚 ?몄텧 (QPS 移댁슫?????몃? 紐⑤땲?곕쭅)
                self._fire_on_processed(symbol, timeframe, candle)

                # 10媛쒕쭏??INFO 濡쒓렇 (REST API 異붿쟻??
                if self._stats["total_processed"] % 10 == 0:
                    logger.info(
                        "[Pipeline] 泥섎━ 吏꾪뻾: %d媛??꾨즺 (?섏떊: %d, ?먮윭: %d)",
                        self._stats["total_processed"],
                        self._stats["total_received"],
                        self._stats["total_errors"],
                    )

            except Exception as exc:
                logger.exception("[Pipeline] 泥섎━ 以??덉쇅 諛쒖깮: %s", exc)
                self._stats["total_errors"] += 1

    # ============================================================
    # 硫뷀?/寃利?????쇰툝由ъ떆 ??蹂댁“ 硫붿꽌??(湲곗〈 肄붾뱶 ?좎?)
    # ============================================================
    async def _get_last_snapshot(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """硫뷀??곗씠?곗뿉??留덉?留??ㅻ깄??議고쉶"""
        logger.debug("[Pipeline] 泥섎━ ?④퀎 1: 硫뷀??곗씠??議고쉶 (symbol=%s)", symbol)
        last_snap_time = None
        if self.metadata:
            try:
                last_snap_time = await self.metadata.get_snapshot(symbol, timeframe)
                logger.debug("?ㅻ깄??議고쉶 ?깃났: %s = %s", symbol, last_snap_time)
            except Exception as exc:
                logger.debug("?ㅻ깄??議고쉶 ?ㅽ뙣(臾댁떆): %s", exc)
        return last_snap_time

    async def _validate_candle(self, candle: dict, last_snap_time: Optional[datetime], symbol: str) -> bool:
        """罹붾뱾 寃利?(Validator ?몄텧)"""
        logger.debug("[Pipeline] 泥섎━ ?④퀎 2: 寃利?(symbol=%s)", symbol)
        try:
            if self.validator:
                self.validator.validate(candle, last_time=last_snap_time)
                logger.debug("[Pipeline] 寃利??듦낵: symbol=%s", symbol)
            else:
                logger.debug("Validator 誘몄꽕??- 寃利??ㅽ궢")
            return True

        except GapExceededException as exc:
            logger.warning(
                "[Pipeline] Gap 媛먯? (怨꾩냽 ???: symbol=%s reason=%s",
                symbol,
                str(exc),
            )
            return True

        except (ValidationError,) as exc:
            reason = str(exc)
            logger.info("[Pipeline] ??寃利??ㅽ뙣: symbol=%s reason=%s", symbol, reason)
            try:
                preserved = {
                    "symbol": candle.get("symbol"),
                    "time": candle.get("time"),
                    "candle": (candle.copy() if isinstance(candle, dict) else {"value": str(candle)}),
                    "reason": reason,
                }
                store_invalid_candle(preserved, reason)
            except Exception:
                logger.debug("pipeline invalid_store ????ㅽ뙣(臾댁떆)", exc_info=True)

            if self.isolator:
                try:
                    await self.isolator.handle(candle, exc)
                    logger.info("[Pipeline] ??Isolator 泥섎━ ?꾨즺: symbol=%s", symbol)
                except Exception as ie:
                    logger.error("[Pipeline] isolator 泥섎━ ?ㅽ뙣: %s", ie)

            self._stats["total_errors"] += 1
            return False

    async def _save_candle(self, candle: dict, symbol: str) -> None:
        """罹붾뱾 ???(Stager/Finalizer/Writer)"""
        logger.debug("[Pipeline] 泥섎━ ?④퀎 3: ???(symbol=%s)", symbol)
        try:
            if self.stager and hasattr(self.stager, "add_candle"):
                await self.stager.add_candle(candle)
                logger.debug("[Pipeline] Staging ????꾨즺: symbol=%s", symbol)
            elif self.finalizer and hasattr(self.finalizer, "upsert_candle"):
                await self.finalizer.upsert_candle(candle)
                logger.debug("[Pipeline] Finalizer ????꾨즺: symbol=%s", symbol)
            elif self.writer and hasattr(self.writer, "upsert"):
                await self.writer.upsert(candle)
                logger.debug("[Pipeline] Writer ????꾨즺: symbol=%s", symbol)
            else:
                logger.warning("??μ냼 ?놁쓬: stager/finalizer/writer 以??섎굹 ?꾩슂")
        except Exception as exc:
            logger.error("???以??ㅻ쪟, isolator濡??닿?: %s", exc, exc_info=True)
            if self.isolator:
                await self.isolator.handle(candle, exc)
            self._stats["total_errors"] += 1
            raise

    async def _update_metadata(self, candle: dict, symbol: str, timeframe: str) -> None:
        """硫뷀??곗씠??媛깆떊"""
        logger.debug("[Pipeline] ?뵇 泥섎━ ?④퀎 4: 硫뷀??곗씠??媛깆떊 (symbol=%s)", symbol)
        try:
            parsed_time = (
                candle.get("_parsed_time")
                or candle.get("time")
                or candle.get("timestamp")
            )
            if parsed_time and not isinstance(parsed_time, datetime):
                try:
                    parsed_time = datetime.fromisoformat(str(parsed_time))
                except Exception:
                    parsed_time = None

            if parsed_time and self.metadata:
                if getattr(parsed_time, "tzinfo", None) is None:
                    parsed_time = parsed_time.replace(tzinfo=timezone.utc)
                await self.metadata.update_snapshot_if_new(symbol, timeframe, parsed_time)
        except Exception as exc:
            logger.warning("硫뷀? 媛깆떊 ?ㅽ뙣(臾댁떆): %s", exc)

    async def _maybe_publish(self, candle: dict) -> None:
        """Redis/Kafka ?쇰툝由ъ떛"""
        payload = None
        try:
            payload = json.dumps(candle, default=str)
        except Exception:
            payload = str(candle)

        # Redis ?쇰툝由ъ떛
        if self.publish_to_redis and self.redis:
            try:
                channel = self.redis_channel_tpl.format(
                    symbol=candle.get("symbol", ""),
                    timeframe=candle.get("timeframe", "1m"),
                )
                publish_fn = getattr(self.redis, "publish", None)
                if publish_fn:
                    res = publish_fn(channel, payload)
                    if asyncio.iscoroutine(res):
                        await res
                else:
                    try:
                        res = self.redis.publish(channel, payload)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.debug("Redis publish ?덉쇅(fallback): %s", e)
            except Exception as exc:
                logger.debug("Redis publish ?ㅽ뙣(臾댁떆): %s", exc)

        # Kafka ?쇰툝由ъ떛
        if self.publish_to_kafka and self.kafka:
            try:
                topic = self.kafka_topic_tpl.format(
                    timeframe=candle.get("timeframe", "1m")
                )
                key = (candle.get("symbol") or "").encode("utf-8")
                send_fn = getattr(self.kafka, "send_and_wait", None) or getattr(
                    self.kafka, "send", None
                )
                if send_fn:
                    value = (
                        payload.encode("utf-8") if isinstance(payload, str) else payload
                    )
                    res = send_fn(topic, value, key=key)
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as exc:
                logger.debug("Kafka produce ?ㅽ뙣(臾댁떆): %s", exc)

    # ============================================================
    # ?듦퀎 議고쉶 硫붿꽌??(UI 紐⑤땲?곕쭅??
    # ============================================================
    def get_stats(self) -> dict:
        """Pipeline 泥섎━ ?듦퀎 諛섑솚"""
        return {
            "total_received": self._stats["total_received"],
            "total_processed": self._stats["total_processed"],
            "total_errors": self._stats["total_errors"],
            "queue_size": self._stats["queue_size"],
            "success_rate": (
                self._stats["total_processed"]
                / max(self._stats["total_received"], 1)
                * 100
            ),
        }
