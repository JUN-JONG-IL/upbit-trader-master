# -*- coding: utf-8 -*-
"""
10_trade 모듈 인터페이스
주문 실행 및 리스크 관리 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_trade_dir = str(Path(__file__).parents[3] / "10_trade")
if _trade_dir not in sys.path:
    sys.path.insert(0, _trade_dir)


class TradeService:
    """10_trade 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._engine: Optional[Any] = None
        self._risk: Optional[Any] = None

    def get_engine(self) -> Any:
        if self._engine is None:
            try:
                from core.order_engine import OrderEngine  # type: ignore
                self._engine = OrderEngine()
            except ImportError:
                pass
        return self._engine

    def get_risk_service(self) -> Any:
        if self._risk is None:
            try:
                from risk.risk_service import RiskService  # type: ignore
                self._risk = RiskService()
            except ImportError:
                pass
        return self._risk

    async def place_order(
        self, symbol: str, side: str, volume: float, price: Optional[float] = None
    ) -> Dict[str, Any]:
        """주문 실행"""
        engine = self.get_engine()
        if engine and hasattr(engine, "place_order"):
            try:
                return await engine.place_order(symbol, side, volume, price) or {}
            except Exception:
                pass
        return {}

    async def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        engine = self.get_engine()
        if engine and hasattr(engine, "cancel_order"):
            try:
                return bool(await engine.cancel_order(order_id))
            except Exception:
                pass
        return False

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """미체결 주문 조회"""
        engine = self.get_engine()
        if engine and hasattr(engine, "get_open_orders"):
            try:
                return await engine.get_open_orders(symbol) or []
            except Exception:
                pass
        return []
