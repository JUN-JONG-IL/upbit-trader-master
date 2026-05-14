#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
포지션 사이징 전략 모음 – 리스크 대비 최적 주문 수량/금액을 산출합니다.

[Responsibilities]
- 고정 금액 사이징
- 자산 대비 고정 비율 사이징
- 켈리 기준(Kelly Criterion) 사이징
- 리스크 패리티 사이징

[References]
- Kelly Criterion: https://en.wikipedia.org/wiki/Kelly_criterion
"""
from __future__ import annotations


class PositionSizing:
    """포지션 사이징 전략 클래스."""

    @staticmethod
    def fixed_amount(amount: float) -> float:
        """고정 금액 사이징.

        Args:
            amount: 고정 주문 금액 (KRW).

        Returns:
            주문 금액.
        """
        if amount <= 0:
            raise ValueError("amount는 0보다 커야 합니다.")
        return amount

    @staticmethod
    def fixed_percentage(total_assets: float, ratio: float) -> float:
        """자산 대비 고정 비율 사이징.

        Args:
            total_assets: 총 자산 (KRW).
            ratio: 투자 비율 (0~1).

        Returns:
            주문 금액.
        """
        if not (0 < ratio <= 1):
            raise ValueError("ratio는 (0, 1] 범위여야 합니다.")
        return total_assets * ratio

    @staticmethod
    def kelly_criterion(win_rate: float, win_loss_ratio: float, total_assets: float) -> float:
        """켈리 기준으로 최적 베팅 금액을 계산합니다.

        Args:
            win_rate: 승률 (0~1).
            win_loss_ratio: 평균 수익/손실 비율.
            total_assets: 총 자산 (KRW).

        Returns:
            켈리 공식으로 산출된 주문 금액.
        """
        if win_loss_ratio <= 0:
            raise ValueError("win_loss_ratio는 0보다 커야 합니다.")
        kelly_fraction = win_rate - (1 - win_rate) / win_loss_ratio
        kelly_fraction = max(0.0, min(kelly_fraction, 1.0))
        return total_assets * kelly_fraction

    @staticmethod
    def risk_parity(volatilities: list[float], total_assets: float) -> list[float]:
        """리스크 패리티 방식으로 각 자산 비중을 산출합니다.

        Args:
            volatilities: 각 자산의 변동성(표준편차) 리스트.
            total_assets: 총 자산 (KRW).

        Returns:
            각 자산에 할당할 금액 리스트.
        """
        if not volatilities:
            raise ValueError("volatilities 리스트가 비어 있습니다.")
        inv_vols = [1 / v for v in volatilities]
        total_inv = sum(inv_vols)
        return [total_assets * (iv / total_inv) for iv in inv_vols]
