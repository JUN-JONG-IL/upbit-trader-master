"""
Event Publisher - Publish NLP events to scanner/alert system
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes NLP events to trading system"""
    
    def __init__(self, kafka_producer=None):
        self.kafka_producer = kafka_producer
        self.events_published = []
    
    def publish_sentiment_event(
        self,
        symbol: str,
        sentiment: Dict,
        source: str = "news"
    ):
        """
        Publish sentiment analysis event
        
        Args:
            symbol: Trading symbol
            sentiment: Sentiment analysis result
            source: Data source (news, twitter, reddit)
        """
        event = {
            "event_type": "sentiment_analysis",
            "symbol": symbol,
            "sentiment": sentiment,
            "source": source,
            "timestamp": datetime.now().isoformat()
        }
        
        self._publish_event(event, topic="nlp.events")
    
    def publish_signal_event(
        self,
        signal: Dict
    ):
        """
        Publish trading signal event
        
        Args:
            signal: Trading signal dictionary
        """
        event = {
            "event_type": "trading_signal",
            "signal": signal,
            "timestamp": datetime.now().isoformat()
        }
        
        self._publish_event(event, topic="nlp.signals")
    
    def publish_anomaly_event(
        self,
        symbol: str,
        anomaly_type: str,
        details: Dict
    ):
        """
        Publish anomaly detection event
        
        Args:
            symbol: Trading symbol
            anomaly_type: Type of anomaly
            details: Anomaly details
        """
        event = {
            "event_type": "anomaly_detected",
            "symbol": symbol,
            "anomaly_type": anomaly_type,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        
        self._publish_event(event, topic="nlp.alerts")
    
    def _publish_event(self, event: Dict, topic: str = "nlp.events"):
        """
        Publish event to Kafka
        
        Args:
            event: Event dictionary
            topic: Kafka topic
        """
        self.events_published.append(event)
        
        if self.kafka_producer:
            try:
                self.kafka_producer.send(
                    topic,
                    value=json.dumps(event).encode()
                )
                logger.debug(f"Published event to {topic}")
            except Exception as e:
                logger.error(f"Failed to publish event: {e}")
        else:
            logger.debug(f"No Kafka producer, event stored locally")
    
    def get_event_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get event history
        
        Args:
            event_type: Optional event type filter
            limit: Maximum number of events
            
        Returns:
            List of events
        """
        events = self.events_published[-limit:]
        
        if event_type:
            events = [e for e in events if e.get('event_type') == event_type]
        
        return events
    
    def get_stats(self) -> Dict:
        """
        Get publishing statistics
        
        Returns:
            Statistics dictionary
        """
        event_types = {}
        for event in self.events_published:
            event_type = event.get('event_type', 'unknown')
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        return {
            "total_events": len(self.events_published),
            "event_types": event_types,
            "has_kafka": self.kafka_producer is not None
        }
