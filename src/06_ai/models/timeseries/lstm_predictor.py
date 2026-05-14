"""
LSTM Predictor - Long Short-Term Memory for time series prediction
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from ..base_predictor import BasePredictor

logger = logging.getLogger(__name__)


class LSTMPredictor(BasePredictor):
    """LSTM-based time series prediction model"""
    
    def __init__(self, model_name: str = "lstm-v1", config: Optional[Dict] = None):
        super().__init__(model_name, config)
        
        self.sequence_length = config.get("sequence_length", 20) if config else 20
        self.hidden_size = config.get("hidden_size", 64) if config else 64
        self.num_layers = config.get("num_layers", 2) if config else 2
        self.dropout = config.get("dropout", 0.2) if config else 0.2
        
        self.scaler = None
    
    def train(self, X: Any, y: Any, **kwargs) -> Dict:
        """
        Train LSTM model
        
        Args:
            X: Training sequences (3D array: samples x sequence_length x features)
            y: Training labels
            **kwargs: epochs, batch_size, validation_data
            
        Returns:
            Training metrics
        """
        logger.info(f"Training {self.model_name} with {len(X)} samples")
        
        start_time = datetime.now()
        
        # Try to use PyTorch/TensorFlow, otherwise use mock
        try:
            import torch
            import torch.nn as nn
            
            self.model = self._build_pytorch_model(X.shape[-1])
            history = self._train_pytorch(X, y, **kwargs)
            
        except ImportError:
            logger.warning("PyTorch not available, using mock LSTM model")
            self.model = MockLSTMModel()
            history = {"mock": True}
        
        self.is_trained = True
        
        metrics = {
            "model": self.model_name,
            "n_samples": len(X),
            "sequence_length": self.sequence_length,
            "training_time_seconds": (datetime.now() - start_time).total_seconds(),
            "history": history
        }
        
        self.training_history.append(metrics)
        
        logger.info(f"LSTM training complete")
        
        return metrics
    
    def _build_pytorch_model(self, input_size: int):
        """Build PyTorch LSTM model"""
        import torch.nn as nn
        
        class LSTMModel(nn.Module):
            def __init__(self, input_size, hidden_size, num_layers, dropout):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size, 
                    hidden_size, 
                    num_layers, 
                    dropout=dropout,
                    batch_first=True
                )
                self.fc = nn.Linear(hidden_size, 1)
            
            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                predictions = self.fc(lstm_out[:, -1, :])
                return predictions
        
        return LSTMModel(input_size, self.hidden_size, self.num_layers, self.dropout)
    
    def _train_pytorch(self, X, y, **kwargs):
        """Train using PyTorch"""
        import torch
        import torch.nn as nn
        
        epochs = kwargs.get("epochs", 50)
        batch_size = kwargs.get("batch_size", 32)
        learning_rate = kwargs.get("learning_rate", 0.001)
        
        # Convert to tensors
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.FloatTensor(y).reshape(-1, 1)
        
        # Optimizer and loss
        optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()
        
        # Training loop
        losses = []
        for epoch in range(epochs):
            self.model.train()
            optimizer.zero_grad()
            
            outputs = self.model(X_tensor)
            loss = criterion(outputs, y_tensor)
            
            loss.backward()
            optimizer.step()
            
            losses.append(loss.item())
        
        return {"losses": losses, "final_loss": losses[-1] if losses else 0}
    
    def predict(self, X: Any, **kwargs) -> Any:
        """
        Make predictions
        
        Args:
            X: Input sequences
            **kwargs: Additional parameters
            
        Returns:
            Predictions
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        try:
            import torch
            
            self.model.eval()
            with torch.no_grad():
                X_tensor = torch.FloatTensor(X)
                predictions = self.model(X_tensor)
                return predictions.numpy().flatten()
        except:
            # Mock predictions
            return np.random.randn(len(X)) * 1000 + 50000
    
    def prepare_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for LSTM training
        
        Args:
            data: 1D or 2D array of time series data
            
        Returns:
            Tuple of (X_sequences, y_targets)
        """
        if len(data.shape) == 1:
            data = data.reshape(-1, 1)
        
        X, y = [], []
        for i in range(len(data) - self.sequence_length):
            X.append(data[i:i + self.sequence_length])
            y.append(data[i + self.sequence_length, 0])  # Predict first feature
        
        return np.array(X), np.array(y)


class MockLSTMModel:
    """Mock LSTM model for testing"""
    
    def predict(self, X):
        """Mock prediction"""
        n = len(X) if hasattr(X, '__len__') else 1
        return np.random.randn(n) * 1000 + 50000
    
    def eval(self):
        """Mock eval mode"""
        pass
