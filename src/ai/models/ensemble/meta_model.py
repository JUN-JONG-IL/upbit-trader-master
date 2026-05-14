"""
Meta Model - Ensemble of multiple prediction models
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..base_predictor import BasePredictor

logger = logging.getLogger(__name__)


class MetaModel(BasePredictor):
    """Ensemble meta-model combining multiple base models"""
    
    def __init__(
        self,
        model_name: str = "meta-ensemble-v1",
        base_models: Optional[List[BasePredictor]] = None,
        config: Optional[Dict] = None
    ):
        super().__init__(model_name, config)
        
        self.base_models = base_models or []
        self.weights = None
        self.aggregation_method = config.get("aggregation", "weighted_avg") if config else "weighted_avg"
    
    def add_model(self, model: BasePredictor, weight: float = 1.0):
        """
        Add a base model to the ensemble
        
        Args:
            model: Base predictor model
            weight: Model weight (default: 1.0)
        """
        self.base_models.append(model)
        
        if self.weights is None:
            self.weights = [weight]
        else:
            self.weights.append(weight)
        
        # Normalize weights
        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]
        
        logger.info(f"Added model {model.model_name} with weight {weight:.3f}")
    
    def train(self, X: Any, y: Any, **kwargs) -> Dict:
        """
        Train all base models
        
        Args:
            X: Training features
            y: Training labels
            **kwargs: Training parameters
            
        Returns:
            Training metrics for all models
        """
        logger.info(f"Training meta-model with {len(self.base_models)} base models")
        
        start_time = datetime.now()
        
        model_metrics = []
        
        for i, model in enumerate(self.base_models):
            logger.info(f"Training base model {i+1}/{len(self.base_models)}: {model.model_name}")
            metrics = model.train(X, y, **kwargs)
            model_metrics.append(metrics)
        
        self.is_trained = True
        
        meta_metrics = {
            "model": self.model_name,
            "n_base_models": len(self.base_models),
            "aggregation_method": self.aggregation_method,
            "base_models": model_metrics,
            "training_time_seconds": (datetime.now() - start_time).total_seconds()
        }
        
        self.training_history.append(meta_metrics)
        
        logger.info(f"Meta-model training complete")
        
        return meta_metrics
    
    def predict(self, X: Any, return_individual: bool = False, **kwargs) -> Any:
        """
        Make ensemble predictions
        
        Args:
            X: Input features
            return_individual: Whether to return individual model predictions
            **kwargs: Additional parameters
            
        Returns:
            Ensemble predictions (or tuple with individual predictions)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        if not self.base_models:
            raise ValueError("No base models in ensemble")
        
        # Get predictions from all base models
        predictions = []
        for model in self.base_models:
            pred = model.predict(X, **kwargs)
            predictions.append(pred)
        
        predictions = np.array(predictions)
        
        # Aggregate predictions
        if self.aggregation_method == "weighted_avg":
            weights = np.array(self.weights).reshape(-1, 1)
            ensemble_pred = np.sum(predictions * weights, axis=0)
        elif self.aggregation_method == "median":
            ensemble_pred = np.median(predictions, axis=0)
        elif self.aggregation_method == "mean":
            ensemble_pred = np.mean(predictions, axis=0)
        else:
            ensemble_pred = np.mean(predictions, axis=0)
        
        if return_individual:
            return ensemble_pred, predictions
        else:
            return ensemble_pred
    
    def evaluate(self, X: Any, y: Any) -> Dict[str, float]:
        """
        Evaluate ensemble and individual models
        
        Args:
            X: Test features
            y: True labels
            
        Returns:
            Evaluation metrics
        """
        # Ensemble metrics
        ensemble_metrics = super().evaluate(X, y)
        ensemble_metrics["model"] = "ensemble"
        
        # Individual model metrics
        individual_metrics = []
        for model in self.base_models:
            metrics = model.evaluate(X, y)
            metrics["model"] = model.model_name
            individual_metrics.append(metrics)
        
        return {
            "ensemble": ensemble_metrics,
            "individual": individual_metrics
        }
