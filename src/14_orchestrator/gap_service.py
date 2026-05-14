# -*- coding: utf-8 -*-
"""
Gap Consumer 서비스 - Orchestrator 통합용 (Pylance 호환 수정판)

설명:
- src/data_01/gap/consumer.py의 GapConsumer를 애플리케이션 시작 시 백그라운드로 실행하고,
  애플리케이션 종료 시 안전히 정리하도록 도와주는 유틸리티입니다.
- Pylance 경고를 피하도록 모듈 수준 변수의 타입을 구체 타입 대신 Any로 표기했습니다.
- start_service()는 동기 컨텍스트에서 안전하게 호출 가능하며,
  start_service_async()는 비동기 컨텍스트에서 await로 호출 가능합니다.
- stop_service()는 서비스의 안전한 종료와 리소스 정리를 담당합니다.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

# GapConsumer import (consumer.py가 repo에 추가되어 있어야 합니다)
from src.data_01.gap.consumer import create_redis_client, create_timescale_pool, GapConsumer  # type: ignore

logger = logging.getLogger("orchestrator.gap_service")

# 모듈 수준 상태 (Any 타입을 사용하여 Pylance 타입 경고 방지)
_service_loop: Optional[asyncio.AbstractEventLoop] = None
_service_thread: Optional[threading.Thread] = None
_service_task: Optional[Any] = None  # asyncio.Task 또는 concurrent.futures.Future
_service_consumer: Optional[Any] = None  # GapConsumer 인스턴스 (Any로 표기)
_service_redis: Optional[Any] = None
_service_pool: Optional[Any] = None


async def _run_consumer_loop(redis_url: str, timescale_dsn: Optional[str], poll_interval: float = 1.0):
    """
    비동기 런너: Redis/timescale 연결 생성, GapConsumer 시작(데몬), 종료 대기.
    이 코드는 이벤트 루프(어떤 스레드에서든 실행 가능) 내부에서 동작합니다.
    """
    global _service_consumer, _service_redis, _service_pool
    try:
        _service_redis = await create_redis_client(redis_url)
    except Exception:
        logger.exception("[gap_service] Redis 연결 실패")
        return

    try:
        _service_pool = await create_timescale_pool(timescale_dsn) if timescale_dsn else None
    except Exception:
        logger.exception("[gap_service] Timescale 풀 생성 실패 (무시하고 진행)")
        _service_pool = None

    _service_consumer = GapConsumer(_service_redis, _service_pool)
    logger.info("[gap_service] GapConsumer 인스턴스 생성, 데몬 시작")
    # GapConsumer.run은 종료 신호를 받을 때까지 블로킹 루프이므로 여기서 호출
    await _service_consumer.run(poll_interval=poll_interval)


def _start_loop_in_thread(loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """
    새 이벤트 루프를 받아 별도 데몬 스레드에서 실행하고 Thread 객체를 반환합니다.
    """
    def _run():
        try:
            asyncio.set_event_loop(loop)
            loop.run_forever()
        except Exception:
            logger.exception("[gap_service] 이벤트 루프 스레드 예외")
    t = threading.Thread(target=_run, name="gap_service_loop", daemon=True)
    t.start()
    return t


def start_service(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    동기 컨텍스트에서 호출 가능한 서비스 시작 함수.
    - 현재 스레드에 이벤트 루프가 실행 중이면 해당 루프에서 태스크를 생성.
    - 루프가 없으면 새 루프를 만들고 별도 스레드에서 실행한 뒤 run_coroutine_threadsafe로 태스크를 등록.
    """
    global _service_loop, _service_thread, _service_task
    try:
        # 현재 실행중인 루프 확인
        loop = asyncio.get_running_loop()
        loop_running_here = True
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop_running_here = False

    if loop_running_here:
        # 같은 루프/스레드에서 실행 중이면 create_task로 실행
        if _service_task and getattr(_service_task, "done", lambda: False)():
            logger.info("[gap_service] 기존 서비스 태스크가 실행 중입니다.")
            return
        _service_loop = loop
        try:
            _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
            logger.info("[gap_service] GapConsumer 태스크를 현재 이벤트 루프에 생성했습니다.")
        except Exception:
            # 방어적: run_coroutine_threadsafe로 시도
            fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
            _service_task = fut
            logger.info("[gap_service] GapConsumer 태스크를 run_coroutine_threadsafe로 생성했습니다.")
    else:
        # 새 루프를 별도 스레드에서 실행하고 태스크를 등록
        _service_loop = loop
        _service_thread = _start_loop_in_thread(loop)
        fut = asyncio.run_coroutine_threadsafe(_run_consumer_loop(redis_url, timescale_dsn, poll_interval), loop)
        _service_task = fut
        logger.info("[gap_service] GapConsumer를 별도 스레드 이벤트 루프에서 실행하도록 시작했습니다.")


async def start_service_async(timescale_dsn: Optional[str], redis_url: str, poll_interval: float = 1.0):
    """
    비동기 환경에서 서비스 시작: await로 호출.
    """
    global _service_loop, _service_task
    loop = asyncio.get_running_loop()
    _service_loop = loop
    if _service_task and getattr(_service_task, "done", lambda: False)():
        logger.info("[gap_service] 기존 서비스 태스크가 실행 중입니다.")
        return
    _service_task = loop.create_task(_run_consumer_loop(redis_url, timescale_dsn, poll_interval))
    logger.info("[gap_service] 비동기 GapConsumer 태스크 생성")


async def stop_service():
    """
    서비스 정지: consumer.stop() 호출, task 대기, 리소스 정리
    - start_service로 시작한 경우에도 이 비동기 함수를 호출하여 정리하세요.
    """
    global _service_task, _service_consumer, _service_redis, _service_pool, _service_loop, _service_thread
    logger.info("[gap_service] 서비스 중지 시작")
    try:
        if _service_consumer:
            _service_consumer.stop()
        # 태스크가 asyncio.Task인 경우
        if isinstance(_service_task, asyncio.Task):
            try:
                await asyncio.wait_for(_service_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[gap_service] 서비스 종료 타임아웃 — 태스크 취소")
                _service_task.cancel()
                try:
                    await _service_task
                except Exception:
                    pass
        else:
            # concurrent.futures.Future (run_coroutine_threadsafe 반환)인 경우 cancel 시도
            if _service_task is not None:
                try:
                    _service_task.cancel()
                except Exception:
                    logger.debug("[gap_service] concurrent future cancel 실패", exc_info=True)
        # 안전히 Redis/DB 종료
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
                logger.debug("[gap_service] redis 안전종료 중 예외", exc_info=True)
        if _service_pool:
            try:
                await _service_pool.close()
            except Exception:
                logger.debug("[gap_service] pool close 중 예외", exc_info=True)
    finally:
        # 별도 루프/스레드로 실행한 경우 루프 정리
        if _service_loop and _service_thread:
            try:
                _service_loop.call_soon_threadsafe(_service_loop.stop)
            except Exception:
                logger.debug("[gap_service] 별도 루프 정지 호출 실패", exc_info=True)
            try:
                _service_thread.join(timeout=5.0)
            except Exception:
                logger.debug("[gap_service] 서비스 스레드 join 실패", exc_info=True)
        # 상태 초기화
        _service_task = None
        _service_consumer = None
        _service_redis = None
        _service_pool = None
        _service_loop = None
        _service_thread = None
        logger.info("[gap_service] 서비스 중지 완료")