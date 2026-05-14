# -*- coding: utf-8 -*-
"""
AI Price Predictor - LSTM-based price prediction
Predicts future price movements with confidence intervals
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List
from PyQt5.QtCore import QThread, pyqtSignal
import logging

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch not installed. AI prediction features will be limited.")


class LSTMPredictor(nn.Module):
    """LSTM model for price prediction"""
    
    def __init__(self, input_size=5, hidden_size=50, num_layers=2, output_size=1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
    
    def forward(self, x):
        # Initialize hidden state
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))
        
        # Decode the hidden state of the last time step
        out = self.fc(out[:, -1, :])
        return out


class PricePredictor:
    """
    Price prediction engine using LSTM.
    
    Features:
    - Predicts future price movements (up to 30 candles)
    - Provides confidence intervals
    - Uses OHLCV data for training
    """
    
    def __init__(self):
        self.model = None
        self.scaler_X = None
        self.scaler_y = None
        self.sequence_length = 60  # Use 60 candles for prediction
        
        if HAS_TORCH:
            self.model = LSTMPredictor(
                input_size=5,  # OHLCV
                hidden_size=50,
                num_layers=2,
                output_size=1
            )
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            self.model.to(self.device)
    
    def prepare_data(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare data for LSTM training.
        
        Args:
            data: DataFrame with OHLCV columns
        
        Returns:
            X, y: Input sequences and target values
        """
        # Extract features (OHLCV)
        features = data[['open', 'high', 'low', 'close', 'volume']].values
        
        # Create sequences
        X, y = [], []
        for i in range(len(features) - self.sequence_length):
            X.append(features[i:i + self.sequence_length])
            y.append(features[i + self.sequence_length, 3])  # Close price
        
        return np.array(X), np.array(y)
    
    def train(self, data: pd.DataFrame, epochs: int = 50):
        """
        Train the LSTM model.
        
        Args:
            data: Historical OHLCV data
            epochs: Number of training epochs
        """
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is required for training")
        
        # Prepare data
        X, y = self.prepare_data(data)
        
        # Normalize data
        from sklearn.preprocessing import MinMaxScaler
        self.scaler_X = MinMaxScaler()
        self.scaler_y = MinMaxScaler()
        
        X_scaled = self.scaler_X.fit_transform(X.reshape(-1, 5)).reshape(X.shape)
        y_scaled = self.scaler_y.fit_transform(y.reshape(-1, 1)).flatten()
        
        # Convert to tensors
        X_tensor = torch.FloatTensor(X_scaled).to(self.device)
        y_tensor = torch.FloatTensor(y_scaled).to(self.device)
        
        # Training
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        
        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = criterion(outputs.squeeze(), y_tensor)
            loss.backward()
            optimizer.step()
            
            if (epoch + 1) % 10 == 0:
                logger.info(f'Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}')
    
    def predict(self, data: pd.DataFrame, steps: int = 30) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Predict future prices.
        
        Args:
            data: Recent OHLCV data (at least sequence_length candles)
            steps: Number of future candles to predict
        
        Returns:
            predictions: Predicted prices
            upper_bound: Upper confidence interval
            lower_bound: Lower confidence interval
        """
        if not HAS_TORCH:
            # Fallback: Simple linear extrapolation
            recent_prices = data['close'].values[-10:]
            trend = (recent_prices[-1] - recent_prices[0]) / len(recent_prices)
            predictions = np.array([recent_prices[-1] + trend * i for i in range(1, steps + 1)])
            confidence = recent_prices.std() * 1.96  # 95% confidence
            return predictions, predictions + confidence, predictions - confidence
        
        # Use trained model
        if self.model is None or self.scaler_X is None:
            raise RuntimeError("Model not trained. Call train() first.")
        
        self.model.eval()
        predictions = []
        
        # Get last sequence
        features = data[['open', 'high', 'low', 'close', 'volume']].values[-self.sequence_length:]
        
        with torch.no_grad():
            for _ in range(steps):
                # Scale input
                input_scaled = self.scaler_X.transform(features.reshape(-1, 5)).reshape(1, self.sequence_length, 5)
                input_tensor = torch.FloatTensor(input_scaled).to(self.device)
                
                # Predict
                pred_scaled = self.model(input_tensor).cpu().numpy()
                pred = self.scaler_y.inverse_transform(pred_scaled.reshape(-1, 1))[0, 0]
                predictions.append(pred)
                
                # Update sequence (simple approach: use predicted close for all OHLC)
                new_row = np.array([[pred, pred, pred, pred, features[-1, 4]]])
                features = np.vstack([features[1:], new_row])
        
        predictions = np.array(predictions)
        
        # Calculate confidence intervals (simple: ±2 * recent volatility)
        recent_volatility = data['close'].pct_change().std() * data['close'].iloc[-1]
        confidence = recent_volatility * 1.96  # 95% confidence
        
        upper_bound = predictions + confidence
        lower_bound = predictions - confidence
        
        return predictions, upper_bound, lower_bound
    
    def save_model(self, path: str):
        """Save trained model"""
        if not HAS_TORCH or self.model is None:
            return
        
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'scaler_X': self.scaler_X,
            'scaler_y': self.scaler_y,
        }, path)
    
    def load_model(self, path: str):
        """Load trained model"""
        if not HAS_TORCH:
            return
        
        checkpoint = torch.load(path)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.scaler_X = checkpoint['scaler_X']
        self.scaler_y = checkpoint['scaler_y']
        self.model.eval()


class PredictionWorker(QThread):
    """QThread worker for async price prediction"""
    
    finished = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)  # predictions, upper, lower
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, predictor: PricePredictor, data: pd.DataFrame, steps: int = 30):
        super().__init__()
        self.predictor = predictor
        self.data = data
        self.steps = steps
    
    def run(self):
        """Run prediction in background thread"""
        try:
            self.progress.emit(10)
            predictions, upper, lower = self.predictor.predict(self.data, self.steps)
            self.progress.emit(100)
            self.finished.emit(predictions, upper, lower)
        except Exception as e:
            self.error.emit(str(e))


class TrainingWorker(QThread):
    """QThread worker for async model training"""
    
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, predictor: PricePredictor, data: pd.DataFrame, epochs: int = 50):
        super().__init__()
        self.predictor = predictor
        self.data = data
        self.epochs = epochs
    
    def run(self):
        """Run training in background thread"""
        try:
            self.progress.emit(0)
            self.predictor.train(self.data, self.epochs)
            self.progress.emit(100)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
