"""
09_sentiment package: News and Social Media Sentiment Analysis

Exports:
- SentimentWidget (from sentiment.ui)
- SentimentLogic (from analysis.core)
"""

from .analysis.ui.widget_sentiment import SentimentWidget
from .analysis.core.sentiment_engine import SentimentLogic

__all__ = ["SentimentWidget", "SentimentLogic"]
