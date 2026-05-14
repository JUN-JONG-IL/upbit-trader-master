"""Mean Reversion Strategy"""
from typing import Dict
import numpy as np

class MeanReversionStrategy:
    def __init__(self, period: int = 20, threshold: float = 2.0):
        self.period = period
        self.threshold = threshold
    
    async def execute(self, market_data: Dict) -> Dict:
        """평균 회귀 전략 실행"""
        prices = market_data.get('prices', [])
        
        if len(prices) < self.period:
            return {'action': 'hold'}
        
        mean = np.mean(prices[-self.period:])
        std = np.std(prices[-self.period:])
        current = prices[-1]
        
        z_score = (current - mean) / std if std > 0 else 0
        
        if z_score < -self.threshold:
            return {'action': 'buy'}
        elif z_score > self.threshold:
            return {'action': 'sell'}
        
        return {'action': 'hold'}
