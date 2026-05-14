"""DCA (Dollar Cost Averaging) Strategy"""
from typing import Dict

class DCAStrategy:
    def __init__(self, interval: int = 3600, amount: float = 10000):
        self.interval = interval
        self.amount = amount
        self.last_buy = 0
    
    async def execute(self, market_data: Dict) -> Dict:
        """DCA 전략 실행"""
        current_time = market_data['timestamp']
        
        if current_time - self.last_buy >= self.interval:
            self.last_buy = current_time
            return {
                'action': 'buy',
                'amount': self.amount,
                'price': market_data['close']
            }
        
        return {'action': 'hold'}
