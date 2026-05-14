# -*- coding: utf-8 -*-
"""
01_core 모듈 인터페이스
인증, 설정, 공통 유틸리티 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_core_dir = str(Path(__file__).parents[3] / "01_core")
if _core_dir not in sys.path:
    sys.path.insert(0, _core_dir)


class CoreService:
    """01_core 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._auth: Optional[Any] = None
        self._config: Optional[Any] = None

    def get_auth(self) -> Any:
        """인증 모듈 반환"""
        if self._auth is None:
            try:
                from auth import auth_service  # type: ignore
                self._auth = auth_service
            except ImportError:
                pass
        return self._auth

    def get_config(self) -> Any:
        """설정 모듈 반환"""
        if self._config is None:
            try:
                from config import config_loader  # type: ignore
                self._config = config_loader
            except ImportError:
                pass
        return self._config

    def get_settings(self) -> Dict[str, Any]:
        """앱 전역 설정 조회"""
        cfg = self.get_config()
        if cfg and hasattr(cfg, "load"):
            try:
                return cfg.load() or {}
            except Exception:
                pass
        return {}
