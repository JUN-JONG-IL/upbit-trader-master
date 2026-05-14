"""
Prediction Module

This module provides machine learning prediction functionality including:
- LSTM, GRU, Transformer deep learning models
- XGBoost and LightGBM gradient boosting models
- Price and market prediction
- Model training and evaluation
- Backtesting functionality
"""

__version__ = "1.0.0"
__author__ = "Upbit Trader Team"

from .ui.widget_prediction import PredictionWidget
from .logic.prediction_logic import PredictionLogic

__all__ = [
    "PredictionWidget",
    "PredictionLogic",
]
