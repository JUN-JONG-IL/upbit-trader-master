#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candles 테이블 데이터 모델"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    """candles 테이블 레코드"""
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
    created_at: Optional[datetime] = None

    def to_dict(self):
        return {
            "time": self.time.isoformat() if self.time else None,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "seq": self.seq,
            "trades": self.trades,
        }
