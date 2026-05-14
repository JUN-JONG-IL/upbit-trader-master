#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SHAP Model Explainability

모델 예측의 설명 가능성을 제공합니다.
- SHAP (SHapley Additive exPlanations) 값 계산
- Feature Importance 시각화
- Waterfall Plot, Force Plot 생성
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class ModelExplainer:
    """
    SHAP 기반 모델 설명성 제공
    """
    
    def __init__(self):
        """Initialize Model Explainer"""
        self.explainer = None
        self.feature_names = None
        self.shap_values = None
        logger.info("Model Explainer initialized")
    
    def explain_prediction(
        self, 
        model, 
        X: np.ndarray, 
        feature_names: Optional[List[str]] = None,
        model_type: str = "tree"
    ) -> Dict:
        """
        예측에 대한 SHAP 설명 생성
        
        Args:
            model: 학습된 모델
            X: 입력 데이터
            feature_names: 특징 이름 리스트
            model_type: 모델 타입 ("tree", "linear", "deep" 등)
        
        Returns:
            SHAP 값과 설명 정보를 담은 딕셔너리
        """
        try:
            import shap
            
            # Create explainer based on model type
            if model_type == "tree":
                # For tree-based models (XGBoost, LightGBM, etc.)
                self.explainer = shap.TreeExplainer(model)
            elif model_type == "linear":
                # For linear models
                self.explainer = shap.LinearExplainer(model, X)
            elif model_type == "deep":
                # For deep learning models (use DeepExplainer or GradientExplainer)
                self.explainer = shap.DeepExplainer(model, X[:100])  # Use subset as background
            else:
                # Fallback to KernelExplainer (slower but model-agnostic)
                self.explainer = shap.KernelExplainer(
                    model.predict if hasattr(model, 'predict') else model,
                    shap.sample(X, 100)
                )
            
            # Calculate SHAP values
            self.shap_values = self.explainer.shap_values(X)
            self.feature_names = feature_names
            
            # Get feature importance
            if isinstance(self.shap_values, list):
                # Multi-class case
                shap_values_mean = np.abs(self.shap_values[0]).mean(axis=0)
            else:
                shap_values_mean = np.abs(self.shap_values).mean(axis=0)
            
            # Sort features by importance
            if feature_names is None:
                feature_names = [f"Feature {i}" for i in range(X.shape[1])]
            
            importance_dict = {
                name: float(importance) 
                for name, importance in zip(feature_names, shap_values_mean)
            }
            
            # Sort by importance (descending)
            sorted_features = sorted(
                importance_dict.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            result = {
                'shap_values': self.shap_values,
                'feature_importance': dict(sorted_features[:10]),  # Top 10
                'base_value': float(self.explainer.expected_value) if hasattr(self.explainer, 'expected_value') else 0.0,
                'feature_names': feature_names
            }
            
            logger.info(f"SHAP explanation generated for {X.shape[0]} samples")
            return result
            
        except ImportError:
            logger.error("SHAP library not installed. Install with: pip install shap")
            return {
                'error': 'SHAP library not installed',
                'feature_importance': {},
                'shap_values': None
            }
        except Exception as e:
            logger.error(f"Failed to generate SHAP explanation: {e}")
            return {
                'error': str(e),
                'feature_importance': {},
                'shap_values': None
            }
    
    def get_top_features(self, n: int = 10) -> List[Tuple[str, float]]:
        """
        상위 N개의 중요 특징 반환
        
        Args:
            n: 반환할 특징 개수
        
        Returns:
            (특징명, 중요도) 튜플 리스트
        """
        if self.shap_values is None or self.feature_names is None:
            logger.warning("SHAP values not calculated yet")
            return []
        
        try:
            # Calculate mean absolute SHAP values
            if isinstance(self.shap_values, list):
                shap_values_mean = np.abs(self.shap_values[0]).mean(axis=0)
            else:
                shap_values_mean = np.abs(self.shap_values).mean(axis=0)
            
            # Sort features
            indices = np.argsort(shap_values_mean)[::-1][:n]
            
            top_features = [
                (self.feature_names[i], float(shap_values_mean[i]))
                for i in indices
            ]
            
            return top_features
            
        except Exception as e:
            logger.error(f"Failed to get top features: {e}")
            return []
    
    def generate_waterfall_plot_data(self, sample_idx: int = 0) -> Dict:
        """
        Waterfall Plot 데이터 생성
        
        Args:
            sample_idx: 샘플 인덱스
        
        Returns:
            Waterfall plot 데이터
        """
        if self.shap_values is None or self.feature_names is None:
            logger.warning("SHAP values not calculated yet")
            return {}
        
        try:
            # Get SHAP values for the sample
            if isinstance(self.shap_values, list):
                values = self.shap_values[0][sample_idx]
            else:
                values = self.shap_values[sample_idx]
            
            # Sort by absolute value
            indices = np.argsort(np.abs(values))[::-1][:10]  # Top 10
            
            waterfall_data = {
                'features': [self.feature_names[i] for i in indices],
                'values': [float(values[i]) for i in indices],
                'base_value': float(self.explainer.expected_value) if hasattr(self.explainer, 'expected_value') else 0.0
            }
            
            return waterfall_data
            
        except Exception as e:
            logger.error(f"Failed to generate waterfall plot data: {e}")
            return {}
    
    def save_explanation(self, filepath: str):
        """
        설명 결과를 파일로 저장
        
        Args:
            filepath: 저장 경로
        """
        try:
            import pickle
            
            explanation_data = {
                'shap_values': self.shap_values,
                'feature_names': self.feature_names,
                'explainer_type': type(self.explainer).__name__
            }
            
            with open(filepath, 'wb') as f:
                pickle.dump(explanation_data, f)
            
            logger.info(f"Explanation saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save explanation: {e}")


def explain_model_prediction(
    model,
    X: np.ndarray,
    feature_names: Optional[List[str]] = None,
    model_type: str = "tree"
) -> Dict:
    """
    Convenience function for model explanation
    
    Args:
        model: 학습된 모델
        X: 입력 데이터
        feature_names: 특징 이름 리스트
        model_type: 모델 타입
    
    Returns:
        SHAP 설명 결과
    """
    explainer = ModelExplainer()
    return explainer.explain_prediction(model, X, feature_names, model_type)


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic data
    np.random.seed(42)
    X = np.random.randn(100, 5)
    y = X[:, 0] * 2 + X[:, 1] - X[:, 2] * 0.5 + np.random.randn(100) * 0.1
    
    # Train a simple model
    try:
        from sklearn.ensemble import RandomForestRegressor
        
        model = RandomForestRegressor(n_estimators=10, random_state=42)
        model.fit(X, y)
        
        # Explain predictions
        feature_names = [f"Feature_{i}" for i in range(5)]
        explanation = explain_model_prediction(model, X, feature_names, "tree")
        
        print("Feature Importance:")
        for name, importance in explanation['feature_importance'].items():
            print(f"  {name}: {importance:.4f}")
            
    except ImportError:
        print("scikit-learn or shap not installed")
