"""
Feature Store - Redis-based feature caching and management
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class FeatureStore:
    """Feature Store for caching and managing features"""
    
    def __init__(self, redis_client=None, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl  # Default TTL: 1 hour
        self.cache = {}  # In-memory cache when Redis not available
        
        if redis_client is None:
            logger.warning("Redis client not provided, using in-memory cache")
    
    def get_features(
        self,
        symbol: str,
        timestamp: datetime,
        feature_groups: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Get features for a symbol at a timestamp
        
        Args:
            symbol: Trading symbol (e.g., 'KRW-BTC')
            timestamp: Timestamp for features
            feature_groups: Optional list of feature groups to retrieve
            
        Returns:
            Dictionary of feature values
        """
        cache_key = f"features:{symbol}:{timestamp.isoformat()}"
        
        # Try cache first
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
        elif cache_key in self.cache:
            return self.cache[cache_key]
        
        # Compute features
        features = self._compute_features(symbol, timestamp, feature_groups)
        
        # Store in cache
        self._set_cache(cache_key, features)
        
        return features
    
    def _compute_features(
        self,
        symbol: str,
        timestamp: datetime,
        feature_groups: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Compute features for a symbol
        
        Args:
            symbol: Trading symbol
            timestamp: Timestamp
            feature_groups: Feature groups to compute
            
        Returns:
            Dictionary of features
        """
        from .feature_engineer import FeatureEngineer
        
        engineer = FeatureEngineer()
        
        # Mock candle data for demonstration
        # In production, this would query actual market data
        candles = self._get_candles(symbol, timestamp, lookback=200)
        
        # Generate features
        features = engineer.generate_features(candles, feature_groups)
        
        return features
    
    def _get_candles(self, symbol: str, timestamp: datetime, lookback: int = 200) -> List[Dict]:
        """
        Get historical candles (mock implementation)
        
        Args:
            symbol: Trading symbol
            timestamp: End timestamp
            lookback: Number of candles to fetch
            
        Returns:
            List of candle dictionaries
        """
        # Mock candle data
        candles = []
        base_price = 50000 if "BTC" in symbol else 3000
        
        for i in range(lookback):
            t = timestamp - timedelta(minutes=lookback - i)
            price = base_price + np.random.randn() * 1000
            volume = 1000 + np.random.rand() * 500
            
            candles.append({
                "timestamp": t,
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price + np.random.randn() * 100,
                "volume": volume
            })
        
        return candles
    
    def _set_cache(self, key: str, value: Dict):
        """Set cache value"""
        if self.redis:
            try:
                self.redis.setex(key, self.ttl, json.dumps(value))
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")
        else:
            self.cache[key] = value
    
    def list_feature_groups(self) -> List[str]:
        """
        List available feature groups
        
        Returns:
            List of feature group names
        """
        return [
            "price_features",
            "technical_indicators",
            "volume_features",
            "volatility_features",
            "momentum_features"
        ]
    
    def get_feature_metadata(self, feature_name: str) -> Dict:
        """
        Get metadata for a feature
        
        Args:
            feature_name: Name of the feature
            
        Returns:
            Dictionary with feature metadata
        """
        return {
            "name": feature_name,
            "type": "float",
            "description": f"Feature: {feature_name}",
            "min_value": None,
            "max_value": None
        }
    
    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear feature cache
        
        Args:
            symbol: Optional symbol to clear (clears all if None)
        """
        if symbol:
            pattern = f"features:{symbol}:*"
            if self.redis:
                try:
                    keys = self.redis.keys(pattern)
                    if keys:
                        self.redis.delete(*keys)
                except:
                    pass
            else:
                self.cache = {k: v for k, v in self.cache.items() if not k.startswith(f"features:{symbol}:")}
        else:
            if self.redis:
                try:
                    keys = self.redis.keys("features:*")
                    if keys:
                        self.redis.delete(*keys)
                except:
                    pass
            else:
                self.cache.clear()
        
        logger.info(f"Cleared cache for {symbol if symbol else 'all symbols'}")
