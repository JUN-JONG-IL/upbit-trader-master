# -*- coding: utf-8 -*-
"""
OEMS 리스크 동기(블로킹) 래퍼

목적:
- src/10_trade/oems/risk.py의 비동기 함수를 동기(블로킹) 컨텍스트에서 안전하게 호출할 수 있는
  래퍼를 제공합니다. (예: PyQt UI 콜백, 동기 테스트 스크립트)
- 내부적으로 별도 스레드에서 asyncio.run으로 코루틴을 실행하여 현재 스레드의 이벤트 루프와 충돌을 방지합니다.
- 단일 책임: check_order_sync, release_reservation_sync, finalize_reservation_sync 제공.

주의:
- 장기 실행/높은 동시성 환경에서는 쓰레드 생성 비용/자원 관리를 고려하여 비동기 경로 사용을 권장합니다.
"""

from __future__ import annotations

import concurrent.futures
import functools
import json
from typing import Any, Dict, Optional

# 내부 비동기 구현 모듈 임포트
from src.10_trade.oems import risk  # type: ignore

_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None:
        # 동시성 요구가 낮으므로 작은 풀을 사용
        _executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="oems-risk-sync")
    return _executor


def _run_coroutine_in_thread(coro_func, *args, **kwargs):
    """
    주어진 코루틴 함수와 인자를 별도 스레드에서 asyncio.run으로 실행하고 결과를 반환.
    예외는 호출자에게 전달됩니다.
    """
    exec = _get_executor()

    def _task():
        import asyncio
        return asyncio.run(functools.partial(coro_func, *args, **kwargs)())

    # 위에서 partial(... )() returns coroutine, so adjust: we accept coro_func as async function
    def _runner():
        import asyncio
        # coro_func is async function; call with args to get coroutine
        coro = coro_func(*args, **kwargs)
        return asyncio.run(coro)

    fut = exec.submit(_runner)
    return fut.result()


def check_order_sync(order: Dict[str, Any], redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    동기 블로킹 방식으로 check_order를 실행합니다.
    - order: 주문 dict
    - redis_client: (선택) 비동기 redis client를 동기으로 사용할 수 없음(비동기 client 전달시 내부에서 무시될 수 있음).
      권장: 전달하지 마세요; 래퍼는 내부에서 risk.init_redis를 호출합니다.
    반환: risk.check_order 반환값(dict)
    """
    # risk.check_order은 async def check_order(order, redis_client=None)
    try:
        return _run_coroutine_in_thread(risk.check_order, order, redis_client)
    except Exception:
        # 예외는 그대로 전달
        raise


def release_reservation_sync(client_oid: str, user_id: str, redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    동기 블로킹 방식으로 release_reservation 실행.
    """
    try:
        return _run_coroutine_in_thread(risk.release_reservation, client_oid, user_id, redis_client)
    except Exception:
        raise


def finalize_reservation_sync(client_oid: str, user_id: str, redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    동기 블로킹 방식으로 finalize_reservation 실행.
    """
    try:
        return _run_coroutine_in_thread(risk.finalize_reservation, client_oid, user_id, redis_client)
    except Exception:
        raise


def shutdown():
    """
    내부 스레드풀을 종료합니다(앱 종료 시 호출 권장).
    """
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None