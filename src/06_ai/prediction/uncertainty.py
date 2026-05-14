#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Uncertainty Quantification Module

Monte Carlo Dropout을 사용하여 예측 불확실성을 정량화합니다.
- MC Dropout으로 예측 구간 계산
- 신뢰 구간 (Confidence Interval) 생성
- 불확실성 점수 (Entropy) 계산
"""

import logging
from typing import Dict, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


class UncertaintyQuantifier:
    """
    Monte Carlo Dropout 기반 불확실성 정량화
    """
    
    def __init__(self, n_iterations: int = 100, confidence_level: float = 0.95):
        """
        Initialize Uncertainty Quantifier
        
        Args:
            n_iterations: MC Dropout 반복 횟수
            confidence_level: 신뢰 수준 (0.95 = 95% CI)
        """
        self.n_iterations = n_iterations
        self.confidence_level = confidence_level
        logger.info(f"Uncertainty Quantifier initialized (iterations: {n_iterations})")
    
    def mc_dropout_predict(
        self,
        model,
        X: np.ndarray,
        training: bool = True
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Monte Carlo Dropout 예측
        
        Args:
            model: 학습된 모델 (Dropout 레이어 포함)
            X: 입력 데이터
            training: Training 모드 (Dropout 활성화)
        
        Returns:
            (평균 예측값, 표준편차, 모든 예측값)
        """
        try:
            predictions = []
            
            # Multiple forward passes with dropout enabled
            for i in range(self.n_iterations):
                # For TensorFlow/Keras models
                if hasattr(model, 'predict'):
                    # Check if it's a Keras model
                    try:
                        import tensorflow as tf
                        # Enable dropout during inference
                        pred = model(X, training=training).numpy()
                    except (ImportError, AttributeError):
                        # Fallback to regular predict
                        pred = model.predict(X, verbose=0)
                else:
                    # For PyTorch models
                    try:
                        import torch
                        model.train()  # Enable dropout
                        with torch.no_grad():
                            pred = model(torch.FloatTensor(X)).numpy()
                    except (ImportError, AttributeError):
                        # Fallback: assume it's a callable
                        pred = model(X)
                
                predictions.append(pred)
            
            predictions = np.array(predictions)
            
            # Calculate statistics
            mean_pred = np.mean(predictions, axis=0)
            std_pred = np.std(predictions, axis=0)
            
            logger.info(f"MC Dropout completed: {self.n_iterations} iterations")
            
            return mean_pred, std_pred, predictions
            
        except Exception as e:
            logger.error(f"MC Dropout failed: {e}")
            # Fallback: single prediction with zero uncertainty
            try:
                pred = model.predict(X) if hasattr(model, 'predict') else model(X)
                return pred, np.zeros_like(pred), np.array([pred])
            except:
                raise
    
    def calculate_confidence_interval(
        self,
        predictions: np.ndarray,
        confidence_level: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        신뢰 구간 계산
        
        Args:
            predictions: MC Dropout 예측값 배열 (n_iterations, n_samples, ...)
            confidence_level: 신뢰 수준 (None인 경우 초기화 시 값 사용)
        
        Returns:
            (하한, 상한)
        """
        if confidence_level is None:
            confidence_level = self.confidence_level
        
        # Calculate percentiles
        alpha = 1 - confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100
        
        lower_bound = np.percentile(predictions, lower_percentile, axis=0)
        upper_bound = np.percentile(predictions, upper_percentile, axis=0)
        
        logger.info(f"{confidence_level*100:.0f}% confidence interval calculated")
        
        return lower_bound, upper_bound
    
    def calculate_entropy(self, predictions: np.ndarray) -> np.ndarray:
        """
        예측 불확실성 점수 (Entropy) 계산
        
        Args:
            predictions: MC Dropout 예측값 배열
        
        Returns:
            Entropy 값 (높을수록 불확실)
        """
        try:
            # Normalize predictions to probabilities
            # Assume predictions are already probabilities for classification
            # For regression, use variance as uncertainty measure
            
            if predictions.ndim == 2:
                # Classification case
                # Calculate entropy: -sum(p * log(p))
                epsilon = 1e-10
                predictions_clipped = np.clip(predictions, epsilon, 1 - epsilon)
                entropy = -np.sum(predictions_clipped * np.log(predictions_clipped), axis=1)
            else:
                # Regression case: use coefficient of variation
                mean_pred = np.mean(predictions, axis=0)
                std_pred = np.std(predictions, axis=0)
                # Normalize by mean to get relative uncertainty
                entropy = std_pred / (np.abs(mean_pred) + 1e-10)
            
            return entropy
            
        except Exception as e:
            logger.error(f"Failed to calculate entropy: {e}")
            return np.zeros(predictions.shape[1] if predictions.ndim > 1 else 1)
    
    def quantify_uncertainty(
        self,
        model,
        X: np.ndarray,
        return_all_predictions: bool = False
    ) -> Dict:
        """
        완전한 불확실성 정량화
        
        Args:
            model: 학습된 모델
            X: 입력 데이터
            return_all_predictions: 모든 예측값 반환 여부
        
        Returns:
            불확실성 정보를 담은 딕셔너리
        """
        # MC Dropout prediction
        mean_pred, std_pred, all_predictions = self.mc_dropout_predict(model, X)
        
        # Confidence intervals
        lower_bound, upper_bound = self.calculate_confidence_interval(all_predictions)
        
        # Entropy/uncertainty score
        uncertainty_score = np.mean(std_pred)  # Average uncertainty
        
        result = {
            'mean_prediction': mean_pred,
            'std_prediction': std_pred,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'confidence_level': self.confidence_level,
            'uncertainty_score': float(uncertainty_score),
            'n_iterations': self.n_iterations
        }
        
        if return_all_predictions:
            result['all_predictions'] = all_predictions
        
        logger.info(f"Uncertainty quantified: score={uncertainty_score:.4f}")
        
        return result
    
    def interpret_uncertainty(self, uncertainty_score: float) -> str:
        """
        불확실성 점수 해석
        
        Args:
            uncertainty_score: 불확실성 점수
        
        Returns:
            해석 메시지
        """
        if uncertainty_score < 0.1:
            return "매우 신뢰도 높음 (High Confidence)"
        elif uncertainty_score < 0.3:
            return "신뢰도 높음 (Good Confidence)"
        elif uncertainty_score < 0.5:
            return "보통 신뢰도 (Moderate Confidence)"
        elif uncertainty_score < 0.7:
            return "낮은 신뢰도 (Low Confidence)"
        else:
            return "매우 낮은 신뢰도 (Very Low Confidence)"


def estimate_prediction_uncertainty(
    model,
    X: np.ndarray,
    n_iterations: int = 100,
    confidence_level: float = 0.95
) -> Dict:
    """
    Convenience function for uncertainty estimation
    
    Args:
        model: 학습된 모델
        X: 입력 데이터
        n_iterations: MC Dropout 반복 횟수
        confidence_level: 신뢰 수준
    
    Returns:
        불확실성 정보
    """
    quantifier = UncertaintyQuantifier(n_iterations, confidence_level)
    return quantifier.quantify_uncertainty(model, X)


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic model (simple function with noise)
    class SimpleModel:
        def predict(self, X):
            # Simulate prediction with noise (like dropout)
            noise = np.random.randn(*X.shape) * 0.1
            return np.sum(X + noise, axis=1, keepdims=True)
    
    # Create test data
    np.random.seed(42)
    X_test = np.random.randn(10, 5)
    
    # Create model and quantifier
    model = SimpleModel()
    quantifier = UncertaintyQuantifier(n_iterations=50)
    
    # Quantify uncertainty
    result = quantify_uncertainty(model, X_test)
    
    print("Uncertainty Quantification Results:")
    print(f"  Mean prediction shape: {result['mean_prediction'].shape}")
    print(f"  Uncertainty score: {result['uncertainty_score']:.4f}")
    print(f"  Interpretation: {quantifier.interpret_uncertainty(result['uncertainty_score'])}")
    print(f"  Confidence level: {result['confidence_level']*100:.0f}%")
