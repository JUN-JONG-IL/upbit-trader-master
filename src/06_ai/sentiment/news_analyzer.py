#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NewsSentimentAnalyzer - Financial News Sentiment Analysis

Fetches news from RSS/API sources and scores each article using
pre-trained NLP models (FinBERT / transformers pipeline).  Aggregates
article-level scores into symbol-level sentiment metrics with a
configurable time-weighted rolling window.

Supports Korean and English news.  Falls back to keyword-based scoring
when the transformers library is unavailable.

Latency target: P95 < 500 ms.
"""

import asyncio
import hashlib
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


class NewsSentimentAnalyzer:
    """
    Financial news sentiment analyser.

    Pipeline:
    1. Fetch articles from configured RSS/API feeds.
    2. Deduplicate by URL hash.
    3. Extract relevant keywords for the target symbol.
    4. Score each article using FinBERT (English) or a keyword lexicon.
    5. Aggregate scores with exponential time weighting.

    Example::

        analyzer = NewsSentimentAnalyzer()
        result = await analyzer.analyze("BTC/KRW")
        print(result["sentiment_score"])   # -1 … +1
    """

    # Simple financial keyword lexicons for fallback scoring
    _POSITIVE_KEYWORDS = frozenset([
        "bull", "bullish", "rally", "surge", "gain", "rise", "up", "high",
        "growth", "positive", "breakout", "record", "buy", "support",
        "approval", "adoption", "institutional", "investment",
        "상승", "급등", "호재", "매수", "돌파", "상승세",
    ])
    _NEGATIVE_KEYWORDS = frozenset([
        "bear", "bearish", "crash", "drop", "fall", "decline", "down", "low",
        "sell", "negative", "loss", "regulation", "ban", "hack", "scam",
        "fraud", "dump", "fear",
        "하락", "급락", "악재", "매도", "규제", "금지",
    ])

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        max_articles: int = 50,
        window_hours: int = 24,
        rss_feeds: Optional[List[str]] = None,
    ):
        """
        Args:
            model_name: HuggingFace model for sentiment scoring.
            max_articles: Maximum number of articles to process per call.
            window_hours: Rolling window for score aggregation.
            rss_feeds: Additional RSS feed URLs to poll.
        """
        self.model_name = model_name
        self.max_articles = max_articles
        self.window_hours = window_hours
        self.rss_feeds = rss_feeds or []

        self._nlp_pipeline: Optional[Any] = None
        self._article_cache: Dict[str, Dict[str, Any]] = {}  # hash → article

        if TRANSFORMERS_AVAILABLE:
            self._load_nlp_pipeline()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch and analyse news sentiment for *symbol*.

        Args:
            symbol: Trading pair, e.g. ``"BTC/KRW"``.

        Returns:
            ::

                {
                    "symbol": str,
                    "timestamp": str,
                    "sentiment_score": float,   # -1 … +1
                    "confidence": float,        # 0 … 1
                    "articles": [...],
                    "aggregated_metrics": {
                        "1h_sentiment": float,
                        "24h_sentiment": float,
                        "news_volume": int,
                        "major_events": [str, ...],
                    },
                }
        """
        coin = symbol.split("/")[0].upper()
        articles = await self._fetch_articles(coin)
        scored = self._score_articles(articles)
        aggregated = self._aggregate(scored)

        return {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "sentiment_score": aggregated["score_24h"],
            "confidence": aggregated["confidence"],
            "articles": scored[: self.max_articles],
            "aggregated_metrics": {
                "1h_sentiment": aggregated["score_1h"],
                "24h_sentiment": aggregated["score_24h"],
                "news_volume": len(scored),
                "major_events": aggregated["major_events"],
            },
        }

    async def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Score an arbitrary text snippet.

        Args:
            text: Input text (English or Korean).

        Returns:
            Dict with ``sentiment`` (-1 … +1) and ``confidence``.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._score_text, text)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _fetch_articles(self, coin: str) -> List[Dict[str, Any]]:
        """Fetch articles from all configured sources."""
        articles: List[Dict[str, Any]] = []

        for feed_url in self.rss_feeds:
            try:
                feed_articles = await self._fetch_rss(feed_url, coin)
                articles.extend(feed_articles)
            except Exception as exc:
                logger.debug("RSS fetch failed (%s): %s", feed_url, exc)

        # Remove duplicates
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for article in articles:
            h = hashlib.md5(article.get("url", article.get("title", "")).encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique.append(article)

        return unique[: self.max_articles]

    async def _fetch_rss(self, url: str, keyword: str) -> List[Dict[str, Any]]:
        """Fetch and parse an RSS feed, returning keyword-relevant items."""
        if not AIOHTTP_AVAILABLE:
            return []
        articles: List[Dict[str, Any]] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return articles
                    text = await resp.text()

            import xml.etree.ElementTree as ET
            root = ET.fromstring(text)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")

                title = title_el.text if title_el is not None else ""
                if keyword.lower() not in title.lower():
                    continue

                articles.append({
                    "title": title,
                    "url": link_el.text if link_el is not None else "",
                    "description": desc_el.text if desc_el is not None else "",
                    "published_at": pub_el.text if pub_el is not None else "",
                    "source": url,
                })
        except Exception as exc:
            logger.debug("RSS parse error: %s", exc)
        return articles

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_articles(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')}"
            scores = self._score_text(text)
            article["sentiment"] = scores["sentiment"]
            article["confidence"] = scores["confidence"]
            article["keywords"] = self._extract_keywords(text)
            scored.append(article)
        return scored

    def _score_text(self, text: str) -> Dict[str, float]:
        """Score a text string using NLP pipeline or keyword fallback."""
        if self._nlp_pipeline is not None:
            try:
                result = self._nlp_pipeline(text[:512], truncation=True)
                label = result[0]["label"].lower()
                score = result[0]["score"]
                if label == "positive":
                    return {"sentiment": score, "confidence": score}
                elif label == "negative":
                    return {"sentiment": -score, "confidence": score}
                return {"sentiment": 0.0, "confidence": score}
            except Exception as exc:
                logger.debug("NLP pipeline failed: %s", exc)

        return self._keyword_score(text)

    def _keyword_score(self, text: str) -> Dict[str, float]:
        words = set(text.lower().split())
        pos = len(words & self._POSITIVE_KEYWORDS)
        neg = len(words & self._NEGATIVE_KEYWORDS)
        total = pos + neg
        if total == 0:
            return {"sentiment": 0.0, "confidence": 0.3}
        sentiment = (pos - neg) / total
        confidence = min(total / 5.0, 1.0)
        return {"sentiment": float(sentiment), "confidence": float(confidence)}

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        cutoff_1h = now - timedelta(hours=1)
        cutoff_24h = now - timedelta(hours=self.window_hours)

        def parse_ts(s: str) -> Optional[datetime]:
            for fmt in (
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%SZ",
            ):
                try:
                    return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            return None

        def weighted_avg(
            items: List[Dict[str, Any]], cutoff: datetime
        ) -> float:
            scores, weights = [], []
            for a in items:
                ts = parse_ts(str(a.get("published_at", "")))
                if ts and ts >= cutoff:
                    age_h = max((now - ts).total_seconds() / 3600, 0.01)
                    w = np.exp(-0.1 * age_h)
                    scores.append(a["sentiment"])
                    weights.append(w)
            if not scores:
                return 0.0
            return float(np.average(scores, weights=weights))

        score_1h = weighted_avg(articles, cutoff_1h)
        score_24h = weighted_avg(articles, cutoff_24h)

        # Major events: articles with large absolute sentiment
        major_events = [
            a["title"]
            for a in articles
            if abs(a.get("sentiment", 0)) > 0.7 and a.get("confidence", 0) > 0.6
        ]

        avg_confidence = float(np.mean([a.get("confidence", 0.5) for a in articles])) if articles else 0.0

        return {
            "score_1h": round(score_1h, 4),
            "score_24h": round(score_24h, 4),
            "confidence": round(avg_confidence, 4),
            "major_events": major_events[:5],
        }

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        financial_terms = {
            "bitcoin", "ethereum", "crypto", "blockchain", "defi", "nft",
            "regulation", "sec", "etf", "institutional", "adoption", "halving",
            "비트코인", "이더리움", "암호화폐", "블록체인",
        }
        words = set(text.lower().split())
        return list(words & financial_terms)[:10]

    # ------------------------------------------------------------------
    # NLP model loading
    # ------------------------------------------------------------------

    def _load_nlp_pipeline(self) -> None:
        try:
            self._nlp_pipeline = transformers_pipeline(
                "sentiment-analysis",
                model=self.model_name,
            )
            logger.info("NLP pipeline loaded: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "Failed to load NLP model '%s' (%s); using keyword fallback",
                self.model_name,
                exc,
            )
            self._nlp_pipeline = None
