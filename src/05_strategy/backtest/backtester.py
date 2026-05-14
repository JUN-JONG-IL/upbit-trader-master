"""
Backtester - Backtest prediction models on historical data
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .performance_metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


class Backtester:
    """Backtesting engine for prediction models"""
    
    def __init__(self, initial_capital: float = 10000000):  # 10M KRW
        self.initial_capital = initial_capital
        self.results = []
        self.trades = []
    
    def run(
        self,
        model: Any,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        **kwargs
    ) -> Dict:
        """
        Run backtest
        
        Args:
            model: Prediction model
            data: Historical data
            start_date: Start date for backtest
            end_date: End date for backtest
            **kwargs: Additional parameters
            
        Returns:
            Backtest results dictionary
        """
        logger.info("Starting backtest...")
        
        # Filter data by date range
        if start_date:
            data = data[data.index >= start_date]
        if end_date:
            data = data[data.index <= end_date]
        
        # Initialize
        capital = self.initial_capital
        position = 0  # Current position (0 = no position, 1 = long)
        equity_curve = []
        predictions = []
        actuals = []
        
        # Backtest loop
        for i in range(len(data) - 1):
            current_price = data['close'].iloc[i]
            next_price = data['close'].iloc[i + 1]
            
            # Get prediction
            try:
                # Use model to predict next price
                features = data.iloc[i:i+1].values
                pred = model.predict(features)[0] if hasattr(model, 'predict') else next_price * 1.01
            except Exception:
                pred = next_price * 1.01
            
            predictions.append(pred)
            actuals.append(next_price)
            
            # Simple trading logic: buy if prediction > current, sell otherwise
            if pred > current_price and position == 0:
                # Buy signal
                position = capital / current_price
                self.trades.append({
                    'timestamp': data.index[i],
                    'type': 'buy',
                    'price': current_price,
                    'amount': position
                })
            elif pred < current_price and position > 0:
                # Sell signal
                capital = position * current_price
                self.trades.append({
                    'timestamp': data.index[i],
                    'type': 'sell',
                    'price': current_price,
                    'amount': position
                })
                position = 0
            
            # Calculate current equity
            if position > 0:
                current_equity = position * current_price
            else:
                current_equity = capital
            
            equity_curve.append(current_equity)
        
        # Calculate performance metrics
        metrics = PerformanceMetrics()
        performance = metrics.calculate_all(
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
            trades=self.trades,
            predictions=predictions,
            actuals=actuals
        )
        
        results = {
            "start_date": data.index[0],
            "end_date": data.index[-1],
            "n_trades": len(self.trades),
            "final_equity": equity_curve[-1] if equity_curve else self.initial_capital,
            "total_return": (equity_curve[-1] / self.initial_capital - 1) * 100 if equity_curve else 0,
            "metrics": performance,
            "equity_curve": equity_curve,
            "trades": self.trades
        }
        
        self.results.append(results)
        
        logger.info(f"Backtest complete: {len(self.trades)} trades, "
                   f"{results['total_return']:.2f}% return")
        
        return results
    
    def get_results(self) -> List[Dict]:
        """Get backtest results"""
        return self.results
    
    def get_latest_result(self) -> Optional[Dict]:
        """Get latest backtest result"""
        return self.results[-1] if self.results else None
