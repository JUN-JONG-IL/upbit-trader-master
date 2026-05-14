#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
심볼(코인) 목록 조회 API

[Endpoints]
- GET /symbols          - 전체 심볼 목록
- GET /symbols/active   - 활성 심볼 목록

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 27장

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/symbols",
    summary="전체 심볼 목록 조회",
    response_description="코인 심볼 목록",
)
async def get_symbols(
    fiat: str = Query("KRW", description="기준 통화 (KRW, BTC, USDT)"),
) -> Dict[str, Any]:
    """
    Upbit 거래소 심볼 목록 조회

    Args:
        fiat: 기준 통화

    Returns:
        심볼 목록 및 메타데이터
    """
    symbols = await _fetch_symbols(fiat)
    return {
        "fiat": fiat,
        "count": len(symbols),
        "symbols": symbols,
    }


@router.get(
    "/symbols/active",
    summary="활성 심볼 목록 조회",
    response_description="활성 코인 심볼 목록",
)
async def get_active_symbols() -> Dict[str, Any]:
    """
    현재 활성화(모니터링 중)된 심볼 목록 조회

    Returns:
        활성 심볼 목록
    """
    symbols = await _fetch_active_symbols()
    return {
        "count": len(symbols),
        "symbols": symbols,
    }


@router.get(
    "/symbols/{symbol}",
    summary="특정 심볼 정보 조회",
)
async def get_symbol_info(symbol: str) -> Dict[str, Any]:
    """
    특정 심볼의 상세 정보 조회

    Args:
        symbol: 코인 심볼 (예: KRW-BTC)

    Returns:
        심볼 상세 정보
    """
    info = await _fetch_symbol_info(symbol)
    if not info:
        raise HTTPException(status_code=404, detail=f"심볼 없음: {symbol}")
    return info


# ── 내부 조회 함수 ────────────────────────────────────────────────────────────

async def _fetch_symbols(fiat: str = "KRW") -> List[Dict[str, Any]]:
    """aiopyupbit에서 심볼 목록 조회"""
    try:
        import aiopyupbit  # type: ignore
        tickers = await aiopyupbit.get_tickers(fiat=fiat, contain_name=True)
        return tickers or []
    except ImportError:
        logger.debug("[SymbolsAPI] aiopyupbit 없음 - 빈 결과 반환")
        return []
    except Exception as exc:
        logger.warning("[SymbolsAPI] 심볼 조회 실패: %s", exc)
        return []


async def _fetch_active_symbols() -> List[str]:
    """MongoDB에서 활성 심볼 조회"""
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )
        result = await db.find_items(
            db_name="config",
            collection_name="active_symbols",
            query={"active": True},
        )
        return [r.get("symbol", "") for r in (result or []) if r.get("symbol")]
    except ImportError:
        return []
    except Exception as exc:
        logger.warning("[SymbolsAPI] 활성 심볼 조회 실패: %s", exc)
        return []


async def _fetch_symbol_info(symbol: str) -> Optional[Dict[str, Any]]:
    """특정 심볼 정보 조회"""
    try:
        import aiopyupbit  # type: ignore
        tickers = await aiopyupbit.get_tickers(contain_name=True)
        if tickers:
            for t in tickers:
                code = t.get("market", "") if isinstance(t, dict) else getattr(t, "market", "")
                if code == symbol:
                    return t if isinstance(t, dict) else vars(t)
        return None
    except Exception as exc:
        logger.warning("[SymbolsAPI] 심볼 정보 조회 실패: %s", exc)
        return None
