"""
06_ai/ui — AI UI 통합 모듈 (v4.0)

AI 엔진 및 예측 위젯을 단일 진입점에서 제공합니다.

Exports:
- AIEngineWidget (ui/ai_engine/widget_ai_engine.py)
- PredictionWidget (ui/prediction/widget_prediction.py)
"""

try:
    from .ai_engine.widget_ai_engine import AIEngineWidget
    from .prediction.widget_prediction import PredictionWidget

    __all__ = [
        "AIEngineWidget",
        "PredictionWidget",
    ]
except ImportError:
    # Allow import in headless/test environments
    __all__ = []
