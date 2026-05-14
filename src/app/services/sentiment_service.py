# -*- coding: utf-8 -*-
"""
sentiment 모듈 인터페이스
뉴스/소셜 감성 분석 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_sentiment_dir = str(Path(__file__).parents[3] / "sentiment")
if _sentiment_dir not in sys.path:
    sys.path.insert(0, _sentiment_dir)


class SentimentService:
    """sentiment 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._engine: Optional[Any] = None

    def get_engine(self) -> Any:
        if self._engine is None:
            try:
                from analysis.core.sentiment_engine import SentimentLogic  # type: ignore
                self._engine = SentimentLogic()
            except ImportError:
                pass
        return self._engine

    async def analyze(self, symbol: str) -> Dict[str, Any]:
        """심볼 감성 분석"""
        engine = self.get_engine()
        if engine and hasattr(engine, "analyze"):
            try:
                return await engine.analyze(symbol) or {}
            except Exception:
                pass
        return {}

    async def get_news(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """관련 뉴스 조회"""
        engine = self.get_engine()
        if engine and hasattr(engine, "get_news"):
            try:
                return await engine.get_news(symbol, limit) or []
            except Exception:
                pass
        return []
