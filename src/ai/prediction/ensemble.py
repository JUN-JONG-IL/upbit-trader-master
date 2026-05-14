#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ensemble Meta-Learner Module

여러 모델의 예측을 결합하여 최종 예측을 생성합니다.
- LSTM, Transformer, XGBoost 예측값 결합
- Meta-Learner (Stacking) 구현
- Dynamic Weighting (최근 성능 기반)
- Optuna 하이퍼파라미터 최적화
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class EnsembleMetaLearner:
    """
    앙상블 Meta-Learner
    """
    
    def __init__(self, meta_model_type: str = "xgboost", dynamic_weighting: bool = True):
        """
        Initialize Ensemble Meta-Learner
        
        Args:
            meta_model_type: Meta-learner 모델 타입 ("xgboost", "linear", "neural")
            dynamic_weighting: 동적 가중치 사용 여부
        """
        self.meta_model_type = meta_model_type
        self.dynamic_weighting = dynamic_weighting
        self.meta_model = None
        self.base_models = {}
        self.weights = None
        self.performance_history = []
        
        logger.info(f"Ensemble Meta-Learner initialized (type: {meta_model_type})")
    
    def add_base_model(self, name: str, model, weight: float = 1.0):
        """
        Base 모델 추가
        
        Args:
            name: 모델 이름
            model: 모델 객체
            weight: 초기 가중치
        """
        self.base_models[name] = {
            'model': model,
            'weight': weight,
            'performance': []
        }
        logger.info(f"Base model added: {name} (weight: {weight})")
    
    def _create_meta_model(self):
        """Meta-learner 모델 생성"""
        try:
            if self.meta_model_type == "xgboost":
                import xgboost as xgb
                self.meta_model = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42
                )
            elif self.meta_model_type == "linear":
                from sklearn.linear_model import Ridge
                self.meta_model = Ridge(alpha=1.0)
            elif self.meta_model_type == "neural":
                from sklearn.neural_network import MLPRegressor
                self.meta_model = MLPRegressor(
                    hidden_layer_sizes=(64, 32),
                    max_iter=500,
                    random_state=42
                )
            else:
                # Default to simple averaging
                self.meta_model = None
            
            logger.info(f"Meta-model created: {self.meta_model_type}")
            
        except ImportError as e:
            logger.warning(f"Failed to import {self.meta_model_type}: {e}. Using simple averaging.")
            self.meta_model = None
    
    def train_meta_learner(self, X_meta: np.ndarray, y_true: np.ndarray):
        """
        Meta-learner 학습
        
        Args:
            X_meta: Base 모델들의 예측값 (n_samples, n_models)
            y_true: 실제 값
        """
        try:
            if self.meta_model is None:
                self._create_meta_model()
            
            if self.meta_model is not None:
                self.meta_model.fit(X_meta, y_true)
                logger.info("Meta-learner trained successfully")
            else:
                # Simple averaging
                logger.info("Using simple averaging (no meta-model)")
            
        except Exception as e:
            logger.error(f"Failed to train meta-learner: {e}")
    
    def predict(self, X: np.ndarray, return_base_predictions: bool = False) -> np.ndarray:
        """
        앙상블 예측
        
        Args:
            X: 입력 데이터
            return_base_predictions: Base 모델 예측값 반환 여부
        
        Returns:
            앙상블 예측값 (및 선택적으로 base 예측값)
        """
        try:
            # Get predictions from all base models
            base_predictions = []
            model_names = []
            
            for name, model_info in self.base_models.items():
                model = model_info['model']
                weight = model_info['weight']
                
                # Get prediction
                if hasattr(model, 'predict'):
                    pred = model.predict(X)
                else:
                    pred = model(X)
                
                # Ensure 1D array
                if pred.ndim > 1:
                    pred = pred.flatten()
                
                base_predictions.append(pred)
                model_names.append(name)
            
            # Stack predictions
            X_meta = np.column_stack(base_predictions)
            
            # Get ensemble prediction
            if self.meta_model is not None:
                # Use meta-learner
                ensemble_pred = self.meta_model.predict(X_meta)
            else:
                # Simple weighted averaging
                if self.dynamic_weighting and self.weights is not None:
                    weights = self.weights
                else:
                    weights = np.array([
                        self.base_models[name]['weight']
                        for name in model_names
                    ])
                
                # Normalize weights
                weights = weights / np.sum(weights)
                
                # Weighted average
                ensemble_pred = np.average(X_meta, axis=1, weights=weights)
            
            logger.info(f"Ensemble prediction completed ({len(self.base_models)} models)")
            
            if return_base_predictions:
                return ensemble_pred, {
                    'predictions': {name: pred for name, pred in zip(model_names, base_predictions)},
                    'weights': weights if 'weights' in locals() else None
                }
            else:
                return ensemble_pred
            
        except Exception as e:
            logger.error(f"Ensemble prediction failed: {e}")
            # Fallback: return first model's prediction
            if self.base_models:
                first_model = list(self.base_models.values())[0]['model']
                return first_model.predict(X) if hasattr(first_model, 'predict') else first_model(X)
            else:
                raise ValueError("No base models available")
    
    def update_weights(self, y_true: np.ndarray, X: Optional[np.ndarray] = None):
        """
        최근 성능 기반 동적 가중치 업데이트
        
        Args:
            y_true: 실제 값
            X: 입력 데이터 (새로운 예측이 필요한 경우)
        """
        try:
            if not self.dynamic_weighting:
                return
            
            # Get predictions from each base model
            performances = []
            
            for name, model_info in self.base_models.items():
                model = model_info['model']
                
                # Get prediction
                if X is not None:
                    if hasattr(model, 'predict'):
                        pred = model.predict(X)
                    else:
                        pred = model(X)
                    
                    # Calculate error (MSE)
                    if pred.ndim > 1:
                        pred = pred.flatten()
                    mse = np.mean((pred - y_true) ** 2)
                else:
                    # Use last recorded performance
                    if model_info['performance']:
                        mse = model_info['performance'][-1]
                    else:
                        mse = 1.0
                
                performances.append(mse)
                model_info['performance'].append(mse)
            
            # Convert errors to weights (inverse relationship)
            performances = np.array(performances)
            # Avoid division by zero
            performances = performances + 1e-10
            # Inverse: lower error = higher weight
            weights = 1.0 / performances
            
            # Normalize
            self.weights = weights / np.sum(weights)
            
            # Update model weights
            for i, name in enumerate(self.base_models.keys()):
                self.base_models[name]['weight'] = self.weights[i]
            
            logger.info(f"Weights updated: {dict(zip(self.base_models.keys(), self.weights))}")
            
        except Exception as e:
            logger.error(f"Failed to update weights: {e}")
    
    def optimize_with_optuna(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials: int = 50
    ) -> Dict:
        """
        Optuna를 사용한 하이퍼파라미터 최적화
        
        Args:
            X_train: 학습 데이터
            y_train: 학습 레이블
            X_val: 검증 데이터
            y_val: 검증 레이블
            n_trials: 시도 횟수
        
        Returns:
            최적화 결과
        """
        try:
            import optuna
            
            def objective(trial):
                # Suggest meta-model parameters
                if self.meta_model_type == "xgboost":
                    params = {
                        'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                        'max_depth': trial.suggest_int('max_depth', 2, 6),
                        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    }
                    
                    import xgboost as xgb
                    model = xgb.XGBRegressor(**params, random_state=42)
                    
                elif self.meta_model_type == "linear":
                    alpha = trial.suggest_float('alpha', 0.1, 10.0)
                    from sklearn.linear_model import Ridge
                    model = Ridge(alpha=alpha)
                    
                else:
                    return 0.0
                
                # Get base predictions
                base_train_preds = []
                base_val_preds = []
                
                for model_info in self.base_models.values():
                    base_model = model_info['model']
                    
                    train_pred = base_model.predict(X_train) if hasattr(base_model, 'predict') else base_model(X_train)
                    val_pred = base_model.predict(X_val) if hasattr(base_model, 'predict') else base_model(X_val)
                    
                    base_train_preds.append(train_pred.flatten())
                    base_val_preds.append(val_pred.flatten())
                
                X_meta_train = np.column_stack(base_train_preds)
                X_meta_val = np.column_stack(base_val_preds)
                
                # Train meta-model
                model.fit(X_meta_train, y_train)
                
                # Evaluate
                val_pred = model.predict(X_meta_val)
                mse = np.mean((val_pred - y_val) ** 2)
                
                return mse
            
            # Run optimization
            study = optuna.create_study(direction='minimize')
            study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
            
            logger.info(f"Optuna optimization completed: best MSE = {study.best_value:.6f}")
            
            return {
                'best_params': study.best_params,
                'best_value': study.best_value,
                'n_trials': n_trials
            }
            
        except ImportError:
            logger.error("Optuna not installed. Install with: pip install optuna")
            return {}
        except Exception as e:
            logger.error(f"Optuna optimization failed: {e}")
            return {}
    
    def get_model_contributions(self, X: np.ndarray) -> Dict:
        """
        각 모델의 기여도 분석
        
        Args:
            X: 입력 데이터
        
        Returns:
            모델별 기여도
        """
        try:
            _, info = self.predict(X, return_base_predictions=True)
            
            contributions = {}
            for name, pred in info['predictions'].items():
                contributions[name] = {
                    'mean_prediction': float(np.mean(pred)),
                    'std_prediction': float(np.std(pred)),
                    'weight': float(self.base_models[name]['weight'])
                }
            
            return contributions
            
        except Exception as e:
            logger.error(f"Failed to analyze contributions: {e}")
            return {}


def create_ensemble(
    models: Dict,
    meta_model_type: str = "xgboost",
    dynamic_weighting: bool = True
) -> EnsembleMetaLearner:
    """
    Convenience function for creating ensemble
    
    Args:
        models: 모델 딕셔너리 {name: model}
        meta_model_type: Meta-learner 타입
        dynamic_weighting: 동적 가중치 사용 여부
    
    Returns:
        EnsembleMetaLearner 인스턴스
    """
    ensemble = EnsembleMetaLearner(meta_model_type, dynamic_weighting)
    
    for name, model in models.items():
        ensemble.add_base_model(name, model)
    
    return ensemble


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic data
    np.random.seed(42)
    X = np.random.randn(100, 5)
    y = X[:, 0] * 2 + X[:, 1] - X[:, 2] * 0.5 + np.random.randn(100) * 0.1
    
    # Create simple models
    class Model1:
        def predict(self, X):
            return X[:, 0] * 2 + np.random.randn(len(X)) * 0.2
    
    class Model2:
        def predict(self, X):
            return X[:, 1] * 1 + np.random.randn(len(X)) * 0.2
    
    # Create ensemble
    models = {
        'model1': Model1(),
        'model2': Model2()
    }
    
    ensemble = create_ensemble(models, meta_model_type="xgboost")
    
    # Make predictions
    predictions = ensemble.predict(X)
    
    print("Ensemble Prediction Results:")
    print(f"  Shape: {predictions.shape}")
    print(f"  Mean: {np.mean(predictions):.4f}")
    print(f"  Std: {np.std(predictions):.4f}")
