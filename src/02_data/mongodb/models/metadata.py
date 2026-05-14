#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
심볼 메타데이터 모델

컬렉션: metadata
스키마:
{
    "symbol": "KRW-BTC",
    "exchange": "upbit",
    "korean_name": "비트코인",
    "active": true,
    "market_cap": 1000000000000,
    "volume_24h": 500000000000
}
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


@dataclass
class SymbolMetadata:
    """심볼 메타데이터"""
    symbol: str
    exchange: str = "upbit"
    korean_name: str = ""
    english_name: str = ""
    active: bool = True
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    base_currency: str = "KRW"
    quote_currency: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
        if not self.quote_currency:
            parts = self.symbol.split("-")
            self.quote_currency = parts[-1] if len(parts) > 1 else self.symbol

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # datetime → ISO string for MongoDB
        for k in ("created_at", "updated_at"):
            if d.get(k) and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SymbolMetadata":
        d = dict(d)
        d.pop("_id", None)
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = datetime.fromisoformat(d[k])
                except Exception:
                    d[k] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
