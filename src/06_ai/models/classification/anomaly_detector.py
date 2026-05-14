"""
Anomaly Detector - Detects unusual market behavior
"""

import logging
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_predictor import BasePredictor

logger = logging.getLogger(__name__)


class AnomalyDetector(BasePredictor):
    """Detects anomalies in market data"""
    
    def __init__(self, model_name: str = "anomaly-detector-v1", config: Optional[Dict] = None):
        super().__init__(model_name, config)
        
        self.contamination = config.get("contamination", 0.01) if config else 0.01
        self.threshold = None
    
    def train(self, X: Any, y: Any = None, **kwargs) -> Dict:
        """
        Train anomaly detector (unsupervised)
        
        Args:
            X: Training features
            y: Not used (unsupervised)
            **kwargs: Training parameters
            
        Returns:
            Training metrics
        """
        logger.info(f"Training {self.model_name} with {len(X)} samples")
        
        start_time = datetime.now()
        
        # Use IsolationForest or similar
        try:
            from sklearn.ensemble import IsolationForest
            
            self.model = IsolationForest(
                contamination=self.contamination,
                random_state=42
            )
            self.model.fit(X)
            
            # Calculate threshold from scores
            scores = self.model.score_samples(X)
            self.threshold = np.percentile(scores, self.contamination * 100)
            
        except ImportError:
            logger.warning("sklearn not available, using mock anomaly detector")
            self.model = MockAnomalyDetector()
            self.threshold = -0.5
        
        self.is_trained = True
        
        metrics = {
            "model": self.model_name,
            "n_samples": len(X),
            "contamination": self.contamination,
            "threshold": float(self.threshold) if self.threshold is not None else None,
            "training_time_seconds": (datetime.now() - start_time).total_seconds()
        }
        
        self.training_history.append(metrics)
        
        logger.info(f"Anomaly detector training complete")
        
        return metrics
    
    def predict(self, X: Any, return_score: bool = False, **kwargs) -> Any:
        """
        Detect anomalies
        
        Args:
            X: Input features
            return_score: Whether to return anomaly scores
            **kwargs: Additional parameters
            
        Returns:
            Predictions (1=normal, -1=anomaly) or scores
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        if return_score and hasattr(self.model, 'score_samples'):
            return self.model.score_samples(X)
        else:
            return self.model.predict(X)
    
    def detect_anomalies(self, X: Any) -> tuple:
        """
        Detect anomalies and return indices
        
        Args:
            X: Input features
            
        Returns:
            Tuple of (predictions, anomaly_indices)
        """
        predictions = self.predict(X)
        anomaly_indices = np.where(predictions == -1)[0]
        
        return predictions, anomaly_indices


class MockAnomalyDetector:
    """Mock anomaly detector for testing"""
    
    def predict(self, X):
        """Mock prediction (mostly normal)"""
        n = len(X) if hasattr(X, '__len__') else 1
        # 99% normal, 1% anomaly
        return np.random.choice([1, -1], size=n, p=[0.99, 0.01])
    
    def score_samples(self, X):
        """Mock anomaly scores"""
        n = len(X) if hasattr(X, '__len__') else 1
        return np.random.randn(n) * 0.5
    
    def fit(self, X):
        """Mock fit"""
        return self
