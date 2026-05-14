#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""staging_candles 테이블 데이터 모델"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class StagingRecord:
    """staging_candles 테이블 레코드"""
    time: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    seq: Optional[int] = None
    trades: Optional[int] = None
    received_at: Optional[datetime] = None
    processed: bool = False

    def __post_init__(self):
        if self.received_at is None:
            self.received_at = datetime.now(timezone.utc)
