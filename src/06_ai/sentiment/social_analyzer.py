#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SocialSentimentAnalyzer - Social Media Sentiment Analysis

Aggregates real-time sentiment from Twitter/X and Reddit for a given
cryptocurrency symbol.  Uses the transformers library for NLP scoring
and falls back gracefully to keyword-based scoring when unavailable.

Features:
- Influencer weighting by follower count / karma
- Hashtag trending detection
- Coordinated activity alerts (potential pump & dump)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from transformers import pipeline as transformers_pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class SocialSentimentAnalyzer:
    """
    Social media sentiment analyser for crypto trading signals.

    Pulls posts/comments from Twitter and Reddit, scores them with an
    NLP model or keyword lexicon, and computes aggregated metrics
    including coordinated-activity detection.

    Example::

        analyzer = SocialSentimentAnalyzer(
            twitter_bearer_token="...",
            reddit_client_id="...",
            reddit_client_secret="...",
        )
        result = await analyzer.analyze("BTC/KRW")
        print(result["sentiment_score"])
    """

    _POSITIVE_KEYWORDS = frozenset([
        "moon", "bull", "buy", "long", "hodl", "pump", "breakout",
        "bullish", "rally", "gain", "profit", "ath",
    ])
    _NEGATIVE_KEYWORDS = frozenset([
        "crash", "dump", "sell", "short", "bear", "rekt", "scam",
        "bearish", "drop", "rug", "fraud", "ban", "hack",
    ])

    def __init__(
        self,
        twitter_bearer_token: Optional[str] = None,
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
        reddit_user_agent: str = "upbit-trader/1.0",
        model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest",
        max_posts: int = 200,
        window_hours: int = 24,
    ):
        """
        Args:
            twitter_bearer_token: Bearer token for the Twitter v2 API.
            reddit_client_id: Reddit API client ID.
            reddit_client_secret: Reddit API client secret.
            reddit_user_agent: HTTP User-Agent for Reddit requests.
            model_name: HuggingFace model for social media NLP.
            max_posts: Maximum posts to analyse per call.
            window_hours: Aggregation time window.
        """
        self.twitter_bearer_token = twitter_bearer_token
        self.reddit_client_id = reddit_client_id
        self.reddit_client_secret = reddit_client_secret
        self.reddit_user_agent = reddit_user_agent
        self.model_name = model_name
        self.max_posts = max_posts
        self.window_hours = window_hours

        self._nlp_pipeline: Optional[Any] = None
        if TRANSFORMERS_AVAILABLE:
            self._load_nlp_pipeline()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        Analyse social sentiment for *symbol*.

        Args:
            symbol: Trading pair, e.g. ``"BTC/KRW"``.

        Returns:
            ::

                {
                    "symbol": str,
                    "timestamp": str,
                    "sentiment_score": float,         # -1 … +1
                    "confidence": float,
                    "post_count": int,
                    "source_breakdown": {
                        "twitter": float,
                        "reddit": float,
                    },
                    "trending_hashtags": [str, ...],
                    "coordinated_activity_alert": bool,
                    "influencer_sentiment": float,
                }
        """
        coin = symbol.split("/")[0].upper()
        posts = await self._fetch_posts(coin)
        scored = self._score_posts(posts)
        aggregated = self._aggregate(scored)

        return {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "sentiment_score": aggregated["overall_score"],
            "confidence": aggregated["confidence"],
            "post_count": len(scored),
            "source_breakdown": {
                "twitter": aggregated["twitter_score"],
                "reddit": aggregated["reddit_score"],
            },
            "trending_hashtags": aggregated["trending_hashtags"],
            "coordinated_activity_alert": aggregated["coordinated_alert"],
            "influencer_sentiment": aggregated["influencer_score"],
        }

    async def get_trending(self, symbols: List[str]) -> Dict[str, float]:
        """
        Return a social-score ranking for a list of symbols.

        Args:
            symbols: List of trading pairs.

        Returns:
            Mapping of symbol → sentiment score.
        """
        results: Dict[str, float] = {}
        for symbol in symbols:
            try:
                r = await self.analyze(symbol)
                results[symbol] = r["sentiment_score"]
            except Exception as exc:
                logger.debug("analyze failed for %s: %s", symbol, exc)
                results[symbol] = 0.0
        return results

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _fetch_posts(self, coin: str) -> List[Dict[str, Any]]:
        posts: List[Dict[str, Any]] = []

        if self.twitter_bearer_token:
            try:
                twitter_posts = await self._fetch_twitter(coin)
                posts.extend(twitter_posts)
            except Exception as exc:
                logger.debug("Twitter fetch failed: %s", exc)

        if self.reddit_client_id and self.reddit_client_secret:
            try:
                reddit_posts = await self._fetch_reddit(coin)
                posts.extend(reddit_posts)
            except Exception as exc:
                logger.debug("Reddit fetch failed: %s", exc)

        return posts[: self.max_posts]

    async def _fetch_twitter(self, coin: str) -> List[Dict[str, Any]]:
        """Fetch recent tweets mentioning *coin*."""
        if not AIOHTTP_AVAILABLE:
            return []
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {self.twitter_bearer_token}"}
        params = {
            "query": f"#{coin} OR ${coin} lang:en -is:retweet",
            "max_results": min(self.max_posts, 100),
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "public_metrics",
        }
        posts: List[Dict[str, Any]] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return posts
                    data = await resp.json()

            users = {
                u["id"]: u
                for u in data.get("includes", {}).get("users", [])
            }
            for tweet in data.get("data", []):
                uid = tweet.get("author_id", "")
                user = users.get(uid, {})
                followers = (
                    user.get("public_metrics", {}).get("followers_count", 0)
                )
                posts.append({
                    "text": tweet.get("text", ""),
                    "source": "twitter",
                    "created_at": tweet.get("created_at", ""),
                    "follower_count": followers,
                    "engagement": (
                        tweet.get("public_metrics", {}).get("like_count", 0)
                        + tweet.get("public_metrics", {}).get("retweet_count", 0)
                    ),
                })
        except Exception as exc:
            logger.debug("Twitter API error: %s", exc)
        return posts

    async def _fetch_reddit(self, coin: str) -> List[Dict[str, Any]]:
        """Fetch recent Reddit posts from crypto subreddits."""
        if not AIOHTTP_AVAILABLE:
            return []
        subreddits = ["cryptocurrency", "bitcoin", "CryptoMarkets", coin.lower()]
        posts: List[Dict[str, Any]] = []
        headers = {"User-Agent": self.reddit_user_agent}

        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/new.json"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        params={"limit": 25},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                for child in data.get("data", {}).get("children", []):
                    d = child.get("data", {})
                    title = d.get("title", "")
                    if coin.lower() not in title.lower():
                        continue
                    posts.append({
                        "text": f"{title} {d.get('selftext', '')}",
                        "source": "reddit",
                        "created_at": str(d.get("created_utc", "")),
                        "follower_count": d.get("author_flair_richtext", 0),
                        "engagement": d.get("score", 0) + d.get("num_comments", 0),
                        "karma": d.get("score", 0),
                    })
            except Exception as exc:
                logger.debug("Reddit fetch error for r/%s: %s", sub, exc)

        return posts

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_posts(
        self, posts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for post in posts:
            s = self._score_text(post.get("text", ""))
            post["sentiment"] = s["sentiment"]
            post["confidence"] = s["confidence"]
            scored.append(post)
        return scored

    def _score_text(self, text: str) -> Dict[str, float]:
        if self._nlp_pipeline is not None:
            try:
                result = self._nlp_pipeline(text[:256], truncation=True)
                label = result[0]["label"].lower()
                score = result[0]["score"]
                mapping = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
                direction = mapping.get(label, 0.0)
                return {"sentiment": float(direction * score), "confidence": float(score)}
            except Exception as exc:
                logger.debug("NLP pipeline error: %s", exc)

        return self._keyword_score(text)

    def _keyword_score(self, text: str) -> Dict[str, float]:
        words = set(text.lower().split())
        pos = len(words & self._POSITIVE_KEYWORDS)
        neg = len(words & self._NEGATIVE_KEYWORDS)
        total = pos + neg
        if total == 0:
            return {"sentiment": 0.0, "confidence": 0.2}
        sentiment = (pos - neg) / total
        confidence = min(total / 5.0, 0.8)
        return {"sentiment": float(sentiment), "confidence": float(confidence)}

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not posts:
            return {
                "overall_score": 0.0,
                "twitter_score": 0.0,
                "reddit_score": 0.0,
                "confidence": 0.0,
                "trending_hashtags": [],
                "coordinated_alert": False,
                "influencer_score": 0.0,
            }

        twitter = [p for p in posts if p.get("source") == "twitter"]
        reddit = [p for p in posts if p.get("source") == "reddit"]

        def avg_sentiment(items: List[Dict[str, Any]]) -> float:
            if not items:
                return 0.0
            return float(np.mean([p["sentiment"] for p in items]))

        # Influencer weighting: follower_count as weight
        inf_scores, inf_weights = [], []
        for p in posts:
            followers = p.get("follower_count", 0)
            if isinstance(followers, int) and followers > 1000:
                inf_scores.append(p["sentiment"])
                inf_weights.append(float(followers))

        influencer_score = (
            float(np.average(inf_scores, weights=inf_weights))
            if inf_scores else avg_sentiment(posts)
        )

        # Overall weighted score (engagement-weighted)
        engagements = [max(float(p.get("engagement", 1)), 1.0) for p in posts]
        overall = float(
            np.average([p["sentiment"] for p in posts], weights=engagements)
        )

        # Coordinated activity: many posts in a short time window using sliding window
        timestamps = []
        for p in posts:
            ts_raw = p.get("created_at", "")
            try:
                timestamps.append(float(ts_raw))
            except Exception:
                pass
        coordinated = False
        if len(timestamps) > 10:
            timestamps_sorted = sorted(timestamps)
            window_size = 60  # seconds
            left = 0
            for right in range(len(timestamps_sorted)):
                # Shrink window from the left
                while timestamps_sorted[right] - timestamps_sorted[left] > window_size:
                    left += 1
                burst = right - left + 1
                if burst > len(posts) * 0.5:
                    coordinated = True
                    break

        # Trending hashtags from Twitter text
        hashtag_counts: Dict[str, int] = {}
        for p in twitter:
            for word in p.get("text", "").split():
                if word.startswith("#") and len(word) > 2:
                    hashtag_counts[word] = hashtag_counts.get(word, 0) + 1
        trending = sorted(hashtag_counts, key=hashtag_counts.get, reverse=True)[:5]  # type: ignore[arg-type]

        confidence = float(np.mean([p.get("confidence", 0.5) for p in posts]))

        return {
            "overall_score": round(overall, 4),
            "twitter_score": round(avg_sentiment(twitter), 4),
            "reddit_score": round(avg_sentiment(reddit), 4),
            "confidence": round(confidence, 4),
            "trending_hashtags": trending,
            "coordinated_alert": coordinated,
            "influencer_score": round(influencer_score, 4),
        }

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_nlp_pipeline(self) -> None:
        try:
            self._nlp_pipeline = transformers_pipeline(
                "sentiment-analysis",
                model=self.model_name,
            )
            logger.info("Social NLP pipeline loaded: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "Failed to load social NLP model '%s' (%s); using keyword fallback",
                self.model_name,
                exc,
            )
            self._nlp_pipeline = None
