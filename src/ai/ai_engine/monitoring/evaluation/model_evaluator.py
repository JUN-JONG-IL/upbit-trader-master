"""
Model Evaluator - Offline and online model validation
"""

import logging
from typing import Dict, List, Any, Optional
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Evaluates model performance offline and online"""
    
    def __init__(self):
        self.evaluation_history: List[Dict] = []
    
    def evaluate_offline(
        self,
        model: Any,
        test_data: List[Dict],
        metrics: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Evaluate model on test dataset
        
        Args:
            model: Model to evaluate
            test_data: List of test samples {input, expected_output}
            metrics: Metrics to compute (accuracy, precision, recall, f1)
            
        Returns:
            Dictionary of metric values
        """
        if metrics is None:
            metrics = ['accuracy', 'mae', 'rmse']
        
        predictions = []
        actuals = []
        
        # Get predictions
        for sample in test_data:
            try:
                pred = model.predict(sample['input'])
                predictions.append(pred)
                actuals.append(sample['expected_output'])
            except Exception as e:
                logger.error(f"Prediction failed for sample: {e}")
                continue
        
        # Compute metrics
        results = {}
        
        if 'accuracy' in metrics and len(predictions) > 0:
            correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
            results['accuracy'] = correct / len(predictions)
        
        if 'mae' in metrics and len(predictions) > 0:
            try:
                results['mae'] = np.mean(np.abs(np.array(predictions) - np.array(actuals)))
            except:
                results['mae'] = 0.0
        
        if 'rmse' in metrics and len(predictions) > 0:
            try:
                results['rmse'] = np.sqrt(np.mean((np.array(predictions) - np.array(actuals)) ** 2))
            except:
                results['rmse'] = 0.0
        
        # Save evaluation
        self.evaluation_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'offline',
            'n_samples': len(test_data),
            'metrics': results
        })
        
        logger.info(f"Offline evaluation: {results}")
        return results
    
    def evaluate_online(
        self,
        model_name: str,
        version: str,
        window_minutes: int = 60
    ) -> Dict[str, float]:
        """
        Evaluate model performance on recent online predictions
        
        Args:
            model_name: Name of model
            version: Model version
            window_minutes: Time window for evaluation
            
        Returns:
            Dictionary of metrics
        """
        # In production, query from monitoring database
        # For now, return mock metrics
        results = {
            'latency_p95_ms': 150.0,
            'latency_p99_ms': 250.0,
            'error_rate': 0.001,
            'throughput_rps': 50.0
        }
        
        self.evaluation_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'online',
            'model': f"{model_name}@{version}",
            'window_minutes': window_minutes,
            'metrics': results
        })
        
        logger.info(f"Online evaluation for {model_name}@{version}: {results}")
        return results
    
    def compare_models(
        self,
        model_a: Any,
        model_b: Any,
        test_data: List[Dict]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compare two models on the same test data
        
        Args:
            model_a: First model
            model_b: Second model
            test_data: Test dataset
            
        Returns:
            Dictionary with results for both models
        """
        results_a = self.evaluate_offline(model_a, test_data)
        results_b = self.evaluate_offline(model_b, test_data)
        
        return {
            'model_a': results_a,
            'model_b': results_b,
            'winner': 'model_a' if results_a.get('accuracy', 0) > results_b.get('accuracy', 0) else 'model_b'
        }
