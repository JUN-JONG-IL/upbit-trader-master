# -*- coding: utf-8 -*-
"""
05_strategy 모듈 인터페이스
자동매매 전략 시스템 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_strategy_dir = str(Path(__file__).parents[3] / "05_strategy")
if _strategy_dir not in sys.path:
    sys.path.insert(0, _strategy_dir)


class StrategyService:
    """05_strategy 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._signal_manager: Optional[Any] = None
        self._registry: Optional[Any] = None

    def get_signal_manager(self) -> Any:
        if self._signal_manager is None:
            try:
                from core.signal_manager import SignalManager  # type: ignore
                self._signal_manager = SignalManager()
            except ImportError:
                pass
        return self._signal_manager

    def get_registry(self) -> Any:
        if self._registry is None:
            try:
                from core.strategy_registry import StrategyRegistry  # type: ignore
                self._registry = StrategyRegistry()
            except ImportError:
                pass
        return self._registry

    def list_strategies(self) -> List[str]:
        """등록된 전략 목록 반환"""
        registry = self.get_registry()
        if registry and hasattr(registry, "list"):
            return registry.list() or []
        return []

    def get_strategy(self, name: str) -> Optional[Any]:
        """전략 인스턴스 반환"""
        registry = self.get_registry()
        if registry and hasattr(registry, "get"):
            return registry.get(name)
        return None
