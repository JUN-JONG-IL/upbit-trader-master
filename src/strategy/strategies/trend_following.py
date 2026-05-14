"""Trend Following Strategy"""
from typing import Dict

class TrendFollowingStrategy:
    def __init__(self, fast_ma: int = 12, slow_ma: int = 26):
        self.fast = fast_ma
        self.slow = slow_ma
    
    async def execute(self, market_data: Dict) -> Dict:
        """추세 추종 전략 실행"""
        prices = market_data.get('prices', [])
        
        if len(prices) < self.slow:
            return {'action': 'hold'}
        
        fast_ma = sum(prices[-self.fast:]) / self.fast
        slow_ma = sum(prices[-self.slow:]) / self.slow
        
        if fast_ma > slow_ma:
            return {'action': 'buy'}
        elif fast_ma < slow_ma:
            return {'action': 'sell'}
        
        return {'action': 'hold'}
