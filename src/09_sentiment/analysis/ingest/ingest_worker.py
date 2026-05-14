"""
Ingest Worker - Kafka producer for ingesting news/social data
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class IngestWorker:
    """Worker for ingesting news and social media data to Kafka"""
    
    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        topic: str = "nlp.raw"
    ):
        self.bootstrap_servers = kafka_bootstrap_servers
        self.topic = topic
        self.producer = None
        self.messages_sent = 0
        
        self._initialize_producer()
    
    def _initialize_producer(self):
        """Initialize Kafka producer"""
        try:
            from kafka import KafkaProducer
            
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            logger.info(f"Kafka producer initialized: {self.bootstrap_servers}")
        except ImportError:
            logger.warning("Kafka library not available, using mock producer")
            self.producer = MockKafkaProducer()
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = MockKafkaProducer()
    
    def ingest_article(self, article: Dict):
        """
        Ingest a news article
        
        Args:
            article: Article dictionary
        """
        event = {
            "type": "news",
            "data": article,
            "timestamp": datetime.now().isoformat(),
            "source": article.get("source", "unknown")
        }
        
        self._send_to_kafka(event)
    
    def ingest_tweet(self, tweet: Dict):
        """
        Ingest a tweet
        
        Args:
            tweet: Tweet dictionary
        """
        event = {
            "type": "social",
            "data": tweet,
            "timestamp": datetime.now().isoformat(),
            "source": "twitter"
        }
        
        self._send_to_kafka(event)
    
    def ingest_batch(self, items: list, item_type: str = "news"):
        """
        Ingest a batch of items
        
        Args:
            items: List of items to ingest
            item_type: Type of items ("news" or "social")
        """
        for item in items:
            if item_type == "news":
                self.ingest_article(item)
            elif item_type == "social":
                self.ingest_tweet(item)
        
        logger.info(f"Ingested batch of {len(items)} {item_type} items")
    
    def _send_to_kafka(self, event: Dict):
        """
        Send event to Kafka
        
        Args:
            event: Event dictionary
        """
        try:
            self.producer.send(self.topic, value=event)
            self.messages_sent += 1
            logger.debug(f"Sent message to Kafka topic {self.topic}")
        except Exception as e:
            logger.error(f"Failed to send to Kafka: {e}")
    
    def get_stats(self) -> Dict:
        """
        Get ingestion statistics
        
        Returns:
            Dictionary with stats
        """
        return {
            "messages_sent": self.messages_sent,
            "topic": self.topic,
            "bootstrap_servers": self.bootstrap_servers
        }
    
    def close(self):
        """Close Kafka producer"""
        if self.producer and hasattr(self.producer, 'close'):
            self.producer.close()
        logger.info("Ingest worker closed")
    
    def start(self):
        """
        Start the worker pool (compatibility method)
        Worker is initialized in __init__, this is a no-op for compatibility
        """
        logger.info("Ingest worker ready (already initialized)")
    
    def shutdown(self):
        """
        Shutdown the worker pool (compatibility method)
        Alias for close()
        """
        self.close()


class MockKafkaProducer:
    """Mock Kafka producer for testing"""
    
    def send(self, topic: str, value: Dict):
        """Mock send"""
        logger.debug(f"Mock send to {topic}: {type(value)}")
    
    def close(self):
        """Mock close"""
        pass
