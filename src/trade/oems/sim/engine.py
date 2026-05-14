# -*- coding: utf-8 -*-
"""
OEMS 시뮬레이션 엔진 (sim engine) - Pylance/파서 호환 수정판

설명:
- 패키지 경로에 숫자가 포함된 폴더명(예: trade)이 있어 'from src.trade.oems import ...' 같은
  정적 import가 SyntaxError를 발생시킵니다. 이를 피하기 위해 importlib.import_module을 사용하여
  런타임에 동적으로 모듈을 로드하도록 수정했습니다.
- 그 외 기능은 기존 PoC와 동일: router가 만든 execution_plan을 실행(sim 또는 adapter 호출),
  결과를 수집하고(선택적으로) ledger에 기록합니다.
- 모든 주석은 한글입니다.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

import orjson  # type: ignore

logger = logging.getLogger("oems.sim.engine")
logger.addHandler(logging.NullHandler())

# 동적 임포트: 'trade' 같은 숫자 시작 디렉터리 때문에 정적 import가 실패할 수 있으므로
# importlib.import_module로 모듈을 로드합니다.
try:
    router = importlib.import_module("src.trade.oems.router")
except Exception:
    logger.exception("[engine] router 모듈 로드 실패")
    router = None  # type: ignore

try:
    adapter_upbit = importlib.import_module("src.trade.oems.adapter_upbit")
except Exception:
    logger.exception("[engine] adapter_upbit 모듈 로드 실패")
    adapter_upbit = None  # type: ignore

try:
    ledger = importlib.import_module("src.trade.oems.ledger")
except Exception:
    logger.exception("[engine] ledger 모듈 로드 실패")
    ledger = None  # type: ignore


# ---------------------------
# 내부 유틸: 시뮬 실행(빠른 PoC)
# ---------------------------
async def _simulate_execution(part: Dict[str, Any]) -> Dict[str, Any]:
    """
    'sim' 타겟에 대해 짧은 시뮬레이션을 수행.
    반환 이벤트 형태(예시):
      {
        "ok": True,
        "target": "sim",
        "part_id": "...",
        "executed_quantity": "...",
        "price": "...",
        "exec_id": "..."
      }
    """
    await asyncio.sleep(0.05)  # 경량 시뮬레이션 지연
    exec_id = uuid.uuid4().hex
    executed_quantity = part.get("quantity")
    price = part.get("price")
    logger.debug("[sim] executed part_id=%s qty=%s price=%s", part.get("part_id"), executed_quantity, price)
    return {
        "ok": True,
        "target": "sim",
        "part_id": part.get("part_id"),
        "executed_quantity": executed_quantity,
        "price": price,
        "exec_id": exec_id,
        "raw": {"note": "simulated"}
    }


async def _execute_via_upbit(part: Dict[str, Any], session: Optional[Any] = None) -> Dict[str, Any]:
    """
    Upbit adapter를 통한 실행 시도.
    adapter_upbit 모듈이 로드되지 않았으면 실패 결과를 반환.
    """
    if adapter_upbit is None:
        logger.error("[engine] adapter_upbit 모듈 없음 - 실행 불가")
        return {"ok": False, "target": part.get("target"), "part_id": part.get("part_id"), "error": "adapter missing"}

    try:
        # adapter_upbit.place_order expects specific keys; adapt part accordingly
        order_payload = {
            "client_oid": part.get("part_id"),
            "market": part.get("symbol"),
            "symbol": part.get("symbol"),
            "side": part.get("side") or "bid",
            "ord_type": "limit" if part.get("order_type", "limit") == "limit" else part.get("order_type"),
            "price": part.get("price"),
            "volume": part.get("quantity"),
            "metadata": part.get("meta", {}),
        }
        res = await adapter_upbit.place_order(order_payload, session=session)
        exec_event = {
            "ok": bool(res.get("ok", False)),
            "target": part.get("target"),
            "part_id": part.get("part_id"),
            "response": res,
            "exec_id": res.get("uuid") or uuid.uuid4().hex
        }
        return exec_event
    except Exception:
        logger.exception("[engine] adapter_upbit 실행 예외")
        return {"ok": False, "target": part.get("target"), "part_id": part.get("part_id"), "exec_id": None, "error": "adapter error"}


# ---------------------------
# 공개 API: execute_plan
# ---------------------------
async def execute_plan(execution_plan: Dict[str, Any], ledger_pool: Optional[Any] = None, adapter_session: Optional[Any] = None) -> Dict[str, Any]:
    """
    실행 계획을 순차적으로 처리하고 결과를 수집하여 반환합니다.
    - execution_plan: router.route_order() 반환값 (딕셔너리)
    - ledger_pool: ledger.create_pool로 생성한 asyncpg pool을 전달하면 record_order로 원장에 기록 시도
    - adapter_session: adapter_upbit.create_session 으로 생성한 세션을 재사용
    """
    client_oid = execution_plan.get("client_oid")
    plan_parts: List[Dict[str, Any]] = execution_plan.get("plan", [])
    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0

    session = adapter_session

    for part in plan_parts:
        target = part.get("target")
        try:
            if target == "sim":
                evt = await _simulate_execution(part)
            else:
                evt = await _execute_via_upbit(part, session=session)
            results.append(evt)
            if evt.get("ok"):
                succeeded += 1
                # ledger에 기록 (선택적)
                if ledger_pool is not None and ledger is not None and hasattr(ledger, "record_order"):
                    order_record = {
                        "client_oid": part.get("part_id"),
                        "trace_id": client_oid,
                        "user_id": execution_plan.get("user_id") or "unknown",
                        "symbol": part.get("symbol"),
                        "side": part.get("side"),
                        "order_type": part.get("order_type"),
                        "price": part.get("price"),
                        "quantity": part.get("quantity"),
                        "metadata": {"engine_exec": True, "exec_id": evt.get("exec_id")}
                    }
                    try:
                        rec = await ledger.record_order(ledger_pool, order_record)
                        logger.debug("[engine] ledger.record_order res=%s", rec)
                    except Exception:
                        logger.exception("[engine] ledger.record_order 예외")
            else:
                failed += 1
                logger.warning("[engine] 파트 실패: part_id=%s evt=%s", part.get("part_id"), evt)
        except Exception:
            failed += 1
            logger.exception("[engine] 파트 실행 중 예외: part=%s", part)

    summary = {"total_parts": len(plan_parts), "succeeded": succeeded, "failed": failed}
    return {"client_oid": client_oid, "summary": summary, "results": results}


# ---------------------------
# CLI / 단발 테스트 런처
# ---------------------------
def _build_sample_order() -> Dict[str, Any]:
    """
    샘플 주문 생성: 라우터/엔진 통합 테스트용
    """
    return {
        "client_oid": f"cli-{uuid.uuid4().hex[:8]}",
        "user_id": "user_test",
        "symbol": "KRW-BTC",
        "side": "buy",
        "order_type": "limit",
        "price": "50000",
        "quantity": "0.35",
        "metadata": {"test": True}
    }


async def _cli_test(timescale_dsn: Optional[str] = None):
    """
    간단한 end-to-end PoC 테스트:
    - 샘플 주문 -> router.route_order -> execute_plan -> 결과 출력
    - timescale_dsn 제공 시 ledger pool 생성 후 레코드 시도
    """
    pool = None
    try:
        if timescale_dsn and ledger is not None and hasattr(ledger, "create_pool"):
            pool = await ledger.create_pool(timescale_dsn)
            if pool:
                try:
                    await ledger.init_ledger_table(pool)
                except Exception:
                    pass

        if router is None:
            raise RuntimeError("router 모듈이 로드되지 않았습니다. src.trade.oems.router 파일을 확인하세요.")

        order = _build_sample_order()
        exec_plan = await router.route_order(order)
        print("Execution plan:")
        print(orjson.dumps(exec_plan, option=orjson.OPT_INDENT_2).decode())

        result = await execute_plan(exec_plan, ledger_pool=pool)
        print("Execution result:")
        print(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode())
    finally:
        if pool is not None and ledger is not None and hasattr(ledger, "close_pool"):
            await ledger.close_pool(pool)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OEMS Sim Engine PoC test")
    parser.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""), help="optional Timescale/Postgres DSN for ledger recording")
    args = parser.parse_args()

    asyncio.run(_cli_test(args.timescale_dsn))