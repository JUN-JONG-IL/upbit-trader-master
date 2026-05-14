# -*- coding: utf-8 -*-
"""
앱 전역 설정
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class AppSettings:
    """앱 전역 설정 데이터 클래스"""

    # 서버 설정
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    # 자동 백필 설정
    auto_backfill_enabled: bool = False
    auto_backfill_interval_sec: int = 300

    # 로깅
    log_level: str = "INFO"

    # 추가 설정 (YAML / QSettings에서 로드된 값을 보관)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        """딕셔너리에서 설정 객체 생성"""
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        extra = {k: v for k, v in data.items() if k not in cls.__dataclass_fields__}
        obj = cls(**known)
        obj.extra = extra
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """설정 객체를 딕셔너리로 변환"""
        result: Dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            result[f] = getattr(self, f)
        result.update(self.extra)
        return result
