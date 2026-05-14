# -*- coding: utf-8 -*-
"""
OEMS 라우터(router) 모듈 - 단일 파일 PoC

기능 요약:
- 단순 SOR(스마트 오더 라우팅) 구현(PoC):
  - 주문 속성에 따라 실행 대상(target)을 결정 (예: 'sim' 또는 'upbit')
  - 주문 수량이 클 경우 지정된 최대 청크 단위로 분할(split)하여 실행 계획 생성
  - 우선순위, 사용자 설정, 심볼 기반 규칙을 적용한 간단한 정책 엔진 포함
- 인터페이스:
  - async def route_order(order: dict, *, max_chunk: Decimal|None = None) -> dict
    반환: execution_plan = {
      "client_oid": "...",
      "plan": [
        {"target": "sim"|"upbit", "price": "...", "quantity": "...", "part_id": 0, ...},
        ...
      ]
    }
- PoC 의도:
  - 실제 전송(실제 adapter 호출)은 이 모듈의 책임이 아니며,
    생성된 execution_plan을 adapter에게 전달하여 실행합니다.
- 모든 주석은 한글입니다.

주의:
- 이 모듈은 PoC 수준입니다. 운영에서는 SOR 알고리즘(수수료/유동성/슬리피지/마켓 상태),
  라우팅 정책 데이터베이스, 모니터링/메트릭을 추가해야 합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger("oems.router")
logging.getLogger("oems.router").addHandler(logging.NullHandler())

# 환경변수로 기본 실행대상 설정 (PoC)
# "sim" 또는 "upbit" 등 adapter 키를 사용
DEFAULT_TARGET = os.environ.get("OEMS_DEFAULT_TARGET", "sim")
# 심볼별 강제 라우팅(간단 예시): "KRW-BTC:upbit,KRW-XXX:sim"
SYMBOL_ROUTE_OVERRIDES = os.environ.get("OEMS_SYMBOL_ROUTE_OVERRIDES", "")
# 최대 분할 단위(수량 기준) 기본값 (문자열로 설정 가능)
DEFAULT_MAX_CHUNK = Decimal(os.environ.get("OEMS_MAX_CHUNK", "0.1"))

# 심볼별 override 파싱
def _parse_symbol_overrides(raw: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not raw:
        return out
    for part in raw.split(","):
        try:
            sym, tgt = part.split(":")
            out[sym.strip()] = tgt.strip()
        except Exception:
            continue
    return out

_SYMBOL_OVERRIDES = _parse_symbol_overrides(SYMBOL_ROUTE_OVERRIDES)


# ---------------------------
# 유틸리티
# ---------------------------
def _to_decimal(val: Any) -> Decimal:
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _make_part_id(client_oid: str, idx: int) -> str:
    return f"{client_oid}:{idx}"


# ---------------------------
# 라우팅 정책 엔진 (간단)
# ---------------------------
def choose_target(order: Dict[str, Any]) -> str:
    """
    단일 주문에 대해 실행 대상(target)을 결정하는 정책 함수(PoC).
    우선순위:
      1) order에 'force_target' 키가 있으면 그 값 사용
      2) 심볼 오버라이드(_SYMBOL_OVERRIDES) 사용
      3) 시장가/지정가 로직 (예: 시장가 -> sim(내부)-> 기본)
      4) 환경변수 DEFAULT_TARGET
    """
    # 강제 타겟 지정 우선
    force = order.get("force_target")
    if force:
        logger.debug("[router] force_target 사용: %s", force)
        return str(force)

    # 심볼 오버라이드
    sym = order.get("symbol")
    if sym and sym in _SYMBOL_OVERRIDES:
        tgt = _SYMBOL_OVERRIDES[sym]
        logger.debug("[router] symbol override 사용: %s -> %s", sym, tgt)
        return tgt

    # 주문 타입 기반 간단 분류 (PoC)
    order_type = (order.get("order_type") or "").lower()
    side = (order.get("side") or "").lower()

    # 예시 정책: 시장가 대용량 매도는 거래소로 보냄
    qty = _to_decimal(order.get("quantity"))
    if order_type == "market":
        # 시장가이면서 소량이면 sim으로, 대량이면 exchange로
        if qty > Decimal("1"):  # 임계값 예시
            return "upbit"
        return "sim"

    # 기본은 환경변수 DEFAULT_TARGET
    return DEFAULT_TARGET


def split_order_quantity(total_qty: Decimal, max_chunk: Decimal) -> List[Decimal]:
    """
    총수량을 max_chunk 단위로 분할하여 리스트 반환.
    예: total=0.35, max_chunk=0.1 -> [0.1,0.1,0.1,0.05]
    """
    if max_chunk <= 0:
        return [total_qty]
    parts: List[Decimal] = []
    remaining = total_qty
    while remaining > 0:
        if remaining >= max_chunk:
            parts.append(max_chunk)
            remaining -= max_chunk
        else:
            parts.append(remaining)
            remaining = Decimal("0")
    return parts


# ---------------------------
# 핵심 API: route_order
# ---------------------------
async def route_order(order: Dict[str, Any], *, max_chunk: Optional[Decimal] = None) -> Dict[str, Any]:
    """
    주문을 받아 실행 계획(execution_plan)을 생성합니다.
    - order: dict (권장 필드: client_oid, user_id, symbol, side, order_type, price, quantity, metadata)
    - max_chunk: 분할 단위(수량). None이면 DEFAULT_MAX_CHUNK 사용.
    반환:
      {
        "client_oid": "...",
        "plan": [
          {"part_id": "...", "target":"sim", "price": "...", "quantity": "...", "meta": {...}},
          ...
        ],
        "summary": {"total_quantity": "...", "parts": N}
      }
    """
    # 기본값 보정
    client_oid = order.get("client_oid") or str(uuid.uuid4())
    symbol = order.get("symbol")
    if not symbol:
        raise ValueError("order.symbol 필요")
    qty = _to_decimal(order.get("quantity"))
    if qty <= 0:
        raise ValueError("quantity > 0 필요")
    price = order.get("price")  # 문자열/숫자 허용 (adapter에서 해석)
    order_type = (order.get("order_type") or "limit").lower()

    # 분할 단위 결정
    chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK

    # 타겟 결정(전체 주문에 대한 우선 타겟)
    target = choose_target(order)

    # 간단 정책: 만약 심볼이 유동성이 낮아서 exchange 우선이라면 target 교체 가능
    # (PoC - 실제 로직은 외부 데이터 참조)
    logger.debug("[router] route_order: client_oid=%s symbol=%s qty=%s target=%s", client_oid, symbol, qty, target)

    # 분할 생성
    parts_qty = split_order_quantity(qty, chunk) if chunk and chunk > 0 else [qty]

    plan: List[Dict[str, Any]] = []
    for idx, part_qty in enumerate(parts_qty):
        part = {
            "part_id": _make_part_id(client_oid, idx),
            "client_oid": client_oid,
            "symbol": symbol,
            "side": order.get("side"),
            "order_type": order_type,
            "price": price,
            "quantity": str(part_qty),  # 문자열로 직렬화하여 adapter가 파싱하도록 함
            "target": target,
            "meta": order.get("metadata", {}),
        }
        plan.append(part)

    summary = {"total_quantity": str(qty), "parts": len(plan)}

    execution_plan = {"client_oid": client_oid, "plan": plan, "summary": summary}
    logger.info("[router] execution_plan 생성: client_oid=%s parts=%d total=%s target=%s", client_oid, len(plan), str(qty), target)
    return execution_plan


# ---------------------------
# 단위 실행/테스트용 런처
# ---------------------------
if __name__ == "__main__":
    # 간단한 수동 테스트(개발자용)
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Router PoC test")
    parser.add_argument("--symbol", type=str, default="KRW-BTC")
    parser.add_argument("--quantity", type=str, default="0.35")
    parser.add_argument("--price", type=str, default="50000")
    parser.add_argument("--order-type", type=str, default="limit")
    parser.add_argument("--side", type=str, default="buy")
    parser.add_argument("--max-chunk", type=str, default=str(DEFAULT_MAX_CHUNK))
    args = parser.parse_args()

    async def _main():
        order = {
            "client_oid": f"cli-{uuid.uuid4().hex[:8]}",
            "user_id": "user_test",
            "symbol": args.symbol,
            "side": args.side,
            "order_type": args.order_type,
            "price": args.price,
            "quantity": args.quantity,
            "metadata": {"test": True},
        }
        try:
            plan = await route_order(order, max_chunk=Decimal(args.max_chunk))
            print("Execution Plan:")
            import orjson
            print(orjson.dumps(plan, option=orjson.OPT_INDENT_2).decode())
        except Exception as e:
            print("Error:", e)

    asyncio.run(_main())