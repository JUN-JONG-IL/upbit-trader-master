# -*- coding: utf-8 -*-
"""
03_market 모듈 인터페이스
실시간 시세, 호가, 체결 데이터 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_market_dir = str(Path(__file__).parents[3] / "03_market")
if _market_dir not in sys.path:
    sys.path.insert(0, _market_dir)


class MarketService:
    """03_market 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._coinlist: Optional[Any] = None
        self._orderbook: Optional[Any] = None
        self._trade: Optional[Any] = None

    def get_coinlist_widget(self) -> Any:
        if self._coinlist is None:
            try:
                from symbol_list.coinlist_widget import CoinlistWidget  # type: ignore
                self._coinlist = CoinlistWidget
            except ImportError:
                pass
        return self._coinlist

    def get_orderbook_widget(self) -> Any:
        if self._orderbook is None:
            try:
                from orderbook.orderbook_widget import OrderbookWidget  # type: ignore
                self._orderbook = OrderbookWidget
            except ImportError:
                pass
        return self._orderbook

    def get_trade_widget(self) -> Any:
        if self._trade is None:
            try:
                from trade.trade_widget import TradeWidget  # type: ignore
                self._trade = TradeWidget
            except ImportError:
                pass
        return self._trade

    async def get_symbols(self) -> List[str]:
        """상장 코인 목록 조회 - 03_market 모듈 위임"""
        try:
            from market.market_data import get_tickers  # type: ignore
            return await get_tickers() or []
        except ImportError:
            pass
        except Exception:
            pass
        try:
            import aiopyupbit  # type: ignore
            return await aiopyupbit.get_tickers(fiat="KRW") or []
        except Exception:
            return []

    async def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        """호가 데이터 조회 - 03_market 모듈 위임"""
        try:
            from orderbook.orderbook_logic import get_orderbook as _get_orderbook  # type: ignore
            return await _get_orderbook(symbol) or {}
        except ImportError:
            pass
        except Exception:
            pass
        try:
            import aiopyupbit  # type: ignore
            return await aiopyupbit.get_orderbook(symbol) or {}
        except Exception:
            return {}
