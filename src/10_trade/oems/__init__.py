# -*- coding: utf-8 -*-
"""
src/10_trade/oems 패키지 초기화 모듈

설명:
- 이 파일은 OEMS 하위 모듈(risk, ledger, router, adapter_upbit 등)을 편리하게 import 하기 위한
  진입점 역할을 합니다.
- 단일 파일 작업 원칙을 준수하여 이 파일은 가벼운 래퍼와 팩토리 헬퍼만 제공하며,
  실제 로직은 각 모듈에 위임됩니다.
- 모든 주석은 한글로 작성되어 있습니다.

사용 예:
    from src.10_trade.oems import risk, ledger, router, adapter_upbit
    await risk.check_order(...)
    await ledger.record_order(...)
    plan = await router.route_order(order)
    await adapter_upbit.place_order(plan['plan'][0])
"""

from __future__ import annotations

import logging
from typing import Any, Optional

# 로거 설정 (상위 로거에 의해 제어되므로 최소한의 설정만 함)
logger = logging.getLogger("src.10_trade.oems")
logger.addHandler(logging.NullHandler())

# 공개 API로 노출할 하위 모듈을 import
# (lazy import을 선호하지만 단순성을 위해 즉시 import)
try:
    from . import risk  # type: ignore
except Exception:
    risk = None  # type: ignore

try:
    from . import ledger  # type: ignore
except Exception:
    ledger = None  # type: ignore

try:
    from . import router  # type: ignore
except Exception:
    router = None  # type: ignore

try:
    from . import adapter_upbit  # type: ignore
except Exception:
    adapter_upbit = None  # type: ignore

__all__ = [
    "risk",
    "ledger",
    "router",
    "adapter_upbit",
]


# ---------------------------
# 패키지 레벨 유틸리티(경량)
# ---------------------------
def available_components() -> dict:
    """
    현재 패키지에서 로드 가능한 컴포넌트 목록을 dict로 반환.
    테스트/디버깅 시 유용.
    반환 예:
      {"risk": True, "ledger": True, "router": True, "adapter_upbit": False}
    """
    return {
        "risk": risk is not None,
        "ledger": ledger is not None,
        "router": router is not None,
        "adapter_upbit": adapter_upbit is not None,
    }


async def init_all_for_dev(redis_url: Optional[str] = None, timescale_dsn: Optional[str] = None) -> dict:
    """
    개발 편의용 초기화 헬퍼:
    - risk: Redis 연결을 미리 열어서 재사용 가능한 client 반�� (init_redis는 risk 모듈에 있음)
    - ledger: asyncpg pool을 생성하여 반환 (create_pool 사용)
    - router/adapter_upbit는 특별 초기화 불필요 (Stateless)
    반환: 상태 dict
    주의: 운영에서는 각 모듈을 필요한 시점에 초기화/종료하도록 구성하세요.
    """
    status = {}
    # risk 리소스 초기화
    try:
        if risk is not None:
            client = await risk.init_redis(redis_url) if hasattr(risk, "init_redis") else None
            status["risk_redis"] = client
        else:
            status["risk_redis"] = None
    except Exception:
        logger.exception("[oems.init_all_for_dev] risk 초기화 실패")
        status["risk_redis"] = None

    # ledger 풀 생성
    try:
        if ledger is not None:
            pool = await ledger.create_pool(timescale_dsn)
            status["ledger_pool"] = pool
        else:
            status["ledger_pool"] = None
    except Exception:
        logger.exception("[oems.init_all_for_dev] ledger 초기화 실패")
        status["ledger_pool"] = None

    # router/adapter_upbit: 특별 초기화 없음
    status["router_ready"] = router is not None
    status["adapter_upbit_ready"] = adapter_upbit is not None

    return status


async def close_all_for_dev(status: dict) -> None:
    """
    init_all_for_dev에서 열었던 리소스 정리 유틸.
    - status: init_all_for_dev가 반환한 dict
    """
    try:
        client = status.get("risk_redis")
        if client is not None and hasattr(risk, "close_redis"):
            await risk.close_redis(client)
    except Exception:
        logger.exception("[oems.close_all_for_dev] risk close 실패")

    try:
        pool = status.get("ledger_pool")
        if pool is not None and hasattr(ledger, "close_pool"):
            await ledger.close_pool(pool)
    except Exception:
        logger.exception("[oems.close_all_for_dev] ledger close 실패")