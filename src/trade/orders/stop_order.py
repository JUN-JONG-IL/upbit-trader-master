#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
스탑 주문 처리 모듈 – 지정 가격 도달 시 자동으로 시장가 주문을 실행합니다.

[Responsibilities]
- 스탑 주문 조건 등록 및 가격 모니터링
- 스탑 가격 도달 시 OrderEngine으로 시장가 주문 실행

[References]
- Stop Order 개념: https://en.wikipedia.org/wiki/Order_(exchange)#Stop_order
"""
from __future__ import annotations

from typing import Any


class StopOrder:
    """스탑 주문 클래스."""

    def build(
        self,
        market: str,
        side: str,
        stop_price: float,
        volume: float,
    ) -> dict[str, Any]:
        """스탑 주문 파라미터를 조립합니다.

        Args:
            market: 마켓 코드 (예: "KRW-BTC").
            side: 주문 방향 ("bid" | "ask").
            stop_price: 스탑 트리거 가격.
            volume: 주문 수량.

        Returns:
            스탑 주문 파라미터 딕셔너리.
        """
        return {
            "market": market,
            "side": side,
            "stop_price": stop_price,
            "volume": volume,
            "ord_type": "stop",
        }

    def is_triggered(self, current_price: float, stop_price: float, side: str) -> bool:
        """스탑 주문 트리거 여부를 판단합니다.

        Args:
            current_price: 현재 시세.
            stop_price: 스탑 트리거 가격.
            side: 주문 방향 ("bid" | "ask").

        Returns:
            트리거 조건 충족 시 True.
        """
        if side == "ask":
            return current_price <= stop_price
        return current_price >= stop_price
