#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
News Scraper

뉴스 수집 모듈 - Bloomberg, Reuters, 네이버 뉴스 등 다중 소스 지원
기존 ingest/crawler_news.py 의 NewsCrawler를 래핑합니다.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NewsScraper:
    """
    뉴스 수집기

    Bloomberg, Reuters, 네이버 뉴스 등 다중 소스에서
    암호화폐 관련 뉴스 기사를 수집합니다.
    """

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        language: str = "en",
    ):
        """
        Initialize NewsScraper

        Args:
            sources: 뉴스 소스 URL 리스트
            keywords: 검색 키워드 리스트
            language: 수집 언어 ('en'|'ko')
        """
        self.sources = sources or [
            "https://newsapi.org/v2/everything",
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.reuters.com/reuters/businessNews",
        ]
        self.keywords = keywords or ["bitcoin", "ethereum", "crypto"]
        self.language = language
        self._crawler = None
        self._initialize_crawler()

        logger.info(
            f"NewsScraper initialized: {len(self.sources)} sources, "
            f"{len(self.keywords)} keywords"
        )

    def _initialize_crawler(self) -> None:
        """내부 크롤러 초기화"""
        try:
            from ..ingest.crawler_news import NewsCrawler

            self._crawler = NewsCrawler(
                sources=self.sources,
                keywords=self.keywords,
                language=self.language,
            )
        except Exception as e:
            logger.warning(f"NewsCrawler unavailable, using stub: {e}")
            self._crawler = None

    async def scrape(
        self,
        keywords: Optional[List[str]] = None,
        max_articles: int = 100,
    ) -> List[Dict]:
        """
        뉴스 기사 수집

        Args:
            keywords: 검색 키워드 (None이면 기본값 사용)
            max_articles: 최대 수집 기사 수

        Returns:
            기사 딕셔너리 리스트
        """
        kw = keywords or self.keywords
        if self._crawler is not None:
            try:
                return await self._crawler.crawl(
                    keywords=kw,
                    max_articles=max_articles,
                    language=self.language,
                )
            except Exception as e:
                logger.error(f"Crawl failed: {e}")
                return []
        return self._stub_articles(kw, max_articles)

    def scrape_sync(
        self,
        keywords: Optional[List[str]] = None,
        max_articles: int = 100,
    ) -> List[Dict]:
        """
        동기 방식 뉴스 기사 수집

        Args:
            keywords: 검색 키워드 (None이면 기본값 사용)
            max_articles: 최대 수집 기사 수

        Returns:
            기사 딕셔너리 리스트
        """
        import asyncio

        kw = keywords or self.keywords
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.scrape(kw, max_articles))
                    return future.result()
            return loop.run_until_complete(self.scrape(kw, max_articles))
        except Exception as e:
            logger.error(f"Sync scrape failed: {e}")
            return self._stub_articles(kw, max_articles)

    def _stub_articles(
        self, keywords: List[str], max_articles: int
    ) -> List[Dict]:
        """크롤러 없을 때 더미 기사 반환"""
        return [
            {
                "title": f"[STUB] {kw} news",
                "source": "stub",
                "url": "",
                "published_at": datetime.now().isoformat(),
                "content": f"Stub article for keyword: {kw}",
                "sentiment": None,
            }
            for kw in keywords[:max_articles]
        ]
