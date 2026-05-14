#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter Scraper

트위터/X 소셜 미디어 수집 모듈
기존 ingest/stream_twitter.py 의 TwitterStreamer를 래핑합니다.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TwitterScraper:
    """
    트위터/X 수집기

    트위터 API를 통해 암호화폐 관련 트윗을 실시간 수집합니다.
    팔로워, 리트윗 수 등 영향력 메타데이터도 함께 수집합니다.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ):
        """
        Initialize TwitterScraper

        Args:
            api_key: Twitter API 키
            api_secret: Twitter API 시크릿
            keywords: 수집 키워드 리스트
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.keywords = keywords or ["bitcoin", "BTC", "crypto"]
        self._streamer = None
        self._initialize_streamer()

        logger.info(
            f"TwitterScraper initialized: {len(self.keywords)} keywords"
        )

    def _initialize_streamer(self) -> None:
        """내부 스트리머 초기화"""
        try:
            from ..ingest.stream_twitter import TwitterStreamer

            self._streamer = TwitterStreamer(
                api_key=self.api_key,
                api_secret=self.api_secret,
                keywords=self.keywords,
            )
        except Exception as e:
            logger.warning(f"TwitterStreamer unavailable, using stub: {e}")
            self._streamer = None

    def scrape(
        self,
        keywords: Optional[List[str]] = None,
        max_tweets: int = 100,
    ) -> List[Dict]:
        """
        트윗 수집

        Args:
            keywords: 검색 키워드 (None이면 기본값 사용)
            max_tweets: 최대 수집 트윗 수

        Returns:
            트윗 딕셔너리 리스트
                - text: str
                - author: str
                - followers_count: int
                - retweet_count: int
                - like_count: int
                - is_verified: bool
                - created_at: str (ISO 8601)
        """
        kw = keywords or self.keywords
        if self._streamer is not None:
            try:
                return self._streamer.search(keywords=kw, max_results=max_tweets)
            except Exception as e:
                logger.error(f"Twitter scrape failed: {e}")
                return []
        return self._stub_tweets(kw, max_tweets)

    def _stub_tweets(
        self, keywords: List[str], max_tweets: int
    ) -> List[Dict]:
        """스트리머 없을 때 더미 트윗 반환"""
        return [
            {
                "text": f"[STUB] #{kw} tweet",
                "author": "stub_user",
                "followers_count": 0,
                "retweet_count": 0,
                "like_count": 0,
                "is_verified": False,
                "created_at": datetime.now().isoformat(),
                "sentiment": None,
            }
            for kw in keywords[:max_tweets]
        ]
