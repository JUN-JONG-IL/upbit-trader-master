#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Engine

핵심 감성 분석 엔진 - 다중 소스 감성 집계 및 실시간 분석
- 뉴스, 트위터/X, Reddit 감성 집계
- 감성 히스토리 관리
- 감성 분포 계산
- 소스별 필터링
"""

import logging
import threading
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QObject = object

logger = logging.getLogger(__name__)


class SentimentLogic(QObject if _HAS_QT else object):
    """
    핵심 감성 분석 엔진

    다중 소스(뉴스, 트위터, Reddit)의 감성 데이터를 수집·집계합니다.
    """

    if _HAS_QT:
        sentiment_updated = pyqtSignal(dict)
        error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        if _HAS_QT:
            super().__init__(parent)
        else:
            super().__init__()

        self._sentiment_history: List[Dict] = []
        self._lock = threading.Lock()
        self._running = False
        self._sources: Dict[str, bool] = {
            "news": True,
            "twitter": True,
            "reddit": True,
        }

        logger.info("SentimentLogic initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_news_scraping(self) -> None:
        """뉴스 수집 시작"""
        self._sources["news"] = True
        logger.info("News scraping enabled")

    def start_twitter_scraping(self) -> None:
        """트위터 수집 시작"""
        self._sources["twitter"] = True
        logger.info("Twitter scraping enabled")

    def start_reddit_scraping(self) -> None:
        """Reddit 수집 시작"""
        self._sources["reddit"] = True
        logger.info("Reddit scraping enabled")

    def stop_all_scraping(self) -> None:
        """모든 수집 중지"""
        self._running = False
        for source in self._sources:
            self._sources[source] = False
        logger.info("All scraping stopped")

    def add_sentiment_data(self, data: Dict) -> None:
        """
        감성 데이터 추가

        Args:
            data: 감성 데이터 dict
                - source: str ('news'|'twitter'|'reddit')
                - score: float (-1.0 ~ 1.0)
                - text: str
                - timestamp: datetime
        """
        if not isinstance(data, dict):
            return
        if "timestamp" not in data:
            data["timestamp"] = datetime.now()
        with self._lock:
            self._sentiment_history.append(data)
            # Keep last 1000 entries
            if len(self._sentiment_history) > 1000:
                self._sentiment_history = self._sentiment_history[-1000:]

        if _HAS_QT:
            self.sentiment_updated.emit(data)

    def get_sentiment_history(
        self,
        source: Optional[str] = None,
        hours: int = 24,
    ) -> List[Dict]:
        """
        감성 히스토리 반환

        Args:
            source: 소스 필터 ('news'|'twitter'|'reddit'|None)
            hours: 조회 시간 범위

        Returns:
            감성 데이터 리스트
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        with self._lock:
            history = [
                d for d in self._sentiment_history
                if d.get("timestamp", datetime.min) >= cutoff
            ]
        if source:
            history = [d for d in history if d.get("source") == source]
        return history

    def get_sentiment_distribution(self) -> Dict[str, float]:
        """
        감성 분포 반환 (positive/neutral/negative 비율)

        Returns:
            {'positive': float, 'neutral': float, 'negative': float}
        """
        with self._lock:
            scores = [d.get("score", 0.0) for d in self._sentiment_history]

        if not scores:
            return {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

        positive = sum(1 for s in scores if s > 0.1)
        negative = sum(1 for s in scores if s < -0.1)
        neutral = len(scores) - positive - negative
        total = len(scores)

        return {
            "positive": positive / total,
            "neutral": neutral / total,
            "negative": negative / total,
        }

    def get_aggregate_score(self) -> float:
        """
        집계 감성 점수 반환 (-1.0 ~ 1.0)

        Returns:
            평균 감성 점수
        """
        with self._lock:
            scores = [d.get("score", 0.0) for d in self._sentiment_history]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def get_source_summary(self) -> Dict[str, Dict]:
        """
        소스별 감성 요약

        Returns:
            소스별 평균 점수 및 개수
        """
        summary: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "total_score": 0.0, "avg_score": 0.0}
        )
        with self._lock:
            for d in self._sentiment_history:
                src = d.get("source", "unknown")
                summary[src]["count"] += 1
                summary[src]["total_score"] += d.get("score", 0.0)

        for src, info in summary.items():
            count = info["count"]
            info["avg_score"] = info["total_score"] / count if count > 0 else 0.0
            del info["total_score"]

        return dict(summary)

    def clear_history(self) -> None:
        """감성 히스토리 초기화"""
        with self._lock:
            self._sentiment_history.clear()
        logger.info("Sentiment history cleared")
