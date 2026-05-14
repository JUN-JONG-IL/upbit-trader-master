"""
Normalizer - Feature normalization and scaling
"""

import logging
import numpy as np
import pickle
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class Normalizer:
    """Normalizes features for model input"""
    
    def __init__(self, method: str = "standard"):
        """
        Initialize normalizer
        
        Args:
            method: Normalization method ('standard', 'minmax', 'robust')
        """
        self.method = method
        self.scaler = None
        self.is_fitted = False
        self.feature_stats = {}
    
    def fit(self, features: Dict[str, float]) -> 'Normalizer':
        """
        Fit normalizer on features
        
        Args:
            features: Dictionary of feature values
            
        Returns:
            Self
        """
        # Store statistics for each feature
        for key, value in features.items():
            if key not in self.feature_stats:
                self.feature_stats[key] = {
                    "values": [],
                    "mean": 0.0,
                    "std": 1.0,
                    "min": 0.0,
                    "max": 1.0
                }
            
            self.feature_stats[key]["values"].append(value)
        
        # Calculate statistics
        for key, stats in self.feature_stats.items():
            values = np.array(stats["values"])
            stats["mean"] = float(np.mean(values))
            stats["std"] = float(np.std(values))
            stats["min"] = float(np.min(values))
            stats["max"] = float(np.max(values))
        
        self.is_fitted = True
        logger.info(f"Normalizer fitted on {len(self.feature_stats)} features")
        
        return self
    
    def transform(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Transform features using fitted statistics
        
        Args:
            features: Dictionary of feature values
            
        Returns:
            Normalized features
        """
        if not self.is_fitted and not self.feature_stats:
            # If not fitted, perform online normalization
            return self._online_normalize(features)
        
        normalized = {}
        
        for key, value in features.items():
            if key in self.feature_stats:
                stats = self.feature_stats[key]
                
                if self.method == "standard":
                    # Z-score normalization
                    if stats["std"] > 0:
                        normalized[key] = (value - stats["mean"]) / stats["std"]
                    else:
                        normalized[key] = 0.0
                
                elif self.method == "minmax":
                    # Min-max normalization to [0, 1]
                    if stats["max"] > stats["min"]:
                        normalized[key] = (value - stats["min"]) / (stats["max"] - stats["min"])
                    else:
                        normalized[key] = 0.0
                
                elif self.method == "robust":
                    # Robust scaling (less sensitive to outliers)
                    iqr = stats.get("iqr", stats["std"])
                    if iqr > 0:
                        normalized[key] = (value - stats["mean"]) / iqr
                    else:
                        normalized[key] = 0.0
                
                else:
                    normalized[key] = value
            else:
                # Unknown feature, pass through
                normalized[key] = value
        
        return normalized
    
    def _online_normalize(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Perform online normalization without pre-fitting
        
        Args:
            features: Input features
            
        Returns:
            Normalized features
        """
        # Simple online normalization using running statistics
        normalized = {}
        
        for key, value in features.items():
            if key not in self.feature_stats:
                self.feature_stats[key] = {
                    "mean": value,
                    "std": 1.0,
                    "min": value,
                    "max": value,
                    "count": 1
                }
                normalized[key] = 0.0
            else:
                stats = self.feature_stats[key]
                
                # Update running statistics
                n = stats["count"]
                old_mean = stats["mean"]
                new_mean = (old_mean * n + value) / (n + 1)
                
                stats["mean"] = new_mean
                stats["min"] = min(stats["min"], value)
                stats["max"] = max(stats["max"], value)
                stats["count"] = n + 1
                
                # Normalize
                if self.method == "standard":
                    if stats["std"] > 0:
                        normalized[key] = (value - stats["mean"]) / stats["std"]
                    else:
                        normalized[key] = 0.0
                else:
                    normalized[key] = value
        
        return normalized
    
    def fit_transform(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Fit and transform in one step
        
        Args:
            features: Input features
            
        Returns:
            Normalized features
        """
        self.fit(features)
        return self.transform(features)
    
    def save(self, path: str):
        """
        Save normalizer to disk
        
        Args:
            path: Path to save the normalizer
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        
        logger.info(f"Normalizer saved to {path}")
    
    @classmethod
    def load(cls, path: str) -> 'Normalizer':
        """
        Load normalizer from disk
        
        Args:
            path: Path to load the normalizer from
            
        Returns:
            Loaded normalizer
        """
        with open(path, 'rb') as f:
            normalizer = pickle.load(f)
        
        logger.info(f"Normalizer loaded from {path}")
        return normalizer
