"""
Sentiment Analysis Module

This module provides sentiment analysis functionality including:
- News scraping and sentiment analysis
- Twitter/X social media monitoring
- Reddit community sentiment tracking
- Multi-source sentiment aggregation
- Real-time sentiment visualization
"""

__version__ = "1.0.0"
__author__ = "Upbit Trader Team"

from .ui.widget_sentiment import SentimentWidget
from .core.sentiment_engine import SentimentLogic
from .models.sentiment_analyzer import SentimentAnalyzer
from .models.summarizer import Summarizer

__all__ = [
    "SentimentWidget",
    "SentimentLogic",
    "SentimentAnalyzer",
    "Summarizer",
]

