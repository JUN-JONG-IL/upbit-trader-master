#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문 관련 API

[Endpoints]
- GET  /orders          - 주문 목록 조회
- GET  /orders/{id}     - 특정 주문 조회
- POST /orders          - 주문 생성 (모의거래/실거래)
- DELETE /orders/{id}   - 주문 취소

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 27장

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 📦 모델 정의
# ─────────────────────────────────────────────────────────────────────────────

class OrderCreateRequest:
    """주문 생성 요청 모델"""
    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: str,
        volume: Optional[float] = None,
        price: Optional[float] = None,
    ):
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.volume = volume
        self.price = price


# ─────────────────────────────────────────────────────────────────────────────
# 📡 API 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/orders",
    summary="주문 목록 조회",
)
async def get_orders(
    symbol: Optional[str] = Query(None, description="코인 심볼 필터"),
    state: str = Query("wait", description="주문 상태 (wait, done, cancel)"),
    limit: int = Query(100, ge=1, le=1000, description="조회 개수"),
) -> Dict[str, Any]:
    """
    주문 목록 조회

    Args:
        symbol: 코인 심볼 필터 (None이면 전체)
        state: 주문 상태
        limit: 조회 개수

    Returns:
        주문 목록
    """
    orders = await _fetch_orders(symbol=symbol, state=state, limit=limit)
    return {
        "count": len(orders),
        "orders": orders,
    }


@router.get(
    "/orders/{order_id}",
    summary="특정 주문 조회",
)
async def get_order(order_id: str) -> Dict[str, Any]:
    """
    특정 주문 조회

    Args:
        order_id: 주문 UUID

    Returns:
        주문 상세 정보
    """
    order = await _fetch_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"주문 없음: {order_id}")
    return order


@router.post(
    "/orders",
    summary="주문 생성",
    status_code=201,
)
async def create_order(
    body: Dict[str, Any] = Body(
        ...,
        examples={
            "limit_order": {
                "summary": "지정가 주문",
                "value": {
                    "symbol": "KRW-BTC",
                    "side": "bid",
                    "order_type": "limit",
                    "volume": 0.001,
                    "price": 50000000,
                }
            }
        },
    ),
) -> Dict[str, Any]:
    """
    주문 생성

    Args:
        body: 주문 요청 본문

    Returns:
        생성된 주문 정보
    """
    symbol = body.get("symbol")
    side = body.get("side")
    order_type = body.get("order_type", "limit")
    volume = body.get("volume")
    price = body.get("price")

    if not symbol or not side:
        raise HTTPException(status_code=400, detail="symbol과 side는 필수입니다")

    if side not in ("bid", "ask"):
        raise HTTPException(status_code=400, detail="side는 'bid' 또는 'ask'여야 합니다")

    result = await _place_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        volume=volume,
        price=price,
    )
    if not result:
        raise HTTPException(status_code=503, detail="주문 생성 실패")
    return result


@router.delete(
    "/orders/{order_id}",
    summary="주문 취소",
)
async def cancel_order(order_id: str) -> Dict[str, Any]:
    """
    주문 취소

    Args:
        order_id: 주문 UUID

    Returns:
        취소 결과
    """
    result = await _cancel_order(order_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"주문 취소 실패: {order_id}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 🔧 내부 비즈니스 로직
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_orders(
    symbol: Optional[str],
    state: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """주문 목록 조회 (pyupbit/aiopyupbit 사용)"""
    try:
        import pyupbit  # type: ignore
        access_key = os.getenv("UPBIT_ACCESS_KEY", "")
        secret_key = os.getenv("UPBIT_SECRET_KEY", "")
        if not access_key or not secret_key:
            logger.debug("[OrdersAPI] API 키 없음")
            return []
        upbit = pyupbit.Upbit(access_key, secret_key)
        result = upbit.get_order(symbol, state=state)
        orders = result if isinstance(result, list) else ([result] if result else [])
        return orders[:limit]
    except ImportError:
        return []
    except Exception as exc:
        logger.warning("[OrdersAPI] 주문 목록 조회 실패: %s", exc)
        return []


async def _fetch_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """특정 주문 조회"""
    try:
        import pyupbit  # type: ignore
        access_key = os.getenv("UPBIT_ACCESS_KEY", "")
        secret_key = os.getenv("UPBIT_SECRET_KEY", "")
        upbit = pyupbit.Upbit(access_key, secret_key)
        result = upbit.get_order(order_id)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("[OrdersAPI] 주문 조회 실패: %s", exc)
        return None


async def _place_order(
    symbol: str,
    side: str,
    order_type: str,
    volume: Optional[float],
    price: Optional[float],
) -> Optional[Dict[str, Any]]:
    """주문 실행"""
    try:
        import pyupbit  # type: ignore
        access_key = os.getenv("UPBIT_ACCESS_KEY", "")
        secret_key = os.getenv("UPBIT_SECRET_KEY", "")
        upbit = pyupbit.Upbit(access_key, secret_key)
        if side == "bid":
            result = upbit.buy_limit_order(symbol, price, volume)
        else:
            result = upbit.sell_limit_order(symbol, price, volume)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("[OrdersAPI] 주문 생성 실패: %s", exc)
        return None


async def _cancel_order(order_id: str) -> Optional[Dict[str, Any]]:
    """주문 취소"""
    try:
        import pyupbit  # type: ignore
        access_key = os.getenv("UPBIT_ACCESS_KEY", "")
        secret_key = os.getenv("UPBIT_SECRET_KEY", "")
        upbit = pyupbit.Upbit(access_key, secret_key)
        result = upbit.cancel_order(order_id)
        return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("[OrdersAPI] 주문 취소 실패: %s", exc)
        return None