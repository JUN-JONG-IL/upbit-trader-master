#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Analysis Logic

Business logic for sentiment analysis including:
- News scraping and analysis
- Twitter/X social media monitoring
- Reddit community sentiment
- Multi-source aggregation
- Real-time sentiment calculation
"""

import os
import logging
import threading
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class SentimentLogic(QObject):
    """
    Sentiment Analysis Business Logic
    
    Handles multi-source sentiment scraping and analysis
    """
    
    # Signal definitions
    signal_news_data = pyqtSignal(dict)
    signal_twitter_data = pyqtSignal(dict)
    signal_reddit_data = pyqtSignal(dict)
    signal_sentiment_updated = pyqtSignal(dict)
    signal_error = pyqtSignal(str)
    
    def __init__(self):
        """Initialize Sentiment Logic"""
        super().__init__()
        
        # Scraping state
        self.is_news_running = False
        self.is_twitter_running = False
        self.is_reddit_running = False
        
        # Threading
        self.news_thread = None
        self.twitter_thread = None
        self.reddit_thread = None
        self._stop_event = threading.Event()
        
        # Filters
        self.filters = {
            'news': True,
            'twitter': True,
            'reddit': True
        }
        
        # Update interval (seconds)
        self.update_interval = 60
        
        # Data storage
        self._sentiment_data = []
        self._sentiment_history = []
        self._keywords_counter = defaultdict(int)
        
        # Sentiment aggregator
        self._current_sentiment = {
            'overall_score': 0,
            'positive': 0,
            'neutral': 0,
            'negative': 0
        }
        
        logger.info("Sentiment Logic initialized")
    
    def start_news_scraping(self):
        """Start news scraping"""
        if self.is_news_running:
            logger.warning("News scraping already running")
            return
        
        self.is_news_running = True
        self._stop_event.clear()
        
        self.news_thread = threading.Thread(
            target=self._news_scraping_loop,
            daemon=True
        )
        self.news_thread.start()
        
        logger.info("News scraping started")
    
    def start_twitter_scraping(self):
        """Start Twitter scraping"""
        if self.is_twitter_running:
            logger.warning("Twitter scraping already running")
            return
        
        self.is_twitter_running = True
        self._stop_event.clear()
        
        self.twitter_thread = threading.Thread(
            target=self._twitter_scraping_loop,
            daemon=True
        )
        self.twitter_thread.start()
        
        logger.info("Twitter scraping started")
    
    def start_reddit_scraping(self):
        """Start Reddit scraping"""
        if self.is_reddit_running:
            logger.warning("Reddit scraping already running")
            return
        
        self.is_reddit_running = True
        self._stop_event.clear()
        
        self.reddit_thread = threading.Thread(
            target=self._reddit_scraping_loop,
            daemon=True
        )
        self.reddit_thread.start()
        
        logger.info("Reddit scraping started")
    
    def stop_all_scraping(self):
        """Stop all scraping activities"""
        self._stop_event.set()
        
        self.is_news_running = False
        self.is_twitter_running = False
        self.is_reddit_running = False
        
        logger.info("All scraping stopped")
    
    def set_filters(self, filters: dict):
        """Set source filters"""
        self.filters.update(filters)
        logger.info(f"Filters updated: {self.filters}")
    
    def set_update_interval(self, seconds: int):
        """Set update interval"""
        self.update_interval = seconds
        logger.info(f"Update interval set to {seconds} seconds")
    
    # Scraping loop methods
    
    def _news_scraping_loop(self):
        """News scraping loop (placeholder)"""
        logger.info("News scraping loop started")
        
        while self.is_news_running and not self._stop_event.is_set():
            try:
                # PLACEHOLDER: Actual news scraping implementation
                # This would use libraries like:
                # - requests + BeautifulSoup for web scraping
                # - newsapi for News API integration
                # - feedparser for RSS feeds
                
                # Simulate news scraping
                news_data = self._scrape_news_placeholder()
                
                if news_data:
                    # Analyze sentiment
                    sentiment_score = self._analyze_sentiment(news_data['text'])
                    keywords = self._extract_keywords(news_data['text'])
                    
                    data = {
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'score': sentiment_score,
                        'keywords': keywords,
                        'text': news_data['text'],
                        'url': news_data.get('url', '')
                    }
                    
                    # Emit signal
                    self.signal_news_data.emit(data)
                    
                    # Update aggregated sentiment
                    self._update_sentiment(data)
                
                # Wait for next update
                self._stop_event.wait(self.update_interval)
                
            except Exception as e:
                logger.error(f"News scraping error: {e}")
                self.signal_error.emit(f"News scraping error: {e}")
                self._stop_event.wait(30)  # Wait before retry
        
        logger.info("News scraping loop stopped")
    
    def _twitter_scraping_loop(self):
        """Twitter scraping loop (placeholder)"""
        logger.info("Twitter scraping loop started")
        
        while self.is_twitter_running and not self._stop_event.is_set():
            try:
                # PLACEHOLDER: Actual Twitter scraping implementation
                # This would use libraries like:
                # - tweepy for Twitter API v2
                # - snscrape for scraping without API
                # - selenium for browser automation
                
                # Simulate Twitter scraping
                tweet_data = self._scrape_twitter_placeholder()
                
                if tweet_data:
                    # Analyze sentiment
                    sentiment_score = self._analyze_sentiment(tweet_data['text'])
                    keywords = self._extract_keywords(tweet_data['text'])
                    
                    data = {
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'score': sentiment_score,
                        'keywords': keywords,
                        'text': tweet_data['text'],
                        'username': tweet_data.get('username', '')
                    }
                    
                    # Emit signal
                    self.signal_twitter_data.emit(data)
                    
                    # Update aggregated sentiment
                    self._update_sentiment(data)
                
                # Wait for next update
                self._stop_event.wait(self.update_interval)
                
            except Exception as e:
                logger.error(f"Twitter scraping error: {e}")
                self.signal_error.emit(f"Twitter scraping error: {e}")
                self._stop_event.wait(30)  # Wait before retry
        
        logger.info("Twitter scraping loop stopped")
    
    def _reddit_scraping_loop(self):
        """Reddit scraping loop (placeholder)"""
        logger.info("Reddit scraping loop started")
        
        while self.is_reddit_running and not self._stop_event.is_set():
            try:
                # PLACEHOLDER: Actual Reddit scraping implementation
                # This would use libraries like:
                # - praw (Python Reddit API Wrapper)
                # - requests for direct API calls
                
                # Simulate Reddit scraping
                reddit_data = self._scrape_reddit_placeholder()
                
                if reddit_data:
                    # Analyze sentiment
                    sentiment_score = self._analyze_sentiment(reddit_data['text'])
                    keywords = self._extract_keywords(reddit_data['text'])
                    
                    data = {
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'score': sentiment_score,
                        'keywords': keywords,
                        'text': reddit_data['text'],
                        'subreddit': reddit_data.get('subreddit', '')
                    }
                    
                    # Emit signal
                    self.signal_reddit_data.emit(data)
                    
                    # Update aggregated sentiment
                    self._update_sentiment(data)
                
                # Wait for next update
                self._stop_event.wait(self.update_interval)
                
            except Exception as e:
                logger.error(f"Reddit scraping error: {e}")
                self.signal_error.emit(f"Reddit scraping error: {e}")
                self._stop_event.wait(30)  # Wait before retry
        
        logger.info("Reddit scraping loop stopped")
    
    # Placeholder scraping methods (to be replaced with actual implementations)
    
    def _scrape_news_placeholder(self) -> Optional[dict]:
        """
        Placeholder for news scraping
        
        TO DO: Implement actual news scraping using:
        - News API (https://newsapi.org/)
        - RSS feeds
        - Web scraping with BeautifulSoup
        """
        import random
        
        headlines = [
            "Bitcoin reaches new all-time high amid institutional adoption",
            "Cryptocurrency market shows signs of recovery",
            "Regulatory concerns weigh on digital asset prices",
            "Major exchange announces new trading features",
            "Blockchain technology adoption accelerates in finance sector"
        ]
        
        return {
            'text': random.choice(headlines),
            'url': 'https://example.com/news',
            'source': 'Example News'
        }
    
    def _scrape_twitter_placeholder(self) -> Optional[dict]:
        """
        Placeholder for Twitter scraping
        
        TO DO: Implement actual Twitter scraping using:
        - tweepy (official Twitter API library)
        - snscrape (scraping without API limits)
        - Twitter API v2
        """
        import random
        
        tweets = [
            "🚀 Bitcoin to the moon! #BTC #crypto",
            "Bearish market conditions continue 📉",
            "HODL strong! The future is bright ✨",
            "Market volatility increasing, be careful",
            "Best time to accumulate crypto 💎🙌"
        ]
        
        return {
            'text': random.choice(tweets),
            'username': '@cryptotrader',
            'likes': random.randint(10, 1000)
        }
    
    def _scrape_reddit_placeholder(self) -> Optional[dict]:
        """
        Placeholder for Reddit scraping
        
        TO DO: Implement actual Reddit scraping using:
        - praw (Python Reddit API Wrapper)
        - Reddit API
        - Subreddit monitoring (r/cryptocurrency, r/bitcoin, etc.)
        """
        import random
        
        posts = [
            "What's everyone's thoughts on the current market?",
            "Just bought the dip, feeling optimistic!",
            "Concerned about recent regulatory news",
            "Technical analysis suggests bullish trend",
            "Time to sell or hold? Advice needed"
        ]
        
        return {
            'text': random.choice(posts),
            'subreddit': 'r/cryptocurrency',
            'upvotes': random.randint(5, 500)
        }
    
    # Sentiment analysis methods
    
    def _analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text
        
        Returns sentiment score: -1.0 (very negative) to 1.0 (very positive)
        
        TO DO: Implement actual sentiment analysis using:
        - VADER (Valence Aware Dictionary and sEntiment Reasoner)
        - TextBlob
        - Transformers (BERT-based models)
        - LLM APIs (GPT, Gemini)
        """
        # Simple placeholder implementation
        positive_words = ['bullish', 'moon', 'buy', 'up', 'gain', 'profit', 'optimistic', 'bright', 'strong']
        negative_words = ['bearish', 'down', 'sell', 'loss', 'crash', 'dump', 'concerned', 'volatile']
        
        text_lower = text.lower()
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count + negative_count == 0:
            return 0.0
        
        score = (positive_count - negative_count) / (positive_count + negative_count)
        return max(-1.0, min(1.0, score))  # Clamp to [-1, 1]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract keywords from text
        
        TO DO: Implement actual keyword extraction using:
        - NLTK
        - spaCy
        - RAKE (Rapid Automatic Keyword Extraction)
        - TF-IDF
        """
        # Simple placeholder implementation
        import re
        
        # Remove special characters and split
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'is', 'are', 'was', 'were'}
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        
        # Return top keywords
        return keywords[:5]
    
    def _update_sentiment(self, data: dict):
        """Update aggregated sentiment"""
        # Add to data storage
        self._sentiment_data.append(data)
        
        # Keep only recent data (last 1000 items)
        if len(self._sentiment_data) > 1000:
            self._sentiment_data = self._sentiment_data[-1000:]
        
        # Update keywords counter
        for keyword in data.get('keywords', []):
            self._keywords_counter[keyword] += 1
        
        # Calculate overall sentiment
        self._calculate_overall_sentiment()
        
        # Add to history
        self._sentiment_history.append({
            'time': datetime.now(),
            'score': self._current_sentiment['overall_score']
        })
        
        # Keep only last 100 history items
        if len(self._sentiment_history) > 100:
            self._sentiment_history = self._sentiment_history[-100:]
        
        # Emit update signal
        self.signal_sentiment_updated.emit(self._current_sentiment.copy())
    
    def _calculate_overall_sentiment(self):
        """Calculate overall sentiment from recent data"""
        if not self._sentiment_data:
            return
        
        # Get recent data (last hour)
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_data = [
            d for d in self._sentiment_data
            if datetime.strptime(d['time'], "%Y-%m-%d %H:%M:%S") > cutoff_time
        ]
        
        if not recent_data:
            recent_data = self._sentiment_data[-10:]  # Use last 10 if no recent data
        
        # Calculate average score
        scores = [d['score'] for d in recent_data]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Scale to -100 to 100
        overall_score = avg_score * 100
        
        # Count distribution
        positive = sum(1 for s in scores if s > 0.2)
        negative = sum(1 for s in scores if s < -0.2)
        neutral = len(scores) - positive - negative
        
        self._current_sentiment = {
            'overall_score': overall_score,
            'positive': positive,
            'neutral': neutral,
            'negative': negative
        }
    
    # Data access methods
    
    def get_sentiment_history(self) -> List[dict]:
        """Get sentiment history for charting"""
        return self._sentiment_history.copy()
    
    def get_sentiment_distribution(self) -> dict:
        """Get sentiment distribution for pie chart"""
        return {
            'Positive': self._current_sentiment['positive'],
            'Neutral': self._current_sentiment['neutral'],
            'Negative': self._current_sentiment['negative']
        }
    
    def get_wordcloud_image(self) -> Optional[bytes]:
        """
        Generate word cloud image
        
        TO DO: Implement actual word cloud generation using:
        - wordcloud library
        - matplotlib for rendering
        """
        try:
            from wordcloud import WordCloud
            import matplotlib.pyplot as plt
            
            if not self._keywords_counter:
                return None
            
            # Generate word cloud
            wc = WordCloud(
                width=800,
                height=400,
                background_color='white',
                colormap='viridis',
                relative_scaling=0.5,
                min_font_size=10
            ).generate_from_frequencies(self._keywords_counter)
            
            # Save to bytes
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.imshow(wc, interpolation='bilinear')
            ax.axis('off')
            
            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            plt.close(fig)
            
            buf.seek(0)
            return buf.read()
            
        except ImportError:
            logger.warning("wordcloud library not available")
            return None
        except Exception as e:
            logger.error(f"Failed to generate word cloud: {e}")
            return None
