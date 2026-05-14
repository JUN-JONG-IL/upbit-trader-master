"""
News Crawler - Crawls news articles from various sources
"""

import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class NewsCrawler:
    """Crawls news articles from configured sources"""
    
    def __init__(self, sources: Optional[List[str]] = None, keywords: Optional[List[str]] = None, language: str = "en"):
        self.sources = sources or [
            "https://api.example.com/crypto-news",
            "https://newsapi.org/v2/everything"
        ]
        self.crawled_articles = []
        self.keywords = keywords or ['bitcoin']
        self.language = language
        self._running = False
        self.callback = None
        self._crawl_task = None  # Store the asyncio task reference
    
    async def crawl(
        self,
        keywords: List[str],
        max_articles: int = 100,
        language: str = "en"
    ) -> List[Dict]:
        """
        Crawl news articles
        
        Args:
            keywords: Keywords to search for
            max_articles: Maximum number of articles to fetch
            language: Language filter (en, ko, ja)
            
        Returns:
            List of article dictionaries
        """
        logger.info(f"Crawling news for keywords: {keywords}, language: {language}")
        
        articles = []
        
        for source in self.sources:
            source_articles = await self._crawl_source(
                source,
                keywords,
                max_articles // len(self.sources),
                language
            )
            articles.extend(source_articles)
        
        # Deduplicate
        articles = self._deduplicate(articles)
        
        self.crawled_articles.extend(articles)
        
        logger.info(f"Crawled {len(articles)} unique articles")
        
        return articles
    
    async def _crawl_source(
        self,
        source: str,
        keywords: List[str],
        max_articles: int,
        language: str
    ) -> List[Dict]:
        """
        Crawl a specific news source
        
        Args:
            source: Source URL
            keywords: Keywords to search
            max_articles: Max articles from this source
            language: Language filter
            
        Returns:
            List of articles
        """
        # Mock implementation - in production, would make actual HTTP requests
        articles = []
        
        for i in range(min(max_articles, 10)):  # Mock: return up to 10 articles
            article = {
                "id": hashlib.md5(f"{source}-{i}".encode()).hexdigest(),
                "source": source,
                "title": f"Mock Article {i} about {' '.join(keywords)}",
                "content": f"This is mock content about {' '.join(keywords)}. " * 10,
                "url": f"{source}/article-{i}",
                "published_at": datetime.now().isoformat(),
                "language": language,
                "keywords": keywords
            }
            articles.append(article)
        
        return articles
    
    def _deduplicate(self, articles: List[Dict]) -> List[Dict]:
        """
        Remove duplicate articles
        
        Args:
            articles: List of articles
            
        Returns:
            Deduplicated list
        """
        seen_ids = set()
        unique_articles = []
        
        for article in articles:
            article_id = article.get("id") or article.get("url")
            if article_id not in seen_ids:
                seen_ids.add(article_id)
                unique_articles.append(article)
        
        return unique_articles
    
    def get_crawled_count(self) -> int:
        """Get number of crawled articles"""
        return len(self.crawled_articles)
    
    def clear_cache(self):
        """Clear crawled articles cache"""
        self.crawled_articles = []
        logger.info("Cleared article cache")
    
    def set_callback(self, callback):
        """
        콜백 함수 설정
        
        Args:
            callback: 크롤링된 기사마다 호출될 콜백 함수
        """
        self.callback = callback
    
    def start(self):
        """
        크롤러 시작 (비동기)
        백그라운드에서 크롤링 루프를 시작합니다.
        """
        if not self._running:
            self._running = True
            # asyncio 이벤트 루프에서 크롤링 태스크 시작
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 백그라운드 태스크로 크롤링 루프 시작하고 참조 저장
            self._crawl_task = asyncio.ensure_future(self._crawl_loop())
            logger.info("News crawler started")
    
    async def _crawl_loop(self):
        """
        크롤링 루프
        주기적으로 뉴스를 크롤링하고 콜백을 호출합니다.
        """
        while self._running:
            try:
                articles = await self.crawl(
                    keywords=self.keywords,
                    max_articles=10,
                    language=self.language
                )
                
                # 콜백 호출
                for article in articles:
                    if self.callback:
                        self.callback(article)
                
                # 1분 대기
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in crawl loop: {e}")
                await asyncio.sleep(10)  # 오류 발생 시 10초 대기
    
    def stop(self):
        """
        크롤러 중지
        실행 중인 태스크를 취소하고 정리합니다.
        """
        self._running = False
        
        # 실행 중인 태스크 취소
        if self._crawl_task and not self._crawl_task.done():
            self._crawl_task.cancel()
            self._crawl_task = None
        
        logger.info("News crawler stopped")

