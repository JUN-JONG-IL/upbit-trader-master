#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
손절 전략 모음 – 고정 비율/트레일링/ATR 기반 손절가를 산출합니다.

[Responsibilities]
- 고정 비율 손절가 계산
- 트레일링 스탑 가격 업데이트
- ATR 기반 손절가 계산

[References]
- ATR(Average True Range): https://en.wikipedia.org/wiki/Average_true_range
"""
from __future__ import annotations


class StopLoss:
    """손절 전략 클래스."""

    @staticmethod
    def fixed_rate(entry_price: float, stop_rate: float) -> float:
        """고정 비율 손절가를 계산합니다.

        Args:
            entry_price: 진입 가격.
            stop_rate: 손절 비율 (0~1, 예: 0.03 = 3%).

        Returns:
            손절가.
        """
        if not (0 < stop_rate < 1):
            raise ValueError("stop_rate는 (0, 1) 범위여야 합니다.")
        return entry_price * (1 - stop_rate)

    @staticmethod
    def trailing_stop(current_price: float, peak_price: float, trail_rate: float) -> float:
        """트레일링 스탑 가격을 계산합니다.

        Args:
            current_price: 현재 시세.
            peak_price: 진입 이후 최고가.
            trail_rate: 최고가 대비 허용 하락 비율 (0~1).

        Returns:
            트레일링 스탑 가격.
        """
        if not (0 < trail_rate < 1):
            raise ValueError("trail_rate는 (0, 1) 범위여야 합니다.")
        stop_price = peak_price * (1 - trail_rate)
        return stop_price

    @staticmethod
    def atr_based(entry_price: float, atr: float, multiplier: float = 2.0) -> float:
        """ATR 기반 손절가를 계산합니다.

        Args:
            entry_price: 진입 가격.
            atr: Average True Range 값.
            multiplier: ATR 배수 (기본값: 2.0).

        Returns:
            ATR 기반 손절가.
        """
        if atr <= 0:
            raise ValueError("atr은 0보다 커야 합니다.")
        return entry_price - atr * multiplier
