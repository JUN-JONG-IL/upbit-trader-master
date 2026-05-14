#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reddit Scraper

Reddit 서브레딧 수집 모듈
r/CryptoCurrency, r/Bitcoin 등 관련 서브레딧의 포스트 및 댓글을 수집합니다.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RedditScraper:
    """
    Reddit 수집기

    PRAW(Python Reddit API Wrapper)를 통해
    암호화폐 관련 서브레딧의 게시물 및 댓글을 수집합니다.
    """

    DEFAULT_SUBREDDITS = [
        "CryptoCurrency",
        "Bitcoin",
        "ethereum",
        "CryptoMarkets",
    ]

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: str = "upbit-trader-sentiment/1.0",
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ):
        """
        Initialize RedditScraper

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: API 요청 User-Agent
            subreddits: 수집할 서브레딧 리스트
            keywords: 필터 키워드 리스트
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS
        self.keywords = keywords or ["bitcoin", "BTC", "crypto"]
        self._reddit = None
        self._initialize_client()

        logger.info(
            f"RedditScraper initialized: subreddits={self.subreddits}"
        )

    def _initialize_client(self) -> None:
        """PRAW 클라이언트 초기화"""
        if not (self.client_id and self.client_secret):
            logger.warning("Reddit credentials not provided, using stub mode")
            return
        try:
            import praw

            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
            logger.info("PRAW Reddit client initialized")
        except ImportError:
            logger.warning("praw not installed, using stub mode")
        except Exception as e:
            logger.error(f"Failed to init Reddit client: {e}")

    def scrape(
        self,
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        limit: int = 100,
        sort: str = "new",
    ) -> List[Dict]:
        """
        Reddit 게시물 수집

        Args:
            subreddits: 수집할 서브레딧 (None이면 기본값)
            keywords: 필터 키워드 (None이면 모두 수집)
            limit: 서브레딧당 최대 게시물 수
            sort: 정렬 방식 ('new'|'hot'|'top')

        Returns:
            게시물 딕셔너리 리스트
                - title: str
                - text: str
                - subreddit: str
                - author: str
                - score: int (upvotes - downvotes)
                - num_comments: int
                - created_at: str (ISO 8601)
                - url: str
        """
        subs = subreddits or self.subreddits
        kw = keywords or self.keywords

        if self._reddit is None:
            return self._stub_posts(subs, kw, limit)

        posts: List[Dict] = []
        for sub_name in subs:
            try:
                subreddit = self._reddit.subreddit(sub_name)
                if sort == "new":
                    submissions = subreddit.new(limit=limit)
                elif sort == "hot":
                    submissions = subreddit.hot(limit=limit)
                else:
                    submissions = subreddit.top(limit=limit)

                for submission in submissions:
                    post_text = (
                        f"{submission.title} {submission.selftext}"
                    ).lower()
                    if kw and not any(k.lower() in post_text for k in kw):
                        continue
                    posts.append(
                        {
                            "title": submission.title,
                            "text": submission.selftext,
                            "subreddit": sub_name,
                            "author": str(submission.author),
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                            "created_at": datetime.fromtimestamp(
                                submission.created_utc
                            ).isoformat(),
                            "url": submission.url,
                            "sentiment": None,
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to scrape r/{sub_name}: {e}")

        logger.info(f"Scraped {len(posts)} Reddit posts")
        return posts

    def _stub_posts(
        self,
        subreddits: List[str],
        keywords: List[str],
        limit: int,
    ) -> List[Dict]:
        """Reddit 클라이언트 없을 때 더미 게시물 반환"""
        posts = []
        for sub in subreddits[:limit]:
            for kw in keywords[:3]:
                posts.append(
                    {
                        "title": f"[STUB] {kw} discussion in r/{sub}",
                        "text": f"Stub post for {kw}",
                        "subreddit": sub,
                        "author": "stub_user",
                        "score": 0,
                        "num_comments": 0,
                        "created_at": datetime.now().isoformat(),
                        "url": "",
                        "sentiment": None,
                    }
                )
        return posts
