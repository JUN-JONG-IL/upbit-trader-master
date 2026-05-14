#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문 처리에서 공통으로 사용하는 헬퍼 함수 모음.

[Responsibilities]
- 가격/수량/금액 포맷팅
- 클라이언트 주문 ID(UUID) 생성

[References]
- Upbit 호가 단위: https://docs.upbit.com/docs/upbit-quotation-overview
"""
from __future__ import annotations

import uuid
from decimal import ROUND_DOWN, Decimal


def format_price(price: float, decimals: int = 0) -> str:
    """가격을 지정된 소수점 자리수로 포맷합니다.

    Args:
        price: 원본 가격.
        decimals: 소수점 자리수 (기본값: 0).

    Returns:
        포맷된 가격 문자열.
    """
    quantize_str = "1" if decimals == 0 else f"0.{'0' * decimals}"
    d = Decimal(str(price)).quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
    return f"{d:,}"


def format_quantity(volume: float, decimals: int = 8) -> str:
    """수량을 지정된 소수점 자리수로 포맷합니다.

    Args:
        volume: 원본 수량.
        decimals: 소수점 자리수 (기본값: 8).

    Returns:
        포맷된 수량 문자열.
    """
    quantize_str = f"0.{'0' * decimals}"
    d = Decimal(str(volume)).quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
    return str(d)


def calculate_total(price: float, volume: float) -> float:
    """주문 총 금액을 계산합니다.

    Args:
        price: 주문 가격.
        volume: 주문 수량.

    Returns:
        총 금액 (price * volume).
    """
    return float(Decimal(str(price)) * Decimal(str(volume)))


def generate_client_order_id(prefix: str = "upbit") -> str:
    """UUID 기반 클라이언트 주문 ID를 생성합니다.

    Args:
        prefix: ID 앞에 붙을 접두사 (기본값: "upbit").

    Returns:
        "{prefix}-{uuid4}" 형식의 고유 주문 ID.
    """
    return f"{prefix}-{uuid.uuid4()}"
