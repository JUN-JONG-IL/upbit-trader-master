"""
Price and Volume Formatting Utilities

[Features]
- 가격 포맷팅 (KRW, USD)
- 거래량 포맷팅 (K, M, B)
- 퍼센트 포맷팅
- 타임스탬프 포맷팅
"""
from typing import Union


def format_price(price: float, currency: str = "KRW") -> str:
    """
    가격 포맷팅

    [Parameters]
    - price: 가격
    - currency: 통화 (KRW, USD)

    [Returns]
    - str: 포맷된 가격 문자열
    """
    if currency == "KRW":
        if price >= 1_000_000:
            return f"₩{price:,.0f}"
        elif price >= 1:
            return f"₩{price:,.0f}"
        else:
            return f"₩{price:.8f}"
    elif currency == "USD":
        if price >= 1:
            return f"${price:,.2f}"
        else:
            return f"${price:.8f}"
    return f"{price:.2f}"


def format_volume(volume: float) -> str:
    """
    거래량 포맷팅

    [Parameters]
    - volume: 거래량

    [Returns]
    - str: 포맷된 거래량 문자열 (예: 1.2K, 3.4M)
    """
    if volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.2f}B"
    elif volume >= 1_000_000:
        return f"{volume / 1_000_000:.2f}M"
    elif volume >= 1_000:
        return f"{volume / 1_000:.2f}K"
    return f"{volume:.2f}"


def format_percent(value: float, decimals: int = 2) -> str:
    """
    퍼센트 포맷팅

    [Parameters]
    - value: 퍼센트 값 (0.05 = 5%)
    - decimals: 소수점 자릿수

    [Returns]
    - str: 포맷된 퍼센트 문자열
    """
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def format_timestamp(ts: Union[int, float], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    타임스탬프 포맷팅

    [Parameters]
    - ts: Unix timestamp (초 단위)
    - fmt: 날짜 포맷 문자열

    [Returns]
    - str: 포맷된 날짜 문자열
    """
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime(fmt)
