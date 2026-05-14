# -*- coding: utf-8 -*-
"""포맷팅 유틸리티 (bytes / duration / timestamp)"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .constants import GB, KB, MB


def format_bytes(bytes_value: int) -> str:
    """바이트를 읽기 쉬운 형식으로 변환 (B / KB / MB / GB).

    Args:
        bytes_value: 변환할 바이트 수

    Returns:
        단위가 붙은 문자열 (예: "1.50 MB")
    """
    if bytes_value < KB:
        return f"{bytes_value} B"
    elif bytes_value < MB:
        return f"{bytes_value / KB:.2f} KB"
    elif bytes_value < GB:
        return f"{bytes_value / MB:.2f} MB"
    return f"{bytes_value / GB:.2f} GB"


def format_duration(seconds: int) -> str:
    """초를 읽기 쉬운 형식으로 변환 (초 / 분 / 시간 / 일).

    Args:
        seconds: 변환할 초 단위 시간

    Returns:
        단위가 붙은 문자열 (예: "3시간")
    """
    if seconds < 60:
        return f"{seconds}초"
    elif seconds < 3600:
        return f"{seconds // 60}분"
    elif seconds < 86400:
        return f"{seconds // 3600}시간"
    return f"{seconds // 86400}일"


def format_timestamp(ts: Optional[datetime], mode: str = "UTC") -> str:
    """타임스탬프를 UTC 또는 KST 형식으로 변환.

    Args:
        ts: 변환할 datetime 객체 (None이면 "-" 반환)
        mode: "UTC" 또는 "KST"

    Returns:
        포맷된 날짜/시간 문자열
    """
    if ts is None:
        return "-"
    if mode == "KST":
        kst = ts + timedelta(hours=9)
        return kst.strftime("%Y-%m-%d %H:%M:%S KST")
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")
