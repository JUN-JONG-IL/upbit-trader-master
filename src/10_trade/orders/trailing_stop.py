#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
트레일링 스탑 주문 처리 모듈 – 가격 상승에 따라 손절가를 자동으로 추적합니다.

[Responsibilities]
- 최고가(peak price) 추적 및 갱신
- 트레일링 스탑 가격 동적 계산
- 스탑 조건 충족 시 매도 신호 발생

[References]
- Trailing Stop: https://en.wikipedia.org/wiki/Order_(exchange)#Trailing_stop_order
"""
from __future__ import annotations


class TrailingStop:
    """트레일링 스탑 주문 클래스."""

    def __init__(self, trail_rate: float) -> None:
        """
        Args:
            trail_rate: 최고가 대비 허용 하락 비율 (0~1, 예: 0.03 = 3%).
        """
        if not (0 < trail_rate < 1):
            raise ValueError("trail_rate는 (0, 1) 범위여야 합니다.")
        self.trail_rate = trail_rate
        self._peak_price: float = 0.0
        self._stop_price: float = 0.0

    def update(self, current_price: float) -> float:
        """현재 가격으로 최고가 및 스탑 가격을 업데이트합니다.

        Args:
            current_price: 현재 시세.

        Returns:
            현재 트레일링 스탑 가격.
        """
        if current_price > self._peak_price:
            self._peak_price = current_price
            self._stop_price = self._peak_price * (1 - self.trail_rate)
        return self._stop_price

    def is_triggered(self, current_price: float) -> bool:
        """트레일링 스탑 조건 충족 여부를 반환합니다.

        Args:
            current_price: 현재 시세.

        Returns:
            손절 조건 충족 시 True.
        """
        return self._stop_price > 0 and current_price <= self._stop_price

    @property
    def stop_price(self) -> float:
        """현재 트레일링 스탑 가격."""
        return self._stop_price

    @property
    def peak_price(self) -> float:
        """추적 중인 최고가."""
        return self._peak_price
