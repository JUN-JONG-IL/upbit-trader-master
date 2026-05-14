#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소 설정 모델

컬렉션: exchange_config
스키마:
{
    "exchange": "upbit",
    "api_key": "encrypted_key",
    "secret_key": "encrypted_secret",
    "rest_url": "https://api.upbit.com/v1",
    "ws_url": "wss://api.upbit.com/websocket/v1",
    "rate_limit": {"rest": 10, "ws": 5},
    "enabled": true
}

보안 주의:
- API 키는 암호화 저장 (AES-256)
- 환경 변수 또는 Vault 사용 권장
- MongoDB 접근 권한 최소화
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


@dataclass
class RateLimit:
    """거래소 API 요청 제한"""
    rest: int = 10
    ws: int = 5


@dataclass
class ExchangeConfig:
    """거래소 API 설정"""
    exchange: str
    api_key: str = ""
    secret_key: str = ""
    rest_url: str = ""
    ws_url: str = ""
    rate_limit: RateLimit = field(default_factory=RateLimit)
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
        if isinstance(self.rate_limit, dict):
            self.rate_limit = RateLimit(**self.rate_limit)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("created_at", "updated_at"):
            if d.get(k) and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExchangeConfig":
        d = dict(d)
        d.pop("_id", None)
        if not d.get("exchange"):
            raise ValueError("exchange field is required in ExchangeConfig")
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = datetime.fromisoformat(d[k])
                except Exception:
                    d[k] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
