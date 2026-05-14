"""
[Purpose]
- 포트폴리오 관리 (보유 종목, 전체 수익률 등)
"""
from typing import Dict, List


class Portfolio:
    """포트폴리오 관리"""

    def __init__(self, initial_capital: float = 10_000_000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict] = {}

    def buy(self, code: str, price: float, quantity: float) -> bool:
        """매수 실행"""
        cost = price * quantity
        if cost > self.cash:
            return False
        self.cash -= cost
        if code in self.positions:
            existing = self.positions[code]
            total_qty = existing['quantity'] + quantity
            total_cost = existing['avg_price'] * existing['quantity'] + cost
            self.positions[code] = {
                'quantity': total_qty,
                'avg_price': total_cost / total_qty
            }
        else:
            self.positions[code] = {'quantity': quantity, 'avg_price': price}
        return True

    def sell(self, code: str, price: float, quantity: float = None) -> float:
        """매도 실행, 실현 손익 반환"""
        if code not in self.positions:
            return 0.0
        pos = self.positions[code]
        qty = quantity if quantity else pos['quantity']
        qty = min(qty, pos['quantity'])
        revenue = price * qty
        self.cash += revenue
        pnl = (price - pos['avg_price']) * qty
        pos['quantity'] -= qty
        if pos['quantity'] <= 0:
            del self.positions[code]
        return pnl

    @property
    def total_value(self) -> float:
        """현재 포트폴리오 총 가치 (포지션 평가 포함 안 됨, 현금만)"""
        return self.cash

    @property
    def total_return_pct(self) -> float:
        """총 수익률"""
        return (self.cash / self.initial_capital - 1) * 100
