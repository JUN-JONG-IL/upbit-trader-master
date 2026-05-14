#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""isolated_candles 테이블 데이터 모델"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Any, Dict


@dataclass
class IsolatedRecord:
    """isolated_candles 테이블 레코드"""
    time: datetime
    symbol: str
    timeframe: str
    isolation_reason: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    seq: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    isolated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.isolated_at is None:
            self.isolated_at = datetime.now(timezone.utc)
