#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문 실행 전 유효성 검증 – 잔고 확인, 중복 주문 방지 등을 담당합니다.

[Responsibilities]
- 주문 파라미터 기본 유효성 검사
- 계좌 잔고 대비 주문 가능 여부 확인
- 동일 조건 중복 주문 여부 확인

[References]
- Upbit 잔고 API: https://docs.upbit.com/reference/전체-계좌-조회
"""
from __future__ import annotations

from typing import Any


class TradeValidator:
    """주문 유효성 검증 클래스."""

    def validate_order(self, order: dict[str, Any]) -> tuple[bool, str]:
        """주문 파라미터의 유효성을 검사합니다.

        Args:
            order: 주문 파라미터 딕셔너리.

        Returns:
            (is_valid, reason) 튜플.
        """
        required = {"market", "side", "ord_type"}
        missing = required - order.keys()
        if missing:
            return False, f"필수 파라미터 누락: {missing}"
        if order["side"] not in ("bid", "ask"):
            return False, f"잘못된 side 값: {order['side']}"
        return True, ""

    def check_balance(self, side: str, amount: float, balance: float) -> tuple[bool, str]:
        """주문 금액/수량이 잔고 내에 있는지 확인합니다.

        Args:
            side: 주문 방향 ("bid" | "ask").
            amount: 주문 금액 또는 수량.
            balance: 현재 사용 가능 잔고.

        Returns:
            (is_ok, reason) 튜플.
        """
        if amount <= 0:
            return False, "주문 금액/수량은 0보다 커야 합니다."
        if amount > balance:
            return False, f"잔고 부족: 필요 {amount}, 가용 {balance}"
        return True, ""

    def check_duplicate(self, pending_orders: list[dict[str, Any]], order: dict[str, Any]) -> bool:
        """동일 조건의 미체결 주문이 이미 존재하는지 확인합니다.

        Args:
            pending_orders: 현재 미체결 주문 목록.
            order: 신규 주문 파라미터.

        Returns:
            중복이면 True, 아니면 False.
        """
        for existing in pending_orders:
            if (
                existing.get("market") == order.get("market")
                and existing.get("side") == order.get("side")
                and existing.get("price") == order.get("price")
            ):
                return True
        return False
