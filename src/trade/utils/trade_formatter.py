#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문/체결 데이터의 UI 표시용 포맷팅을 담당합니다.

[Responsibilities]
- 주문 상태 코드를 한국어 레이블로 변환
- 주문 방향(bid/ask)을 한국어 레이블로 변환
- 체결 시각 포맷팅

[References]
- Upbit 주문 상태: https://docs.upbit.com/reference/주문-리스트-조회
"""
from __future__ import annotations

from datetime import datetime


class TradeFormatter:
    """주문/체결 데이터 포맷터."""

    STATUS_LABELS: dict[str, str] = {
        "wait": "미체결",
        "watch": "예약중",
        "done": "체결완료",
        "cancel": "취소됨",
    }

    SIDE_LABELS: dict[str, str] = {
        "bid": "매수",
        "ask": "매도",
    }

    @classmethod
    def status(cls, code: str) -> str:
        """주문 상태 코드를 한국어 레이블로 변환합니다.

        Args:
            code: Upbit 주문 상태 코드 ("wait" | "watch" | "done" | "cancel").

        Returns:
            한국어 상태 레이블.
        """
        return cls.STATUS_LABELS.get(code, code)

    @classmethod
    def side(cls, code: str) -> str:
        """주문 방향 코드를 한국어 레이블로 변환합니다.

        Args:
            code: 주문 방향 코드 ("bid" | "ask").

        Returns:
            한국어 방향 레이블.
        """
        return cls.SIDE_LABELS.get(code, code)

    @staticmethod
    def timestamp(iso_str: str) -> str:
        """ISO 8601 타임스탬프를 'YYYY-MM-DD HH:MM:SS' 형식으로 변환합니다.

        Args:
            iso_str: ISO 8601 형식 문자열.

        Returns:
            포맷된 날짜/시간 문자열.
        """
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            return iso_str
