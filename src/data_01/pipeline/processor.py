# -*- coding: utf-8 -*-
"""
PipelineProcessor (v3.1 - 중앙 asyncio 이벤트루프 도입, 스레드 안전 스케줄링)

변경사항 v3.1 (2026-05-10):
- 중앙 asyncio 이벤트 루프(loop thread)를 도입하여 모든 비동기 코루틴을 해당 루프에서 실행하도록 통일.
- 워커 스레드에서 새로운 루프를 만드는 방식 제거 → asyncio.run_coroutine_threadsafe를 사용해 중앙 루프에 작업 제출.
- Stager/Finalizer 주기적 flush는 중앙 루프에서 스케줄링하도록 변경.
- WebSocket 동기 콜백(process_candle_sync)은 중앙 루프에 코루틴으로 제출(논블로킹).
- stop/종료 시 중앙 루프 안전 종료 로직 추가.
- 이렇게 하면 "attached to a different loop" 오류를 제거하고 motor/pymongo 동작 안정성을 높임.
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
# 동적 모듈 로더 (패키지 import 실패 시 파일 경로 폴백)
# ============================================================
def _load_module_by_path(path: Path, name: Optional[str] = None):
    """파일 경로 기반 모듈 로더"""
    try:
        spec = importlib.util.spec_from_file_location(name or path.stem, str(path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception:
        logger.debug("파일경로 모듈로드 실패: %s", path, exc_info=True)
    return None


# ============================================================
# validator 모듈 로드 (상대 import 우선, 파일 경로 폴백)
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
# invalid_store 모듈 로드 (파일 경로 기반 폴백)
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
        """더미 함수 (invalid_store 로드 실패 시)"""
        return None


def _now_utc() -> datetime:
    """UTC 현재 시각"""
    return datetime.now(timezone.utc)


# ============================================================
# PipelineProcessor 클래스
# ============================================================
class PipelineProcessor:
    """
    Pipeline 데이터 처리 엔진

    설계 변경 요지:
    - 중앙 asyncio 이벤트 루프를 별도 스레드에서 실행(run_forever).
    - 모든 코루틴은 asyncio.run_coroutine_threadsafe를 통해 중앙 루프에 제출.
    - 워커 스레드는 중앙 루프에 제출한 Future.result(timeout=...)로 동기 대기하거나 논블로킹으로 반환.
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
        # 컴포넌트
        self.validator = validator or (CandleValidator() if CandleValidator else None)
        self.stager = stager
        self.finalizer = finalizer
        self.writer = writer
        self.isolator = isolator
        self.metadata = metadata
        self.redis = redis_client
        self.kafka = kafka_producer

        # 동시성 제어
        self._concurrency = concurrency
        self._sem: Optional[asyncio.Semaphore] = None
        self._sem_loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: Set[asyncio.Task] = set()
        self._running = False

        # 중앙 asyncio 루프 (별도 스레드에서 실행)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        # 퍼블리싱 설정
        self.publish_to_redis = publish_to_redis
        self.publish_to_kafka = publish_to_kafka
        self.redis_channel_tpl = redis_channel_tpl
        self.kafka_topic_tpl = kafka_topic_tpl

        # REST API용 동기 큐
        self._queue: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self._workers: list = []

        # 통계 카운터
        self._stats = {
            "total_received": 0,
            "total_processed": 0,
            "total_errors": 0,
            "queue_size": 0,
        }

        # 처리 완료 콜백 목록 (QPS 카운팅 등 외부 모니터링용)
        self._on_processed_callbacks: list = []

        # 내부 동기 fut timeout (워커가 중앙 루프에서 실행한 태스크 결과를 기다릴 때)
        self._worker_task_timeout = 30.0  # seconds

    def add_on_processed(self, callback) -> None:
        """처리 완료 콜백 등록."""
        if callable(callback) and callback not in self._on_processed_callbacks:
            self._on_processed_callbacks.append(callback)

    def _fire_on_processed(self, symbol: str, timeframe: str, candle: dict) -> None:
        """등록된 처리 완료 콜백을 모두 호출합니다 (예외 무시)."""
        for cb in list(self._on_processed_callbacks):
            try:
                cb(symbol, timeframe, candle)
            except Exception as _cb_exc:
                logger.debug("[Pipeline] on_processed 콜백 에러: %s", _cb_exc)

    # ============================================================
    # 중앙 루프 관리
    # ============================================================
    def _ensure_loop_thread(self) -> None:
        """중앙 asyncio 이벤트 루프와 루프 스레드를 초기화(이미 있을 경우 무시)."""
        if self._loop is not None and self._loop_thread is not None and self._loop_thread.is_alive():
            return

        # 새 이벤트 루프 생성 및 스레드 시작
        loop = asyncio.new_event_loop()

        def _run_loop():
            try:
                asyncio.set_event_loop(loop)
                logger.info("[Pipeline] 중앙 asyncio 루프 시작 (별도 스레드)")
                loop.run_forever()
            except Exception as exc:
                logger.exception("[Pipeline] 중앙 이벤트 루프 실행 중 예외: %s", exc)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
                logger.info("[Pipeline] 중앙 asyncio 루프 종료")

        t = threading.Thread(target=_run_loop, name="PipelineAsyncLoopThread", daemon=True)
        t.start()

        self._loop = loop
        self._loop_thread = t

    def _stop_loop_thread(self) -> None:
        """중앙 이벤트 루프를 안전히 중지하고 스레드를 조인합니다."""
        if self._loop is None or self._loop_thread is None:
            return
        try:
            loop = self._loop
            # 요청 스레드에 안전하게 중지 콜
            def _stop():
                try:
                    loop.stop()
                except Exception:
                    pass

            loop.call_soon_threadsafe(_stop)
            # 루프 스레드가 종료될 때까지 대기(짧은 타임아웃)
            self._loop_thread.join(timeout=5.0)
        except Exception as exc:
            logger.debug("[Pipeline] 중앙 루프 정지 실패: %s", exc)
        finally:
            self._loop = None
            self._loop_thread = None

    # ============================================================
    # 시작/종료
    # ============================================================
    def start(self) -> None:
        """Pipeline 시작 (동기)"""
        if self._running:
            logger.warning("[Pipeline] 이미 실행 중입니다")
            return

        self._running = True

        logger.info(
            "[Pipeline] 🚀 시작 (concurrency=%d, queue_maxsize=%d)",
            self._concurrency,
            self._queue.maxsize,
        )

        # 중앙 asyncio 루프 보장(모든 비동기 작업은 이 루프에서 실행)
        try:
            self._ensure_loop_thread()
        except Exception as exc:
            logger.warning("[Pipeline] 중앙 루프 초기화 실패: %s", exc)

        # Worker 스레드 시작 (REST 처리)
        for i in range(self._concurrency):
            thread = threading.Thread(
                target=self._worker,
                name=f"PipelineWorker-{i}",
                daemon=True,
            )
            thread.start()
            self._workers.append(thread)
            logger.info("[Pipeline] 워커 스레드 시작: %s", thread.name)

        logger.info("[Pipeline] ✅ %d개 워커 스레드 시작 완료", len(self._workers))

        # Stager/Finalizer 주기적 flush는 중앙 루프에 스케줄
        self._start_stager_flush()
        self._start_finalizer_flush()

    def _start_stager_flush(self) -> None:
        """Stager 주기적 flush 시작 (중앙 루프에서 코루틴으로 스케줄)"""
        if self.stager and hasattr(self.stager, "start_periodic_flush"):
            try:
                if self._loop is None:
                    self._ensure_loop_thread()
                # 스케줄(coroutine) 제출 (비동기 실행)
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.stager.start_periodic_flush(interval_seconds=30),
                        self._loop,
                    )
                    # don't block here; the periodic flush coroutine can run in background
                    logger.info("[Pipeline] ✅ Stager 주기적 flush 스케줄 요청 됨")
                except Exception as e:
                    logger.error("[Pipeline] Stager flush 스케줄 실패: %s", e)
            except Exception as e:
                logger.warning("[Pipeline] Stager 주기적 flush 시작 실패: %s", e)

    def _start_finalizer_flush(self) -> None:
        """Finalizer 주기적 flush 시작 (중앙 루프에서 코루틴으로 스케줄)"""
        if self.finalizer and hasattr(self.finalizer, "start_periodic_flush"):
            try:
                if self._loop is None:
                    self._ensure_loop_thread()
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.finalizer.start_periodic_flush(),
                        self._loop,
                    )
                    logger.info("[Pipeline] ✅ Finalizer 주기적 flush 스케줄 요청 됨")
                except Exception as e:
                    logger.error("[Pipeline] Finalizer flush 스케줄 실패: %s", e)
            except Exception as e:
                logger.warning("[Pipeline] Finalizer 주기적 flush 시작 실패: %s", e)

    async def stop(self) -> None:
        """Pipeline 종료 (비동기)"""
        self._running = False

        # 워커 스레드가 큐를 비우도록 잠시 대기
        try:
            # 남은 태스크 대기 (중앙 루프의 태스크)
            if self._tasks:
                logger.info("[Pipeline] 남은 태스크 대기: %d", len(self._tasks))
                # 비동기 환경에서 대기
                await asyncio.wait(self._tasks, timeout=10.0)
        except Exception as exc:
            logger.warning("[Pipeline] 종료 시 태스크 대기 중 오류: %s", exc)

        # 최종 flush: 중앙 루프에서 실행
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
            logger.warning("[Pipeline] 종료 시 flush 중 오류: %s", exc)

        # 중앙 루프 정지
        try:
            self._stop_loop_thread()
        except Exception as exc:
            logger.debug("[Pipeline] 중앙 루프 정지 실패: %s", exc)

    # ============================================================
    # REST API용 동기 enqueue 메서드
    # ============================================================
    def enqueue(self, candle: dict) -> None:
        """동기적으로 캔들을 큐에 추가 (REST API에서 호출)"""
        if not self._running:
            logger.info("[Pipeline] 🚀 enqueue() 최초 호출 - 워커 스레드 자동 시작")
            self.start()

        logger.debug(
            "[Pipeline] 📥 enqueue() 호출: %s %s (time=%s)",
            candle.get("symbol"),
            candle.get("timeframe"),
            candle.get("time"),
        )

        try:
            self._queue.put_nowait(candle)
            self._stats["total_received"] += 1
            self._stats["queue_size"] = self._queue.qsize()

            logger.debug(
                "[Pipeline] ✅ 큐 추가 성공 (큐 크기: %d, 누적 수신: %d)",
                self._stats["queue_size"],
                self._stats["total_received"],
            )
        except queue.Full:
            logger.error(
                "[Pipeline] ❌ 큐가 가득 찼습니다! (max_size=%d) - 캔들 버림: %s",
                self._queue.maxsize,
                candle.get("symbol"),
            )
            self._stats["total_errors"] += 1
        except Exception as exc:
            logger.error(
                "[Pipeline] ❌ enqueue 실패: %s (캔들: %s)",
                exc,
                candle.get("symbol"),
            )
            self._stats["total_errors"] += 1

    # ============================================================
    # WebSocket용 동기 콜백 메서드
    # ============================================================
    def process_candle_sync(self, candle: dict) -> None:
        """
        동기 캔들 처리 (WebSocket 콜백용)

        WebSocket에서 동기 함수로 호출되므로,
        중앙 이벤트 루프에 비동기 작업을 스케줄링(논블로킹)합니다.
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
                logger.error("[Pipeline] 동기 콜백 처리 실패 (스케줄): %s", exc, exc_info=True)

            # 1000개마다만 INFO 로그 (터미널 출력 최소화)
            if self._stats["total_received"] % 1000 == 0:
                logger.info(
                    "[Pipeline] 누적 수신: %d개 (처리: %d, 에러: %d)",
                    self._stats["total_received"],
                    self._stats["total_processed"],
                    self._stats["total_errors"],
                )
        except Exception as exc:
            self._stats["total_errors"] += 1
            logger.error("[Pipeline] 동기 콜백 처리 실패: %s", exc, exc_info=True)

    # ============================================================
    # 워커 스레드 (REST API 캔들 처리)
    # ============================================================
    def _worker(self) -> None:
        """워커 스레드 (REST API 캔들 처리)"""
        thread_name = threading.current_thread().name
        logger.info("[Pipeline] 워커 스레드 시작: %s", thread_name)

        while self._running:
            try:
                try:
                    candle = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                logger.debug(
                    "[Pipeline] 🔧 워커(%s) 처리 시작: %s %s (time=%s)",
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
                            "[Pipeline] ✅ 워커(%s) 처리 완료: %s",
                            thread_name,
                            candle.get("symbol"),
                        )
                    except concurrent.futures.TimeoutError:
                        logger.warning("[Pipeline] 워커(%s) 처리 타임아웃: %s", thread_name, candle.get("symbol"))
                        # let task continue in central loop; worker moves on
                    except Exception as exc:
                        logger.error(
                            "[Pipeline] ❌ 워커(%s) 처리 실패: %s (symbol=%s)",
                            thread_name,
                            exc,
                            candle.get("symbol"),
                            exc_info=True,
                        )
                        self._stats["total_errors"] += 1
                except Exception as exc:
                    logger.error("[Pipeline] 워커 제출 실패: %s", exc, exc_info=True)
                    self._stats["total_errors"] += 1
                finally:
                    try:
                        self._queue.task_done()
                    except Exception:
                        pass

            except Exception as exc:
                logger.error(
                    "[Pipeline] ❌ 워커(%s) 루프 에러: %s",
                    thread_name,
                    exc,
                    exc_info=True,
                )

        logger.info("[Pipeline] 워커 스레드 종료: %s", thread_name)

    # ============================================================
    # 비동기 캔들 처리 (중앙 루프)
    # ============================================================
    async def process_candle(self, candle: dict) -> None:
        """비동기 캔들 처리 (중앙 루프에서 실행)"""
        if not self._running:
            # NOTE: avoid re-entrant calling of start() from central loop
            pass

        self._standardize_headers(candle)
        logger.debug("[Pipeline] 캔들 수신: symbol=%s", candle.get("symbol", ""))

        task = asyncio.create_task(self._process_task(candle))
        self._tasks.add(task)

        def _done_cb(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.exception("[Pipeline] 태스크 예외: %s", exc)

        task.add_done_callback(_done_cb)

    # ============================================================
    # 헤더 표준화
    # ============================================================
    def _standardize_headers(self, candle: dict) -> None:
        """캔들 헤더 표준화 (trace_id, ingest_ts, idempotency_key)"""
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
    # 핵심 처리 태스크
    # ============================================================
    async def _process_task(self, candle: dict) -> None:
        """핵심 처리 태스크 (검증 → 저장 → 퍼블리싱)"""
        # Semaphore 초기화는 중앙 루프 문맥에서 수행
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
                # Step 1: 메타데이터 조회
                last_snap_time = await self._get_last_snapshot(symbol, timeframe)

                # Step 2: 검증
                validation_result = await self._validate_candle(
                    candle, last_snap_time, symbol
                )
                if not validation_result:
                    return  # 검증 실패 시 종료

                # Step 3: 저장
                await self._save_candle(candle, symbol)

                # Step 4: 메타데이터 갱신
                await self._update_metadata(candle, symbol, timeframe)

                # Step 5: 퍼블리싱
                await self._maybe_publish(candle)

                self._stats["total_processed"] += 1

                # 처리 완료 콜백 호출 (QPS 카운터 등 외부 모니터링)
                self._fire_on_processed(symbol, timeframe, candle)

                # 10개마다 INFO 로그 (REST API 추적용)
                if self._stats["total_processed"] % 10 == 0:
                    logger.info(
                        "[Pipeline] 처리 진행: %d개 완료 (수신: %d, 에러: %d)",
                        self._stats["total_processed"],
                        self._stats["total_received"],
                        self._stats["total_errors"],
                    )

            except Exception as exc:
                logger.exception("[Pipeline] 처리 중 예외 발생: %s", exc)
                self._stats["total_errors"] += 1

    # ============================================================
    # 메타/검증/저장/퍼블리시 등 보조 메서드 (기존 코드 유지)
    # ============================================================
    async def _get_last_snapshot(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """메타데이터에서 마지막 스냅샷 조회"""
        logger.debug("[Pipeline] 처리 단계 1: 메타데이터 조회 (symbol=%s)", symbol)
        last_snap_time = None
        if self.metadata:
            try:
                last_snap_time = await self.metadata.get_snapshot(symbol, timeframe)
                logger.debug("스냅샷 조회 성공: %s = %s", symbol, last_snap_time)
            except Exception as exc:
                logger.debug("스냅샷 조회 실패(무시): %s", exc)
        return last_snap_time

    async def _validate_candle(self, candle: dict, last_snap_time: Optional[datetime], symbol: str) -> bool:
        """캔들 검증 (Validator 호출)"""
        logger.debug("[Pipeline] 처리 단계 2: 검증 (symbol=%s)", symbol)
        try:
            if self.validator:
                self.validator.validate(candle, last_time=last_snap_time)
                logger.debug("[Pipeline] 검증 통과: symbol=%s", symbol)
            else:
                logger.debug("Validator 미설정 - 검증 스킵")
            return True

        except GapExceededException as exc:
            logger.warning(
                "[Pipeline] Gap 감지 (계속 저장): symbol=%s reason=%s",
                symbol,
                str(exc),
            )
            return True

        except (ValidationError,) as exc:
            reason = str(exc)
            logger.info("[Pipeline] ❌ 검증 실패: symbol=%s reason=%s", symbol, reason)
            try:
                preserved = {
                    "symbol": candle.get("symbol"),
                    "time": candle.get("time"),
                    "candle": (candle.copy() if isinstance(candle, dict) else {"value": str(candle)}),
                    "reason": reason,
                }
                store_invalid_candle(preserved, reason)
            except Exception:
                logger.debug("pipeline invalid_store 저장 실패(무시)", exc_info=True)

            if self.isolator:
                try:
                    await self.isolator.handle(candle, exc)
                    logger.info("[Pipeline] ✅ Isolator 처리 완료: symbol=%s", symbol)
                except Exception as ie:
                    logger.error("[Pipeline] isolator 처리 실패: %s", ie)

            self._stats["total_errors"] += 1
            return False

    async def _save_candle(self, candle: dict, symbol: str) -> None:
        """캔들 저장 (Stager/Finalizer/Writer)"""
        logger.debug("[Pipeline] 처리 단계 3: 저장 (symbol=%s)", symbol)
        try:
            if self.stager and hasattr(self.stager, "add_candle"):
                await self.stager.add_candle(candle)
                logger.debug("[Pipeline] Staging 저장 완료: symbol=%s", symbol)
            elif self.finalizer and hasattr(self.finalizer, "upsert_candle"):
                await self.finalizer.upsert_candle(candle)
                logger.debug("[Pipeline] Finalizer 저장 완료: symbol=%s", symbol)
            elif self.writer and hasattr(self.writer, "upsert"):
                await self.writer.upsert(candle)
                logger.debug("[Pipeline] Writer 저장 완료: symbol=%s", symbol)
            else:
                logger.warning("저장소 없음: stager/finalizer/writer 중 하나 필요")
        except Exception as exc:
            logger.error("저장 중 오류, isolator로 이관: %s", exc, exc_info=True)
            if self.isolator:
                await self.isolator.handle(candle, exc)
            self._stats["total_errors"] += 1
            raise

    async def _update_metadata(self, candle: dict, symbol: str, timeframe: str) -> None:
        """메타데이터 갱신"""
        logger.debug("[Pipeline] 🔍 처리 단계 4: 메타데이터 갱신 (symbol=%s)", symbol)
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
            logger.warning("메타 갱신 실패(무시): %s", exc)

    async def _maybe_publish(self, candle: dict) -> None:
        """Redis/Kafka 퍼블리싱"""
        payload = None
        try:
            payload = json.dumps(candle, default=str)
        except Exception:
            payload = str(candle)

        # Redis 퍼블리싱
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
                        logger.debug("Redis publish 예외(fallback): %s", e)
            except Exception as exc:
                logger.debug("Redis publish 실패(무시): %s", exc)

        # Kafka 퍼블리싱
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
                logger.debug("Kafka produce 실패(무시): %s", exc)

    # ============================================================
    # 통계 조회 메서드 (UI 모니터링용)
    # ============================================================
    def get_stats(self) -> dict:
        """Pipeline 처리 통계 반환"""
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