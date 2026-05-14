# -*- coding: utf-8 -*-
"""
06_ai 모듈 인터페이스
AI 예측 및 시그널 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ai_dir = str(Path(__file__).parents[3] / "06_ai")
if _ai_dir not in sys.path:
    sys.path.insert(0, _ai_dir)


class AIService:
    """06_ai 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._engine: Optional[Any] = None
        self._predictor: Optional[Any] = None

    def get_engine(self) -> Any:
        if self._engine is None:
            try:
                from core.engine import AIEngine  # type: ignore
                self._engine = AIEngine()
            except ImportError:
                pass
        return self._engine

    def get_predictor(self) -> Any:
        if self._predictor is None:
            try:
                from prediction.price_predictor import PricePredictor  # type: ignore
                self._predictor = PricePredictor()
            except ImportError:
                pass
        return self._predictor

    async def predict_price(self, symbol: str, tf: str) -> Dict[str, Any]:
        """가격 예측 실행"""
        predictor = self.get_predictor()
        if predictor and hasattr(predictor, "predict"):
            try:
                return await predictor.predict(symbol, tf) or {}
            except Exception:
                pass
        return {}

    async def get_signals(self, symbol: str) -> List[Dict[str, Any]]:
        """AI 매매 시그널 조회"""
        engine = self.get_engine()
        if engine and hasattr(engine, "get_signals"):
            try:
                return await engine.get_signals(symbol) or []
            except Exception:
                pass
        return []
