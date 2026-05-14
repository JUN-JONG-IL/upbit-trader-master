#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
리스크 관리 서비스 – 주문 전 종합 리스크 점검을 수행합니다.

[Responsibilities]
- 개별 주문 리스크 점검 (최대 주문 금액 초과 등)
- 일간 최대 손실 한도 도달 여부 확인
- 포트폴리오 익스포저(집중도) 초과 여부 확인
- 거래 허용 여부 최종 판단

[References]
- 리스크 관리 설계: docs/risk_management.md
"""
from __future__ import annotations

from typing import Any


class RiskService:
    """종합 리스크 관리 서비스."""

    def __init__(
        self,
        max_order_amount: float = 1_000_000,
        daily_loss_limit: float = 500_000,
        max_exposure_ratio: float = 0.3,
    ) -> None:
        """
        Args:
            max_order_amount: 단일 주문 최대 금액 (KRW).
            daily_loss_limit: 일간 최대 허용 손실 (KRW).
            max_exposure_ratio: 단일 종목 최대 익스포저 비율 (0~1).
        """
        self.max_order_amount = max_order_amount
        self.daily_loss_limit = daily_loss_limit
        self.max_exposure_ratio = max_exposure_ratio
        self._daily_loss: float = 0.0
        self._trading_allowed: bool = True

    def check_order_risk(self, order: dict[str, Any]) -> tuple[bool, str]:
        """개별 주문의 리스크를 점검합니다.

        Args:
            order: 주문 파라미터 딕셔너리.

        Returns:
            (is_ok, reason) 튜플.
        """
        amount = (order.get("price") or 0) * (order.get("volume") or 0)
        if amount > self.max_order_amount:
            return False, f"주문 금액 초과: {amount} > {self.max_order_amount}"
        return True, ""

    def check_daily_loss(self, realized_loss: float) -> tuple[bool, str]:
        """일간 손실 한도를 확인합니다.

        Args:
            realized_loss: 당일 누적 실현 손실 (양수 = 손실).

        Returns:
            (is_ok, reason) 튜플.
        """
        if realized_loss >= self.daily_loss_limit:
            self._trading_allowed = False
            return False, f"일간 손실 한도 도달: {realized_loss} >= {self.daily_loss_limit}"
        return True, ""

    def check_exposure(self, market: str, order_amount: float, total_assets: float) -> tuple[bool, str]:
        """단일 종목 익스포저(집중도)를 확인합니다.

        Args:
            market: 마켓 코드.
            order_amount: 추가 매수 금액 (KRW).
            total_assets: 총 자산 (KRW).

        Returns:
            (is_ok, reason) 튜플.
        """
        if total_assets <= 0:
            return False, "총 자산이 0 이하입니다."
        ratio = order_amount / total_assets
        if ratio > self.max_exposure_ratio:
            return False, f"{market} 익스포저 초과: {ratio:.1%} > {self.max_exposure_ratio:.1%}"
        return True, ""

    def is_trading_allowed(self) -> bool:
        """현재 거래 허용 여부를 반환합니다.

        Returns:
            거래 가능이면 True.
        """
        return self._trading_allowed
