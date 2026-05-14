#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Analysis Module

Provides news and social media sentiment analysis for trading signals.
Includes widget, business logic, and advanced NLP analysis (Phase 11-13).
"""

from .news_analyzer import NewsSentimentAnalyzer
from .social_analyzer import SocialSentimentAnalyzer
from .sentiment_logic import SentimentLogic
from .widget_sentiment import SentimentWidget

__all__ = [
    "NewsSentimentAnalyzer",
    "SocialSentimentAnalyzer",
    "SentimentLogic",
    "SentimentWidget",
]
