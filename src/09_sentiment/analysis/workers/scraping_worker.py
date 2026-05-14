#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scraping Worker - QThread 기반 백그라운드 수집

다중 소스(뉴스, 트위터, Reddit)에서 데이터를 수집하는
논블로킹 백그라운드 워커입니다.
"""

import logging
from typing import List, Optional

try:
    from PyQt5.QtCore import QThread, pyqtSignal
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QThread = object

logger = logging.getLogger(__name__)


class ScrapingWorker(QThread if _HAS_QT else object):
    """
    QThread 기반 백그라운드 데이터 수집 워커

    UI 스레드를 차단하지 않고 감성 데이터를 수집합니다.
    """

    if _HAS_QT:
        data_received = pyqtSignal(dict)
        error_occurred = pyqtSignal(str)
        progress = pyqtSignal(int, str)
        finished_scraping = pyqtSignal()

    def __init__(
        self,
        source: str,
        keywords: List[str],
        max_items: int = 100,
        parent=None,
    ):
        """
        Initialize ScrapingWorker

        Args:
            source: 수집 소스 ('news'|'twitter'|'reddit')
            keywords: 수집 키워드 리스트
            max_items: 최대 수집 항목 수
            parent: 부모 QObject
        """
        if _HAS_QT:
            super().__init__(parent)
        else:
            super().__init__()

        self.source = source
        self.keywords = keywords
        self.max_items = max_items
        self._stop_flag = False

        logger.info(
            f"ScrapingWorker created: source={source}, "
            f"keywords={keywords[:3]}"
        )

    def stop(self) -> None:
        """수집 중지 요청"""
        self._stop_flag = True

    def run(self) -> None:
        """백그라운드 수집 실행 (QThread.start() 에서 호출)"""
        self._stop_flag = False
        try:
            if self.source == "news":
                self._run_news()
            elif self.source == "twitter":
                self._run_twitter()
            elif self.source == "reddit":
                self._run_reddit()
            else:
                msg = f"Unknown source: {self.source}"
                logger.error(msg)
                if _HAS_QT:
                    self.error_occurred.emit(msg)
        except Exception as e:
            logger.error(f"ScrapingWorker error: {e}")
            if _HAS_QT:
                self.error_occurred.emit(str(e))
        finally:
            if _HAS_QT:
                self.finished_scraping.emit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_news(self) -> None:
        """뉴스 수집 실행"""
        if _HAS_QT:
            self.progress.emit(0, "뉴스 수집 시작...")
        try:
            from ..logic.news_scraper import NewsScraper
            import asyncio

            scraper = NewsScraper(keywords=self.keywords)
            articles = scraper.scrape_sync(
                keywords=self.keywords,
                max_articles=self.max_items,
            )
            for i, article in enumerate(articles):
                if self._stop_flag:
                    break
                if _HAS_QT:
                    self.data_received.emit(
                        {
                            "source": "news",
                            "data": article,
                            "index": i,
                            "total": len(articles),
                        }
                    )
                    pct = int((i + 1) / max(len(articles), 1) * 100)
                    self.progress.emit(pct, f"뉴스 수집 중... {i+1}/{len(articles)}")
        except Exception as e:
            logger.error(f"News scraping failed: {e}")
            if _HAS_QT:
                self.error_occurred.emit(str(e))

    def _run_twitter(self) -> None:
        """트위터 수집 실행"""
        if _HAS_QT:
            self.progress.emit(0, "트위터 수집 시작...")
        try:
            from ..logic.twitter_scraper import TwitterScraper

            scraper = TwitterScraper(keywords=self.keywords)
            tweets = scraper.scrape(
                keywords=self.keywords,
                max_tweets=self.max_items,
            )
            for i, tweet in enumerate(tweets):
                if self._stop_flag:
                    break
                if _HAS_QT:
                    self.data_received.emit(
                        {
                            "source": "twitter",
                            "data": tweet,
                            "index": i,
                            "total": len(tweets),
                        }
                    )
                    pct = int((i + 1) / max(len(tweets), 1) * 100)
                    self.progress.emit(pct, f"트위터 수집 중... {i+1}/{len(tweets)}")
        except Exception as e:
            logger.error(f"Twitter scraping failed: {e}")
            if _HAS_QT:
                self.error_occurred.emit(str(e))

    def _run_reddit(self) -> None:
        """Reddit 수집 실행"""
        if _HAS_QT:
            self.progress.emit(0, "Reddit 수집 시작...")
        try:
            from ..logic.reddit_scraper import RedditScraper

            scraper = RedditScraper(keywords=self.keywords)
            posts = scraper.scrape(
                keywords=self.keywords,
                limit=self.max_items,
            )
            for i, post in enumerate(posts):
                if self._stop_flag:
                    break
                if _HAS_QT:
                    self.data_received.emit(
                        {
                            "source": "reddit",
                            "data": post,
                            "index": i,
                            "total": len(posts),
                        }
                    )
                    pct = int((i + 1) / max(len(posts), 1) * 100)
                    self.progress.emit(pct, f"Reddit 수집 중... {i+1}/{len(posts)}")
        except Exception as e:
            logger.error(f"Reddit scraping failed: {e}")
            if _HAS_QT:
                self.error_occurred.emit(str(e))
