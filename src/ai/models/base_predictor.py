"""
Base Predictor - Abstract base class for all prediction models
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class BasePredictor(ABC):
    """Abstract base class for prediction models"""
    
    def __init__(self, model_name: str, config: Optional[Dict] = None):
        self.model_name = model_name
        self.config = config or {}
        self.model = None
        self.is_trained = False
        self.training_history = []
    
    @abstractmethod
    def train(self, X: Any, y: Any, **kwargs) -> Dict:
        """
        Train the model
        
        Args:
            X: Training features
            y: Training labels
            **kwargs: Additional training parameters
            
        Returns:
            Training metrics dictionary
        """
        pass
    
    @abstractmethod
    def predict(self, X: Any, **kwargs) -> Any:
        """
        Make predictions
        
        Args:
            X: Input features
            **kwargs: Additional prediction parameters
            
        Returns:
            Predictions
        """
        pass
    
    def evaluate(self, X: Any, y: Any) -> Dict[str, float]:
        """
        Evaluate model performance
        
        Args:
            X: Test features
            y: True labels
            
        Returns:
            Evaluation metrics
        """
        predictions = self.predict(X)
        
        # Calculate basic metrics
        import numpy as np
        
        try:
            mae = np.mean(np.abs(predictions - y))
            rmse = np.sqrt(np.mean((predictions - y) ** 2))
            mape = np.mean(np.abs((y - predictions) / y)) * 100
            
            return {
                "mae": float(mae),
                "rmse": float(rmse),
                "mape": float(mape)
            }
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}
    
    def save(self, path: str):
        """
        Save model to disk
        
        Args:
            path: Path to save the model
        """
        import pickle
        
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        
        logger.info(f"Model saved to {path}")
    
    @classmethod
    def load(cls, path: str) -> 'BasePredictor':
        """
        Load model from disk
        
        Args:
            path: Path to load the model from
            
        Returns:
            Loaded model instance
        """
        import pickle
        
        with open(path, 'rb') as f:
            model = pickle.load(f)
        
        logger.info(f"Model loaded from {path}")
        return model
    
    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """
        Get feature importance if available
        
        Returns:
            Dictionary of feature importances or None
        """
        return None
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.model_name}', trained={self.is_trained})"
