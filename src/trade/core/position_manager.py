#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
포지션(보유 종목) 상태를 추적하고 손익을 계산합니다.

[Responsibilities]
- 체결 이벤트를 수신하여 포지션 데이터 갱신
- 종목별 평균 매수가 및 보유 수량 관리
- 실현/미실현 손익(PnL) 계산

[References]
- Upbit 잔고 API: https://docs.upbit.com/reference/전체-계좌-조회
"""
from __future__ import annotations

from typing import Any


class PositionManager:
    """포지션(보유 종목) 관리 클래스."""

    def __init__(self) -> None:
        self._positions: dict[str, dict[str, Any]] = {}

    def update_position(self, market: str, volume: float, avg_buy_price: float) -> None:
        """포지션 정보를 갱신합니다.

        Args:
            market: 마켓 코드 (예: "KRW-BTC").
            volume: 보유 수량.
            avg_buy_price: 평균 매수가.
        """
        self._positions[market] = {
            "volume": volume,
            "avg_buy_price": avg_buy_price,
        }

    def get_position(self, market: str) -> dict[str, Any] | None:
        """특정 종목의 포지션 정보를 반환합니다.

        Args:
            market: 마켓 코드.

        Returns:
            포지션 딕셔너리 또는 None.
        """
        return self._positions.get(market)

    def get_all_positions(self) -> dict[str, dict[str, Any]]:
        """전체 포지션 정보를 반환합니다.

        Returns:
            {market: position_dict} 형태의 딕셔너리.
        """
        return dict(self._positions)

    def calculate_pnl(self, market: str, current_price: float) -> float:
        """미실현 손익을 계산합니다.

        Args:
            market: 마켓 코드.
            current_price: 현재 시세.

        Returns:
            미실현 손익 (KRW). 포지션이 없으면 0.0.
        """
        position = self._positions.get(market)
        if position is None:
            return 0.0
        return (current_price - position["avg_buy_price"]) * position["volume"]
