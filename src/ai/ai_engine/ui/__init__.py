"""AI Engine UI Components — backward-compat shim (v4.0)

실제 구현은 src/ai/ui/ai_engine/ 로 이동되었습니다.
"""
try:
    from ...ui.ai_engine.widget_ai_engine import AIEngineWidget
    __all__ = ["AIEngineWidget"]
except ImportError:
    __all__ = []
