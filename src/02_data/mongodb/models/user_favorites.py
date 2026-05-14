#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
관심 종목 모델

컬렉션: user_favorites
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


@dataclass
class UserFavorite:
    """사용자 관심 종목"""
    user_id: str
    symbol: str
    exchange: str = "upbit"
    note: str = ""
    added_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("added_at") and hasattr(d["added_at"], "isoformat"):
            d["added_at"] = d["added_at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UserFavorite":
        d = dict(d)
        d.pop("_id", None)
        if isinstance(d.get("added_at"), str):
            try:
                d["added_at"] = datetime.fromisoformat(d["added_at"])
            except Exception:
                d["added_at"] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
