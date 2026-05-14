"""
AI Engine Module

This module provides AI-powered trading engine functionality including:
- GPT-4o and Gemini API integration
- AI-based market analysis
- Real-time prediction and trading signals
- Emergency stop mechanism
- ML model selection and execution (MLService)

CHANGELOG:
- 2026-03-19 | Copilot | MLService 추가 (src/ai/priority/services/ → ai_engine/ 이동)
"""

__version__ = "1.0.0"
__author__ = "Upbit Trader Team"

from .ui.widget_ai_engine import AIEngineWidget
from .logic.ai_engine_logic import AIEngineLogic
from .ml_service import MLService

__all__ = [
    "AIEngineWidget",
    "AIEngineLogic",
    "MLService",
]
