"""Prediction UI Components — backward-compat shim (v4.0)

실제 구현은 src/ai/ui/prediction/ 로 이동되었습니다.
"""
try:
    from ...ui.prediction.widget_prediction import PredictionWidget
    __all__ = ["PredictionWidget"]
except ImportError:
    __all__ = []
