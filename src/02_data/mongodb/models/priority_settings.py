#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 모델

컬렉션: priority_settings
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


@dataclass
class PrioritySettings:
    """심볼별 우선순위 설정"""
    symbol: str
    priority: str = "MEDIUM"   # HIGH / MEDIUM / LOW
    reason: str = ""
    manual_override: bool = False
    updated_by: str = "system"
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PrioritySettings":
        d = dict(d)
        d.pop("_id", None)
        if isinstance(d.get("updated_at"), str):
            try:
                d["updated_at"] = datetime.fromisoformat(d["updated_at"])
            except Exception:
                d["updated_at"] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
