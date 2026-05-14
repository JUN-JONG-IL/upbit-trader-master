"""차익거래 전략"""
from typing import Dict


class ArbitrageStrategy:
    """차익거래 전략 - 거래소 간 가격 차이 활용"""

    def __init__(self, min_spread: float = 0.005):
        self.min_spread = min_spread

    async def execute(self, market_data: Dict) -> Dict:
        """차익거래 기회 탐지 및 실행"""
        bid_price = market_data.get('bid_price', 0)
        ask_price = market_data.get('ask_price', 0)

        if ask_price <= 0:
            return {'action': 'hold'}

        spread = (bid_price - ask_price) / ask_price

        if spread >= self.min_spread:
            return {'action': 'arbitrage', 'spread': spread}

        return {'action': 'hold'}
