"""
[Purpose]
- 손절매 관리 (고정 손절, 트레일링 스탑 등)
"""


class StopLoss:
    """손절매 관리"""

    def __init__(self, stop_pct: float = 0.02):
        """
        Args:
            stop_pct: 손절 비율 (예: 0.02 = 2%)
        """
        self.stop_pct = stop_pct

    def fixed(self, entry_price: float) -> float:
        """고정 손절가 계산"""
        return entry_price * (1 - self.stop_pct)

    def trailing(self, highest_price: float) -> float:
        """트레일링 스탑 계산"""
        return highest_price * (1 - self.stop_pct)

    def is_triggered(self, current_price: float, stop_price: float) -> bool:
        """손절 발동 여부 확인"""
        return current_price <= stop_price
