# -*- coding: utf-8 -*-
"""
scanner 모듈 인터페이스
종목 스캐너 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_scanner_dir = str(Path(__file__).parents[3] / "scanner")
if _scanner_dir not in sys.path:
    sys.path.insert(0, _scanner_dir)


class ScannerService:
    """scanner 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._engine: Optional[Any] = None

    def get_engine(self) -> Any:
        if self._engine is None:
            try:
                from engine.logic.scanner_engine import ScannerEngine  # type: ignore
                self._engine = ScannerEngine()
            except ImportError:
                pass
        return self._engine

    async def scan(self, conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """조건 스캔 실행"""
        engine = self.get_engine()
        if engine and hasattr(engine, "scan"):
            try:
                return await engine.scan(conditions) or []
            except Exception:
                pass
        return []
