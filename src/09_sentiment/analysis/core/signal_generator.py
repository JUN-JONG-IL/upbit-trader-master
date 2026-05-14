"""
Signal Generator - Generate trading signals from NLP analysis
"""

import logging
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals from sentiment and NLP analysis"""
    
    def __init__(self, kafka_producer=None):
        self.kafka_producer = kafka_producer
        self.baseline_sentiment = {}  # symbol -> baseline sentiment
        self.signals_generated = []
    
    def generate_signals(
        self,
        symbol: str,
        documents: List[Dict],
        window_minutes: int = 5,
        z_score_threshold: float = 2.0
    ) -> List[Dict]:
        """
        Generate signals from sentiment spikes
        
        Args:
            symbol: Trading symbol
            documents: List of analyzed documents with sentiment
            window_minutes: Time window for analysis
            z_score_threshold: Z-score threshold for signal
            
        Returns:
            List of signal dictionaries
        """
        if not documents:
            return []
        
        # Calculate average sentiment
        sentiments = [doc.get('sentiment', {}).get('score', 0) for doc in documents]
        avg_sentiment = np.mean(sentiments) if sentiments else 0
        
        # Get baseline
        if symbol not in self.baseline_sentiment:
            self.baseline_sentiment[symbol] = {
                'mean': 0.0,
                'std': 0.2,
                'samples': []
            }
        
        baseline = self.baseline_sentiment[symbol]
        
        # Update baseline with exponential moving average
        alpha = 0.1
        baseline['mean'] = alpha * avg_sentiment + (1 - alpha) * baseline['mean']
        baseline['samples'].append(avg_sentiment)
        
        # Keep last 100 samples for std calculation
        if len(baseline['samples']) > 100:
            baseline['samples'] = baseline['samples'][-100:]
            baseline['std'] = np.std(baseline['samples'])
        
        # Calculate z-score
        if baseline['std'] > 0:
            z_score = (avg_sentiment - baseline['mean']) / baseline['std']
        else:
            z_score = 0
        
        signals = []
        
        # Generate signal if threshold exceeded
        if abs(z_score) > z_score_threshold:
            signal_type = "bullish" if z_score > 0 else "bearish"
            
            signal = {
                "type": "sentiment_spike",
                "symbol": symbol,
                "signal": signal_type,
                "window_minutes": window_minutes,
                "avg_sentiment": float(avg_sentiment),
                "z_score": float(z_score),
                "n_documents": len(documents),
                "timestamp": datetime.now().isoformat(),
                "confidence": min(abs(z_score) / 5.0, 1.0)  # Normalize confidence
            }
            
            signals.append(signal)
            self.signals_generated.append(signal)
            
            # Publish to Kafka if available
            if self.kafka_producer:
                self._publish_signal(signal)
            
            logger.info(f"Signal generated: {signal_type} for {symbol}, z-score={z_score:.2f}")
        
        return signals
    
    def _publish_signal(self, signal: Dict):
        """
        Publish signal to Kafka
        
        Args:
            signal: Signal dictionary
        """
        try:
            import json
            self.kafka_producer.send(
                'nlp.signals',
                value=json.dumps(signal).encode()
            )
            logger.debug(f"Published signal to Kafka")
        except Exception as e:
            logger.error(f"Failed to publish signal: {e}")
    
    def get_signal_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get signal history
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of signals to return
            
        Returns:
            List of signals
        """
        signals = self.signals_generated[-limit:]
        
        if symbol:
            signals = [s for s in signals if s['symbol'] == symbol]
        
        return signals
    
    def get_baseline_sentiment(self, symbol: str) -> Dict:
        """
        Get baseline sentiment for symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Baseline dictionary
        """
        return self.baseline_sentiment.get(symbol, {
            'mean': 0.0,
            'std': 0.2,
            'samples': []
        })
    
    def reset_baseline(self, symbol: Optional[str] = None):
        """
        Reset baseline sentiment
        
        Args:
            symbol: Optional symbol to reset (all if None)
        """
        if symbol:
            if symbol in self.baseline_sentiment:
                del self.baseline_sentiment[symbol]
                logger.info(f"Reset baseline for {symbol}")
        else:
            self.baseline_sentiment = {}
            logger.info("Reset all baselines")
