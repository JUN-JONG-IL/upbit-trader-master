#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문 실행 엔진 – 시장가/지정가/스탑/트레일링스탑 주문을 Upbit API로 전송합니다.

[Responsibilities]
- 주문 타입별 API 파라미터 조립 및 전송
- 클라이언트 주문 ID(idempotency key) 관리
- 주문 상태 조회 및 취소 처리

[References]
- Upbit REST API: https://docs.upbit.com/reference/주문하기
"""
from __future__ import annotations

from typing import Any


class OrderEngine:
    """주문 실행 엔진.

    Upbit API를 통해 시장가/지정가/스탑/트레일링스탑 주문을 실행합니다.
    """

    def place_order(
        self,
        market: str,
        side: str,
        order_type: str,
        volume: float | None = None,
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """주문을 실행합니다.

        Args:
            market: 마켓 코드 (예: "KRW-BTC").
            side: 주문 방향 ("bid" 매수 | "ask" 매도).
            order_type: 주문 타입 ("limit" | "price" | "market" | "stop").
            volume: 주문 수량 (지정가/시장가 매도 시 필수).
            price: 주문 가격 (지정가/시장가 매수 시 필수).
            client_order_id: 클라이언트 주문 식별자 (멱등성 키).

        Returns:
            Upbit API 응답 딕셔너리.
        """
        raise NotImplementedError

    def cancel_order(self, uuid: str) -> dict[str, Any]:
        """주문을 취소합니다.

        Args:
            uuid: 취소할 주문의 UUID.

        Returns:
            Upbit API 응답 딕셔너리.
        """
        raise NotImplementedError

    def get_order_status(self, uuid: str) -> dict[str, Any]:
        """주문 상태를 조회합니다.

        Args:
            uuid: 조회할 주문의 UUID.

        Returns:
            Upbit API 응답 딕셔너리.
        """
        raise NotImplementedError
