#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prediction Logic

Business logic for machine learning prediction including:
- LSTM, GRU, Transformer deep learning models
- XGBoost and LightGBM gradient boosting models
- Data preprocessing and feature engineering
- Model training and evaluation
- Backtesting
"""

import logging
import pickle
from typing import Dict, Optional, Callable, List
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class PredictionLogic:
    """
    Prediction Business Logic
    
    Handles machine learning model training, prediction, and evaluation
    """
    
    def __init__(self):
        """Initialize Prediction Logic"""
        self.model = None
        self.model_type = None
        self.scaler = None
        self.data_source = None
        self.lookback = 60
        
        # Data storage
        self.X_train = None
        self.y_train = None
        self.X_val = None
        self.y_val = None
        self.X_test = None
        self.y_test = None
        
        # Historical data for charting
        self.historical_data = None
        
        logger.info("Prediction Logic initialized")
    
    def prepare_data(self, data_source: str, lookback: int = 60):
        """
        Prepare data for training
        
        Args:
            data_source: Data source type (Price, Technical Indicators, etc.)
            lookback: Number of previous time steps to use
        
        Returns:
            Tuple of (X_train, y_train, X_val, y_val, X_test, y_test)
        """
        logger.info(f"Preparing data: {data_source}, lookback={lookback}")
        
        try:
            # TODO: Implement actual data loading from database or API
            # For now, generate synthetic data for demonstration
            
            # Generate synthetic price data (random walk)
            np.random.seed(42)
            n_samples = 1000
            returns = np.random.randn(n_samples) * 0.02  # 2% volatility
            prices = 100 * np.exp(np.cumsum(returns))
            
            # Add trend and seasonality
            trend = np.linspace(0, 20, n_samples)
            seasonality = 5 * np.sin(np.linspace(0, 4*np.pi, n_samples))
            prices = prices + trend + seasonality
            
            # Create features based on data source
            if data_source == "Price (OHLCV)":
                # Use price data only
                data = prices.reshape(-1, 1)
            elif data_source == "Technical Indicators":
                # Add technical indicators (simplified)
                sma_20 = self._calculate_sma(prices, 20)
                sma_50 = self._calculate_sma(prices, 50)
                rsi = self._calculate_rsi(prices, 14)
                data = np.column_stack([prices, sma_20, sma_50, rsi])
            elif data_source == "Order Book":
                # Simulate order book data
                bid_price = prices * 0.999
                ask_price = prices * 1.001
                volume = np.random.uniform(100, 1000, n_samples)
                data = np.column_stack([prices, bid_price, ask_price, volume])
            else:  # Combined
                # Combine all features
                sma_20 = self._calculate_sma(prices, 20)
                rsi = self._calculate_rsi(prices, 14)
                volume = np.random.uniform(100, 1000, n_samples)
                data = np.column_stack([prices, sma_20, rsi, volume])
            
            # Normalize data
            from sklearn.preprocessing import MinMaxScaler
            self.scaler = MinMaxScaler()
            data_normalized = self.scaler.fit_transform(data)
            
            # Create sequences
            X, y = [], []
            for i in range(lookback, len(data_normalized)):
                X.append(data_normalized[i-lookback:i])
                y.append(data_normalized[i, 0])  # Predict first feature (price)
            
            X = np.array(X)
            y = np.array(y)
            
            # Split data: 70% train, 15% validation, 15% test
            train_size = int(len(X) * 0.7)
            val_size = int(len(X) * 0.15)
            
            self.X_train = X[:train_size]
            self.y_train = y[:train_size]
            self.X_val = X[train_size:train_size+val_size]
            self.y_val = y[train_size:train_size+val_size]
            self.X_test = X[train_size+val_size:]
            self.y_test = y[train_size+val_size:]
            
            # Store historical data
            self.historical_data = prices[:train_size+val_size]
            
            logger.info(f"Data prepared: Train={len(self.X_train)}, Val={len(self.X_val)}, Test={len(self.X_test)}")
            
            return self.X_train, self.y_train, self.X_val, self.y_val, self.X_test, self.y_test
            
        except Exception as e:
            logger.error(f"Failed to prepare data: {e}")
            raise
    
    def _calculate_sma(self, data, window):
        """Calculate Simple Moving Average"""
        sma = np.zeros_like(data)
        for i in range(window-1, len(data)):
            sma[i] = np.mean(data[i-window+1:i+1])
        # Fill initial values
        sma[:window-1] = sma[window-1]
        return sma
    
    def _calculate_rsi(self, data, window=14):
        """Calculate Relative Strength Index"""
        deltas = np.diff(data)
        seed = deltas[:window+1]
        up = seed[seed >= 0].sum() / window
        down = -seed[seed < 0].sum() / window
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(data)
        rsi[:window] = 100. - 100. / (1. + rs)
        
        for i in range(window, len(data)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            
            up = (up * (window - 1) + upval) / window
            down = (down * (window - 1) + downval) / window
            rs = up / down if down != 0 else 0
            rsi[i] = 100. - 100. / (1. + rs)
        
        return rsi
    
    def train_model(self, model_type: str, data_source: str, lookback: int,
                    progress_callback: Optional[Callable] = None) -> Dict:
        """
        Train machine learning model
        
        Args:
            model_type: Model type (LSTM, GRU, Transformer, XGBoost, LightGBM)
            data_source: Data source type
            lookback: Lookback window size
            progress_callback: Callback function(epoch, total_epochs, loss)
        
        Returns:
            Dictionary of training metrics
        """
        logger.info(f"Training model: {model_type}")
        
        self.model_type = model_type
        self.data_source = data_source
        self.lookback = lookback
        
        # Prepare data
        self.prepare_data(data_source, lookback)
        
        try:
            if model_type in ["LSTM", "GRU", "Transformer"]:
                metrics = self._train_deep_learning_model(model_type, progress_callback)
            elif model_type in ["XGBoost", "LightGBM"]:
                metrics = self._train_gradient_boosting_model(model_type, progress_callback)
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            logger.info(f"Training completed: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to train model: {e}")
            raise
    
    def _train_deep_learning_model(self, model_type: str,
                                   progress_callback: Optional[Callable] = None) -> Dict:
        """Train deep learning model (LSTM, GRU, Transformer)"""
        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras import layers
            
            # Model architecture
            input_shape = (self.X_train.shape[1], self.X_train.shape[2])
            
            model = keras.Sequential()
            
            if model_type == "LSTM":
                model.add(layers.LSTM(128, return_sequences=True, input_shape=input_shape))
                model.add(layers.Dropout(0.2))
                model.add(layers.LSTM(64, return_sequences=True))
                model.add(layers.Dropout(0.2))
                model.add(layers.LSTM(32))
                model.add(layers.Dropout(0.2))
            elif model_type == "GRU":
                model.add(layers.GRU(128, return_sequences=True, input_shape=input_shape))
                model.add(layers.Dropout(0.2))
                model.add(layers.GRU(64, return_sequences=True))
                model.add(layers.Dropout(0.2))
                model.add(layers.GRU(32))
                model.add(layers.Dropout(0.2))
            elif model_type == "Transformer":
                # Simplified Transformer architecture
                inputs = layers.Input(shape=input_shape)
                x = layers.MultiHeadAttention(num_heads=4, key_dim=32)(inputs, inputs)
                x = layers.Dropout(0.1)(x)
                x = layers.LayerNormalization(epsilon=1e-6)(x)
                x = layers.GlobalAveragePooling1D()(x)
                x = layers.Dense(64, activation="relu")(x)
                x = layers.Dropout(0.1)(x)
                
                model = keras.Model(inputs=inputs, outputs=x)
            
            # Add output layer
            if model_type != "Transformer":
                model.add(layers.Dense(32, activation='relu'))
                model.add(layers.Dense(1))
            else:
                model.add(layers.Dense(1))
            
            # Compile model
            model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=0.001),
                loss='mse',
                metrics=['mae']
            )
            
            logger.info(f"Model architecture created: {model_type}")
            
            # Custom callback for progress
            class ProgressCallback(keras.callbacks.Callback):
                def __init__(self, callback_fn, total_epochs):
                    super().__init__()
                    self.callback_fn = callback_fn
                    self.total_epochs = total_epochs
                
                def on_epoch_end(self, epoch, logs=None):
                    if self.callback_fn:
                        loss = logs.get('loss', 0)
                        self.callback_fn(epoch + 1, self.total_epochs, loss)
            
            # Train model
            epochs = 50
            batch_size = 32
            
            callbacks = []
            if progress_callback:
                callbacks.append(ProgressCallback(progress_callback, epochs))
            
            callbacks.append(keras.callbacks.EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True
            ))
            
            history = model.fit(
                self.X_train, self.y_train,
                validation_data=(self.X_val, self.y_val),
                epochs=epochs,
                batch_size=batch_size,
                callbacks=callbacks,
                verbose=0
            )
            
            self.model = model
            
            # Evaluate model
            metrics = self._evaluate_model()
            
            return metrics
            
        except ImportError:
            logger.error("TensorFlow not installed. Install with: pip install tensorflow")
            raise ImportError("TensorFlow is required for deep learning models")
        except Exception as e:
            logger.error(f"Failed to train deep learning model: {e}")
            raise
    
    def _train_gradient_boosting_model(self, model_type: str,
                                       progress_callback: Optional[Callable] = None) -> Dict:
        """Train gradient boosting model (XGBoost, LightGBM)"""
        try:
            # Reshape data for gradient boosting (flatten sequences)
            X_train_flat = self.X_train.reshape(self.X_train.shape[0], -1)
            X_val_flat = self.X_val.reshape(self.X_val.shape[0], -1)
            X_test_flat = self.X_test.reshape(self.X_test.shape[0], -1)
            
            if model_type == "XGBoost":
                import xgboost as xgb
                
                # Create DMatrix
                dtrain = xgb.DMatrix(X_train_flat, label=self.y_train)
                dval = xgb.DMatrix(X_val_flat, label=self.y_val)
                
                # Parameters
                params = {
                    'objective': 'reg:squarederror',
                    'max_depth': 6,
                    'learning_rate': 0.1,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8,
                    'seed': 42
                }
                
                # Training with progress callback
                num_rounds = 100
                evals = [(dtrain, 'train'), (dval, 'val')]
                
                class XGBProgressCallback:
                    def __init__(self, callback_fn, total_rounds):
                        self.callback_fn = callback_fn
                        self.total_rounds = total_rounds
                    
                    def __call__(self, env):
                        if self.callback_fn and env.iteration % 5 == 0:
                            train_rmse = env.evaluation_result_list[0][1]
                            self.callback_fn(env.iteration, self.total_rounds, train_rmse)
                
                callbacks = []
                if progress_callback:
                    callbacks.append(XGBProgressCallback(progress_callback, num_rounds))
                
                self.model = xgb.train(
                    params,
                    dtrain,
                    num_rounds,
                    evals=evals,
                    early_stopping_rounds=10,
                    callbacks=callbacks,
                    verbose_eval=False
                )
                
            elif model_type == "LightGBM":
                import lightgbm as lgb
                
                # Create Dataset
                train_data = lgb.Dataset(X_train_flat, label=self.y_train)
                val_data = lgb.Dataset(X_val_flat, label=self.y_val, reference=train_data)
                
                # Parameters
                params = {
                    'objective': 'regression',
                    'metric': 'rmse',
                    'max_depth': 6,
                    'learning_rate': 0.1,
                    'num_leaves': 31,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8,
                    'seed': 42,
                    'verbose': -1
                }
                
                # Training with progress callback
                num_rounds = 100
                
                class LGBProgressCallback:
                    def __init__(self, callback_fn, total_rounds):
                        self.callback_fn = callback_fn
                        self.total_rounds = total_rounds
                    
                    def __call__(self, env):
                        if self.callback_fn and env.iteration % 5 == 0:
                            train_rmse = env.evaluation_result_list[0][2]
                            self.callback_fn(env.iteration, self.total_rounds, train_rmse)
                
                callbacks = []
                if progress_callback:
                    callbacks.append(LGBProgressCallback(progress_callback, num_rounds))
                
                self.model = lgb.train(
                    params,
                    train_data,
                    num_boost_round=num_rounds,
                    valid_sets=[train_data, val_data],
                    valid_names=['train', 'val'],
                    callbacks=callbacks
                )
            
            # Store flattened test data for later use
            self.X_test_flat = X_test_flat
            
            # Evaluate model
            metrics = self._evaluate_model_gb()
            
            return metrics
            
        except ImportError as e:
            logger.error(f"{model_type} not installed: {e}")
            raise ImportError(f"{model_type} is required. Install with: pip install {model_type.lower()}")
        except Exception as e:
            logger.error(f"Failed to train gradient boosting model: {e}")
            raise
    
    def _evaluate_model(self) -> Dict:
        """Evaluate deep learning model"""
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        
        # Predictions
        y_train_pred = self.model.predict(self.X_train, verbose=0).flatten()
        y_val_pred = self.model.predict(self.X_val, verbose=0).flatten()
        y_test_pred = self.model.predict(self.X_test, verbose=0).flatten()
        
        # Calculate metrics
        metrics = {
            'train_mae': mean_absolute_error(self.y_train, y_train_pred),
            'train_rmse': np.sqrt(mean_squared_error(self.y_train, y_train_pred)),
            'train_r2': r2_score(self.y_train, y_train_pred),
            'val_mae': mean_absolute_error(self.y_val, y_val_pred),
            'val_rmse': np.sqrt(mean_squared_error(self.y_val, y_val_pred)),
            'val_r2': r2_score(self.y_val, y_val_pred),
            'test_mae': mean_absolute_error(self.y_test, y_test_pred),
            'test_rmse': np.sqrt(mean_squared_error(self.y_test, y_test_pred)),
            'test_r2': r2_score(self.y_test, y_test_pred),
        }
        
        # Calculate Sharpe Ratio (simplified)
        metrics['train_sharpe'] = self._calculate_sharpe_ratio(self.y_train, y_train_pred)
        metrics['val_sharpe'] = self._calculate_sharpe_ratio(self.y_val, y_val_pred)
        metrics['test_sharpe'] = self._calculate_sharpe_ratio(self.y_test, y_test_pred)
        
        return metrics
    
    def _evaluate_model_gb(self) -> Dict:
        """Evaluate gradient boosting model"""
        import xgboost as xgb
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        
        # Reshape data
        X_train_flat = self.X_train.reshape(self.X_train.shape[0], -1)
        X_val_flat = self.X_val.reshape(self.X_val.shape[0], -1)
        
        # Predictions
        if self.model_type == "XGBoost":
            y_train_pred = self.model.predict(xgb.DMatrix(X_train_flat))
            y_val_pred = self.model.predict(xgb.DMatrix(X_val_flat))
            y_test_pred = self.model.predict(xgb.DMatrix(self.X_test_flat))
        else:  # LightGBM
            y_train_pred = self.model.predict(X_train_flat)
            y_val_pred = self.model.predict(X_val_flat)
            y_test_pred = self.model.predict(self.X_test_flat)
        
        # Calculate metrics
        metrics = {
            'train_mae': mean_absolute_error(self.y_train, y_train_pred),
            'train_rmse': np.sqrt(mean_squared_error(self.y_train, y_train_pred)),
            'train_r2': r2_score(self.y_train, y_train_pred),
            'val_mae': mean_absolute_error(self.y_val, y_val_pred),
            'val_rmse': np.sqrt(mean_squared_error(self.y_val, y_val_pred)),
            'val_r2': r2_score(self.y_val, y_val_pred),
            'test_mae': mean_absolute_error(self.y_test, y_test_pred),
            'test_rmse': np.sqrt(mean_squared_error(self.y_test, y_test_pred)),
            'test_r2': r2_score(self.y_test, y_test_pred),
        }
        
        # Calculate Sharpe Ratio
        metrics['train_sharpe'] = self._calculate_sharpe_ratio(self.y_train, y_train_pred)
        metrics['val_sharpe'] = self._calculate_sharpe_ratio(self.y_val, y_val_pred)
        metrics['test_sharpe'] = self._calculate_sharpe_ratio(self.y_test, y_test_pred)
        
        return metrics
    
    def _calculate_sharpe_ratio(self, y_true, y_pred, risk_free_rate=0.0):
        """Calculate Sharpe Ratio"""
        returns = (y_pred - y_true) / y_true
        excess_returns = returns - risk_free_rate
        
        if len(excess_returns) == 0 or np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        return sharpe * np.sqrt(252)  # Annualized
    
    def predict(self, steps: int = 10) -> Optional[np.ndarray]:
        """
        Generate predictions
        
        Args:
            steps: Number of steps to predict
        
        Returns:
            Array of predictions
        """
        if self.model is None:
            logger.warning("No model available for prediction")
            return None
        
        try:
            # Use last sequence from test data
            if self.X_test is None or len(self.X_test) == 0:
                logger.warning("No test data available")
                return None
            
            last_sequence = self.X_test[-1:].copy()
            predictions = []
            
            for _ in range(steps):
                if self.model_type in ["LSTM", "GRU", "Transformer"]:
                    pred = self.model.predict(last_sequence, verbose=0)[0, 0]
                else:  # XGBoost, LightGBM
                    import xgboost as xgb
                    seq_flat = last_sequence.reshape(1, -1)
                    if self.model_type == "XGBoost":
                        pred = self.model.predict(xgb.DMatrix(seq_flat))[0]
                    else:
                        pred = self.model.predict(seq_flat)[0]
                
                predictions.append(pred)
                
                # Update sequence (simple approach: shift and append)
                last_sequence = np.roll(last_sequence, -1, axis=1)
                last_sequence[0, -1, 0] = pred
            
            # Inverse transform predictions
            predictions = np.array(predictions).reshape(-1, 1)
            
            # Create dummy array for inverse transform
            dummy = np.zeros((len(predictions), self.scaler.n_features_in_))
            dummy[:, 0] = predictions.flatten()
            predictions_rescaled = self.scaler.inverse_transform(dummy)[:, 0]
            
            logger.info(f"Generated {len(predictions_rescaled)} predictions")
            return predictions_rescaled
            
        except Exception as e:
            logger.error(f"Failed to predict: {e}")
            return None
    
    def backtest(self) -> Optional[Dict]:
        """
        Run backtest on test data
        
        Returns:
            Dictionary of backtest results
        """
        if self.model is None:
            logger.warning("No model available for backtesting")
            return None
        
        try:
            # Generate predictions on test set
            if self.model_type in ["LSTM", "GRU", "Transformer"]:
                predictions = self.model.predict(self.X_test, verbose=0).flatten()
            else:  # XGBoost, LightGBM
                import xgboost as xgb
                if self.model_type == "XGBoost":
                    predictions = self.model.predict(xgb.DMatrix(self.X_test_flat))
                else:
                    predictions = self.model.predict(self.X_test_flat)
            
            # Inverse transform
            dummy_actual = np.zeros((len(self.y_test), self.scaler.n_features_in_))
            dummy_actual[:, 0] = self.y_test
            actual_prices = self.scaler.inverse_transform(dummy_actual)[:, 0]
            
            dummy_pred = np.zeros((len(predictions), self.scaler.n_features_in_))
            dummy_pred[:, 0] = predictions
            predicted_prices = self.scaler.inverse_transform(dummy_pred)[:, 0]
            
            # Calculate returns
            actual_returns = np.diff(actual_prices) / actual_prices[:-1]
            predicted_returns = np.diff(predicted_prices) / predicted_prices[:-1]
            
            # Simple strategy: buy if predicted return > 0
            strategy_returns = []
            for i in range(len(predicted_returns)):
                if predicted_returns[i] > 0:
                    strategy_returns.append(actual_returns[i])
                else:
                    strategy_returns.append(0)
            
            strategy_returns = np.array(strategy_returns)
            
            # Calculate metrics
            total_return = np.sum(strategy_returns) * 100
            sharpe_ratio = self._calculate_sharpe_ratio(
                actual_prices[1:], predicted_prices[1:]
            )
            
            # Calculate max drawdown
            cumulative = np.cumprod(1 + strategy_returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdown) * 100
            
            results = {
                'actual': actual_prices.tolist(),
                'predicted': predicted_prices.tolist(),
                'total_return': total_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'win_rate': (strategy_returns > 0).sum() / len(strategy_returns) * 100
            }
            
            logger.info(f"Backtest completed: Return={total_return:.2f}%, Sharpe={sharpe_ratio:.3f}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to backtest: {e}")
            return None
    
    def save_model(self, file_path: str):
        """
        Save model to file
        
        Args:
            file_path: Path to save model
        """
        if self.model is None:
            raise ValueError("No model to save")
        
        try:
            if self.model_type in ["LSTM", "GRU", "Transformer"]:
                # Save Keras model
                self.model.save(file_path)
            else:
                # Save gradient boosting model
                with open(file_path, 'wb') as f:
                    pickle.dump({
                        'model': self.model,
                        'model_type': self.model_type,
                        'scaler': self.scaler,
                        'lookback': self.lookback
                    }, f)
            
            logger.info(f"Model saved: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            raise
    
    def load_model(self, file_path: str):
        """
        Load model from file
        
        Args:
            file_path: Path to model file
        """
        try:
            if file_path.endswith('.h5'):
                # Load Keras model
                import tensorflow as tf
                self.model = tf.keras.models.load_model(file_path)
                # Try to infer model type from architecture
                layer_types = [type(layer).__name__ for layer in self.model.layers]
                if 'LSTM' in layer_types:
                    self.model_type = 'LSTM'
                elif 'GRU' in layer_types:
                    self.model_type = 'GRU'
                else:
                    self.model_type = 'Transformer'
            else:
                # Load gradient boosting model
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                    self.model = data['model']
                    self.model_type = data.get('model_type', 'XGBoost')
                    self.scaler = data.get('scaler')
                    self.lookback = data.get('lookback', 60)
            
            logger.info(f"Model loaded: {file_path}, Type: {self.model_type}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def get_historical_data(self) -> Optional[np.ndarray]:
        """Get historical data for charting"""
        return self.historical_data
