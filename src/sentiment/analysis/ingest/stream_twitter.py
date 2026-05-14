"""
Twitter Streamer - Real-time Twitter data collection
"""

import logging
import asyncio
import json
from typing import List, Dict, Optional, Callable
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class TwitterStreamer:
    """Streams real-time tweets about crypto"""
    
    def __init__(self, bearer_token: Optional[str] = None, keywords: List[str] = None, languages: List[str] = None):
        self.bearer_token = bearer_token or "mock_bearer_token"
        self.is_streaming = False
        self.tweet_buffer = []
        self.kafka_producer = None
        self.keywords = keywords or []
        self.languages = languages or ['en', 'ko']
        self.callback = None
        self.stream_thread = None
    
    async def start_stream(
        self,
        keywords: List[str],
        callback: Optional[Callable] = None,
        language: List[str] = None
    ):
        """
        Start streaming tweets
        
        Args:
            keywords: Keywords to track
            callback: Optional callback function for each tweet
            language: Languages to filter (e.g., ['en', 'ko'])
        """
        logger.info(f"Starting Twitter stream for keywords: {keywords}")
        
        self.is_streaming = True
        languages = language or ['en', 'ko']
        
        # Mock streaming - in production would use tweepy or Twitter API v2
        while self.is_streaming:
            # Generate mock tweet
            tweet = self._generate_mock_tweet(keywords, languages)
            
            # Process tweet
            await self._process_tweet(tweet, callback)
            
            # Simulate streaming delay
            await asyncio.sleep(2)
    
    def _generate_mock_tweet(self, keywords: List[str], languages: List[str]) -> Dict:
        """Generate a mock tweet for testing"""
        import random
        
        keyword = random.choice(keywords)
        lang = random.choice(languages)
        
        sentiments = [
            f"{keyword} is going to the moon! 🚀",
            f"Bearish on {keyword} today",
            f"Just bought some {keyword}, feeling good!",
            f"{keyword} looking strong",
            f"Worried about {keyword} price action"
        ]
        
        tweet = {
            "id": hashlib.md5(f"{datetime.now().timestamp()}".encode()).hexdigest(),
            "text": random.choice(sentiments),
            "author_id": f"user_{random.randint(1000, 9999)}",
            "created_at": datetime.now().isoformat(),
            "lang": lang,
            "source": "twitter",
            "keywords": [keyword]
        }
        
        return tweet
    
    async def _process_tweet(self, tweet: Dict, callback: Optional[Callable] = None):
        """
        Process a tweet
        
        Args:
            tweet: Tweet dictionary
            callback: Optional callback function
        """
        # Add to buffer
        self.tweet_buffer.append(tweet)
        
        # Keep buffer size manageable
        if len(self.tweet_buffer) > 1000:
            self.tweet_buffer = self.tweet_buffer[-1000:]
        
        # Publish to Kafka if producer available
        if self.kafka_producer:
            try:
                self.kafka_producer.send(
                    'social.raw',
                    value=json.dumps(tweet).encode()
                )
            except Exception as e:
                logger.warning(f"Failed to publish tweet to Kafka: {e}")
        
        # Call callback if provided
        if callback:
            try:
                await callback(tweet)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        logger.debug(f"Processed tweet {tweet['id']}")
    
    def stop_stream(self):
        """Stop the Twitter stream"""
        self.is_streaming = False
        logger.info("Twitter stream stopped")
    
    def get_buffered_tweets(self, n: int = 100) -> List[Dict]:
        """
        Get recent buffered tweets
        
        Args:
            n: Number of tweets to return
            
        Returns:
            List of recent tweets
        """
        return self.tweet_buffer[-n:]
    
    def clear_buffer(self):
        """Clear tweet buffer"""
        self.tweet_buffer = []
        logger.info("Tweet buffer cleared")
    
    def set_kafka_producer(self, producer):
        """Set Kafka producer for publishing tweets"""
        self.kafka_producer = producer
        logger.info("Kafka producer set")
    
    def set_callback(self, callback: Callable):
        """
        Set callback function for tweet processing
        
        Args:
            callback: Callback function to call for each tweet
        """
        self.callback = callback
        logger.info("Callback function set")
    
    def start_streaming(self):
        """
        Start streaming tweets (non-async wrapper)
        Starts streaming in a background thread
        """
        import threading
        
        def run_async_stream():
            """Run async stream in event loop"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.start_stream(
                        keywords=self.keywords,
                        callback=self._sync_callback_wrapper,
                        language=self.languages
                    )
                )
            finally:
                loop.close()
        
        self.stream_thread = threading.Thread(target=run_async_stream, daemon=True)
        self.stream_thread.start()
        logger.info("Twitter streaming started in background thread")
    
    def _sync_callback_wrapper(self, tweet: Dict):
        """
        Wrapper to convert async callback to sync
        
        Args:
            tweet: Tweet dictionary
        """
        if self.callback:
            try:
                # Call the sync callback
                self.callback(tweet)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def stop(self):
        """Stop streaming (alias for stop_stream)"""
        self.stop_stream()

