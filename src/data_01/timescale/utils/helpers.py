#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimescaleDB 유틸리티 함수"""
from datetime import datetime, timezone
from typing import Optional


def parse_timeframe_seconds(timeframe: str) -> int:
    """TF 문자열 → 초 변환"""
    tf_map = {
        "1s": 1, "5s": 5, "10s": 10, "30s": 30,
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "12h": 43200,
        "1d": 86400, "1w": 604800,
    }
    return tf_map.get(timeframe, 60)


def now_utc() -> datetime:
    """UTC 현재 시간"""
    return datetime.now(timezone.utc)


def parse_iso(dt_str: str) -> Optional[datetime]:
    """ISO 문자열 → datetime"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def candle_key(symbol: str, timeframe: str, time: datetime) -> str:
    """캔들 고유 키 생성"""
    return f"{symbol}:{timeframe}:{time.isoformat()}"
