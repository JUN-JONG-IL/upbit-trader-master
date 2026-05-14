"""
Performance Metrics - Calculate trading performance metrics
"""

import logging
import numpy as np
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Calculates various trading performance metrics"""
    
    def __init__(self):
        pass
    
    def calculate_all(
        self,
        equity_curve: List[float],
        initial_capital: float,
        trades: List[Dict],
        predictions: Optional[List[float]] = None,
        actuals: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """
        Calculate all performance metrics
        
        Args:
            equity_curve: List of equity values over time
            initial_capital: Initial capital
            trades: List of trade dictionaries
            predictions: Optional predictions
            actuals: Optional actual values
            
        Returns:
            Dictionary of metrics
        """
        metrics = {}
        
        # Prediction metrics
        if predictions and actuals:
            metrics.update(self.calculate_prediction_metrics(predictions, actuals))
        
        # Trading metrics
        if equity_curve:
            metrics.update(self.calculate_trading_metrics(equity_curve, initial_capital))
        
        # Trade statistics
        if trades:
            metrics.update(self.calculate_trade_stats(trades))
        
        return metrics
    
    def calculate_prediction_metrics(
        self,
        predictions: List[float],
        actuals: List[float]
    ) -> Dict[str, float]:
        """
        Calculate prediction accuracy metrics
        
        Args:
            predictions: Predicted values
            actuals: Actual values
            
        Returns:
            Dictionary of prediction metrics
        """
        pred_array = np.array(predictions)
        actual_array = np.array(actuals)
        
        # MAE - Mean Absolute Error
        mae = np.mean(np.abs(pred_array - actual_array))
        
        # RMSE - Root Mean Squared Error
        rmse = np.sqrt(np.mean((pred_array - actual_array) ** 2))
        
        # MAPE - Mean Absolute Percentage Error
        mape = np.mean(np.abs((actual_array - pred_array) / actual_array)) * 100
        
        # Direction Accuracy
        pred_direction = np.sign(np.diff(pred_array))
        actual_direction = np.sign(np.diff(actual_array))
        direction_accuracy = np.mean(pred_direction == actual_direction) * 100
        
        return {
            "MAE": float(mae),
            "RMSE": float(rmse),
            "MAPE": float(mape),
            "direction_accuracy": float(direction_accuracy)
        }
    
    def calculate_trading_metrics(
        self,
        equity_curve: List[float],
        initial_capital: float
    ) -> Dict[str, float]:
        """
        Calculate trading performance metrics
        
        Args:
            equity_curve: Equity values over time
            initial_capital: Initial capital
            
        Returns:
            Dictionary of trading metrics
        """
        equity = np.array(equity_curve)
        
        # Total Return
        total_return = (equity[-1] / initial_capital - 1) * 100
        
        # Calculate returns
        returns = np.diff(equity) / equity[:-1]
        
        # Sharpe Ratio (annualized, assuming daily data)
        if len(returns) > 0 and np.std(returns) > 0:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # Maximum Drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak * 100
        max_drawdown = np.min(drawdown)
        
        # Win Rate (based on daily returns)
        winning_days = np.sum(returns > 0)
        total_days = len(returns)
        win_rate = (winning_days / total_days * 100) if total_days > 0 else 0
        
        # Volatility (annualized)
        volatility = np.std(returns) * np.sqrt(252) * 100 if len(returns) > 0 else 0
        
        return {
            "total_return_pct": float(total_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown_pct": float(max_drawdown),
            "win_rate_pct": float(win_rate),
            "volatility_pct": float(volatility)
        }
    
    def calculate_trade_stats(self, trades: List[Dict]) -> Dict[str, float]:
        """
        Calculate trade statistics
        
        Args:
            trades: List of trades
            
        Returns:
            Dictionary of trade statistics
        """
        if not trades:
            return {
                "n_trades": 0,
                "avg_trade_duration": 0
            }
        
        # Count buys and sells
        buys = [t for t in trades if t['type'] == 'buy']
        sells = [t for t in trades if t['type'] == 'sell']
        
        return {
            "n_trades": len(trades),
            "n_buys": len(buys),
            "n_sells": len(sells)
        }
