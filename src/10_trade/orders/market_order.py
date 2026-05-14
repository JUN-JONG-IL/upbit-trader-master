#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
시장가 주문 처리 모듈.

[Responsibilities]
- 시장가 매수/매도 주문 파라미터 조립
- OrderEngine을 통한 주문 실행

[References]
- Upbit 시장가 주문 API: https://docs.upbit.com/reference/주문하기
"""
from __future__ import annotations

from typing import Any


class MarketOrder:
    """시장가 주문 클래스."""

    def build_bid(self, market: str, price: float) -> dict[str, Any]:
        """시장가 매수 주문 파라미터를 조립합니다.

        Args:
            market: 마켓 코드 (예: "KRW-BTC").
            price: 매수 금액 (KRW).

        Returns:
            주문 파라미터 딕셔너리.
        """
        return {
            "market": market,
            "side": "bid",
            "price": price,
            "ord_type": "price",
        }

    def build_ask(self, market: str, volume: float) -> dict[str, Any]:
        """시장가 매도 주문 파라미터를 조립합니다.

        Args:
            market: 마켓 코드.
            volume: 매도 수량.

        Returns:
            주문 파라미터 딕셔너리.
        """
        return {
            "market": market,
            "side": "ask",
            "volume": volume,
            "ord_type": "market",
        }
