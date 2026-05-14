#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 관리 모듈

DB 또는 JSON 파일로부터 우선순위 설정을 로드/저장합니다.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "priority_config.json"
)

PRIORITY_KEYS = [
    "volume",
    "market_cap",
    "popularity",
    "new_listings",
    "volatility",
    "price_change",
    "pattern_detection",
    "social_mentions",
]


@dataclass
class PriorityConfig:
    """우선순위 설정 데이터 클래스"""

    setting_name: str = "기본 설정"

    # 우선순위 항목 활성화 여부
    volume_enabled: bool = False
    market_cap_enabled: bool = False
    popularity_enabled: bool = False
    new_listings_enabled: bool = False
    volatility_enabled: bool = False
    price_change_enabled: bool = False
    pattern_detection_enabled: bool = False
    social_mentions_enabled: bool = False

    # 우선순위 순서 (활성화된 항목의 키 목록)
    priority_order: List[str] = field(default_factory=list)

    # 로직 선택 (OR / AND)
    logic_type: str = "OR"

    # 활성화 여부
    is_active: bool = True

    def enabled_items(self) -> List[str]:
        """활성화된 항목의 키 목록 반환"""
        mapping = {
            "volume": self.volume_enabled,
            "market_cap": self.market_cap_enabled,
            "popularity": self.popularity_enabled,
            "new_listings": self.new_listings_enabled,
            "volatility": self.volatility_enabled,
            "price_change": self.price_change_enabled,
            "pattern_detection": self.pattern_detection_enabled,
            "social_mentions": self.social_mentions_enabled,
        }
        return [key for key, enabled in mapping.items() if enabled]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PriorityConfig":
        known_fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class PriorityConfigManager:
    """우선순위 설정 파일 기반 관리자"""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._path = config_path or _DEFAULT_CONFIG_PATH
        self._config: PriorityConfig = PriorityConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> PriorityConfig:
        """JSON 파일에서 설정을 로드합니다."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._config = PriorityConfig.from_dict(data)
                logger.info("우선순위 설정 로드 완료: %s", self._path)
            else:
                logger.info("설정 파일 없음, 기본값 사용: %s", self._path)
        except Exception as exc:
            logger.error("우선순위 설정 로드 실패: %s", exc)
        return self._config

    def save(self, config: PriorityConfig) -> None:
        """설정을 JSON 파일에 저장합니다."""
        try:
            self._config = config
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(config.to_dict(), fh, ensure_ascii=False, indent=2)
            logger.info("우선순위 설정 저장 완료: %s", self._path)
        except Exception as exc:
            logger.error("우선순위 설정 저장 실패: %s", exc)
            raise

    @property
    def config(self) -> PriorityConfig:
        return self._config
