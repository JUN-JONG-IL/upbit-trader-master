"""
Drift Detector - Detects data drift and model drift
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detects data drift and model performance drift"""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.reference_data = {}  # model_name -> reference statistics
        self.recent_data = {}  # model_name -> recent data window
    
    def set_reference(
        self,
        model_name: str,
        data: List[float],
        feature_name: str = "default"
    ):
        """
        Set reference distribution for drift detection
        
        Args:
            model_name: Model name
            data: Reference data samples
            feature_name: Name of the feature
        """
        if model_name not in self.reference_data:
            self.reference_data[model_name] = {}
        
        self.reference_data[model_name][feature_name] = {
            "mean": np.mean(data),
            "std": np.std(data),
            "min": np.min(data),
            "max": np.max(data),
            "quantiles": np.percentile(data, [25, 50, 75]),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Set reference distribution for {model_name}/{feature_name}")
    
    def record_sample(
        self,
        model_name: str,
        value: float,
        feature_name: str = "default"
    ):
        """
        Record a new data sample
        
        Args:
            model_name: Model name
            value: Sample value
            feature_name: Feature name
        """
        key = f"{model_name}/{feature_name}"
        
        if key not in self.recent_data:
            self.recent_data[key] = deque(maxlen=self.window_size)
        
        self.recent_data[key].append(value)
    
    def detect_data_drift(
        self,
        model_name: str,
        feature_name: str = "default",
        threshold: float = 2.0
    ) -> Tuple[bool, Dict]:
        """
        Detect data drift using statistical tests
        
        Args:
            model_name: Model name
            feature_name: Feature name
            threshold: Z-score threshold for drift detection
            
        Returns:
            Tuple of (drift_detected, drift_metrics)
        """
        key = f"{model_name}/{feature_name}"
        
        # Check if we have reference and recent data
        if model_name not in self.reference_data:
            logger.warning(f"No reference data for {model_name}")
            return False, {}
        
        if feature_name not in self.reference_data[model_name]:
            logger.warning(f"No reference data for {model_name}/{feature_name}")
            return False, {}
        
        if key not in self.recent_data or len(self.recent_data[key]) < 100:
            logger.warning(f"Insufficient recent data for {key}")
            return False, {}
        
        # Get reference statistics
        ref_stats = self.reference_data[model_name][feature_name]
        ref_mean = ref_stats["mean"]
        ref_std = ref_stats["std"]
        
        # Get recent statistics
        recent_samples = list(self.recent_data[key])
        recent_mean = np.mean(recent_samples)
        recent_std = np.std(recent_samples)
        
        # Compute z-score for mean shift
        if ref_std > 0:
            z_score = abs(recent_mean - ref_mean) / ref_std
        else:
            z_score = 0
        
        # Detect drift
        drift_detected = z_score > threshold
        
        drift_metrics = {
            "feature_name": feature_name,
            "reference_mean": float(ref_mean),
            "reference_std": float(ref_std),
            "recent_mean": float(recent_mean),
            "recent_std": float(recent_std),
            "z_score": float(z_score),
            "threshold": threshold,
            "drift_detected": drift_detected,
            "timestamp": datetime.now().isoformat()
        }
        
        if drift_detected:
            logger.warning(f"Data drift detected for {key}: z-score={z_score:.2f}")
        
        return drift_detected, drift_metrics
    
    def detect_model_drift(
        self,
        model_name: str,
        recent_errors: List[float],
        baseline_error: float,
        threshold: float = 1.5
    ) -> Tuple[bool, Dict]:
        """
        Detect model performance drift
        
        Args:
            model_name: Model name
            recent_errors: Recent prediction errors
            baseline_error: Baseline error rate
            threshold: Multiplier threshold (e.g., 1.5 = 50% increase)
            
        Returns:
            Tuple of (drift_detected, drift_metrics)
        """
        if not recent_errors:
            return False, {}
        
        recent_avg_error = np.mean(recent_errors)
        error_increase = recent_avg_error / max(baseline_error, 1e-10)
        
        drift_detected = error_increase > threshold
        
        drift_metrics = {
            "model_name": model_name,
            "baseline_error": float(baseline_error),
            "recent_avg_error": float(recent_avg_error),
            "error_increase_ratio": float(error_increase),
            "threshold": threshold,
            "drift_detected": drift_detected,
            "timestamp": datetime.now().isoformat()
        }
        
        if drift_detected:
            logger.warning(
                f"Model drift detected for {model_name}: "
                f"error increased by {(error_increase-1)*100:.1f}%"
            )
        
        return drift_detected, drift_metrics
    
    def get_drift_report(self, model_name: str) -> Dict:
        """
        Generate drift detection report
        
        Args:
            model_name: Model name
            
        Returns:
            Dictionary with drift status
        """
        report = {
            "model_name": model_name,
            "timestamp": datetime.now().isoformat(),
            "features": []
        }
        
        if model_name in self.reference_data:
            for feature_name in self.reference_data[model_name].keys():
                drift_detected, metrics = self.detect_data_drift(model_name, feature_name)
                report["features"].append(metrics)
        
        return report
