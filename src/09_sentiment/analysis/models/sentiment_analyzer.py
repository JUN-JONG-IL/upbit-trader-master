#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Analyzer

FinBERT, KoBERT 기반 감성 분석 모델 인터페이스.
기존 models/sentiment_model.py 의 SentimentAnalyzer를 re-export합니다.
"""

# Re-export from the underlying model implementation
from .sentiment_model import SentimentAnalyzer  # noqa: F401

__all__ = ["SentimentAnalyzer"]
