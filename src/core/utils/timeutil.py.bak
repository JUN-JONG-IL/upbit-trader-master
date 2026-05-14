# -*- coding: utf-8 -*-
"""
시간 유틸리티: UTC 표준화 및 로컬 변환 도우미

사용법:
    from src.01_core.utils.timeutil import to_utc, to_local, parse_time

- 내부적으로는 UTC로 저장(standardize).
- 화면/응답 직전에 to_local(dt_utc, tz_name) 호출해 표시용으로 변환.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any
from zoneinfo import ZoneInfo

# 기본 표시 타임존 (개발 편의: 설정에서 덮어쓸 수 있음)
DEFAULT_DISPLAY_TZ = "Asia/Seoul"


def parse_time(value: Any) -> Optional[datetime]:
    """
    다양한 입력(ISO 문자열, epoch sec/ms, datetime)을 UTC-aware datetime으로 반환.
    실패 시 None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            if isinstance(value, (int, float)):
                # heuristic: 1e12 이상이면 ms
                if value > 1e12:
                    dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            elif isinstance(value, str):
                s = value.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                try:
                    dt = datetime.fromisoformat(s)
                except Exception:
                    # 마지막 수단: 숫자 문자열로 epoch 처리
                    try:
                        num = float(s)
                        if num > 1e12:
                            dt = datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
                        else:
                            dt = datetime.fromtimestamp(num, tz=timezone.utc)
                    except Exception:
                        return None
        except Exception:
            return None

    # timezone 정보가 없으면 UTC로 간주
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def to_utc(value: Any) -> Optional[datetime]:
    """입력값을 UTC datetime으로 반환(파싱 실패 시 None)."""
    return parse_time(value)


def to_local(dt_utc: datetime, tz_name: Optional[str] = None) -> datetime:
    """
    UTC datetime을 tz_name(예: 'Asia/Seoul')로 변환해 반환.
    tz_name이 None이면 DEFAULT_DISPLAY_TZ 사용.
    dt_utc는 timezone-aware(권장).
    """
    if tz_name is None:
        tz_name = DEFAULT_DISPLAY_TZ
    if dt_utc is None:
        raise ValueError("dt_utc is required")
    if dt_utc.tzinfo is None:
        # 입력이 naive면 UTC라 가정
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(tz_name))