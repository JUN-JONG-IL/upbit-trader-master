"""
Asynchronous Inference Client - Kafka-based async inference
"""

import json
import logging
import asyncio
from typing import Dict, Optional, Any, Callable
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class AsyncInferenceClient:
    """Asynchronous inference client using Kafka message queue"""
    
    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        request_topic: str = "ai.inference.requests",
        response_topic: str = "ai.inference.responses"
    ):
        self.bootstrap_servers = kafka_bootstrap_servers
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.producer = None
        self.consumer = None
        self.pending_requests: Dict[str, Callable] = {}
    
    async def initialize(self):
        """Initialize Kafka producer and consumer"""
        try:
            # Note: Using aiokafka would be ideal, but for simplicity using sync Kafka
            from kafka import KafkaProducer, KafkaConsumer
            
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            
            self.consumer = KafkaConsumer(
                self.response_topic,
                bootstrap_servers=self.bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True
            )
            
            logger.info("AsyncInferenceClient initialized")
        except ImportError:
            logger.warning("Kafka library not available - async inference disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka client: {e}")
    
    async def infer_async(
        self,
        model: str,
        prompt: str,
        context: Optional[Dict] = None,
        params: Optional[Dict] = None,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Submit asynchronous inference request
        
        Args:
            model: Model name
            prompt: Input prompt
            context: Additional context
            params: Model parameters
            callback: Optional callback function for result
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        
        payload = {
            "request_id": request_id,
            "model": model,
            "prompt": prompt,
            "context": context or {},
            "params": params or {},
            "timestamp": datetime.now().isoformat()
        }
        
        if callback:
            self.pending_requests[request_id] = callback
        
        try:
            if self.producer:
                self.producer.send(self.request_topic, value=payload)
                logger.info(f"Sent async inference request: {request_id}")
            else:
                logger.warning("Kafka producer not initialized")
        except Exception as e:
            logger.error(f"Failed to send async request: {e}")
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            raise
        
        return request_id
    
    async def poll_responses(self, timeout_ms: int = 1000):
        """
        Poll for inference responses and execute callbacks
        
        Args:
            timeout_ms: Polling timeout in milliseconds
        """
        if not self.consumer:
            return
        
        try:
            messages = self.consumer.poll(timeout_ms=timeout_ms)
            
            for topic_partition, records in messages.items():
                for record in records:
                    response = record.value
                    request_id = response.get('request_id')
                    
                    if request_id in self.pending_requests:
                        callback = self.pending_requests.pop(request_id)
                        try:
                            callback(response)
                        except Exception as e:
                            logger.error(f"Callback error for {request_id}: {e}")
                    
                    logger.debug(f"Processed async response: {request_id}")
        except Exception as e:
            logger.error(f"Error polling responses: {e}")
    
    async def close(self):
        """Close Kafka connections"""
        if self.producer:
            self.producer.close()
        if self.consumer:
            self.consumer.close()
        logger.info("AsyncInferenceClient closed")
