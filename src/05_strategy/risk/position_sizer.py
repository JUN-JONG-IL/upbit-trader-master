"""
[Purpose]
- 포지션 크기 계산 (Kelly Criterion, Fixed Fractional 등)
"""


class PositionSizer:
    """포지션 크기 계산기"""

    def fixed_fractional(
        self,
        capital: float,
        risk_percent: float,
        stop_loss_distance: float,
        price: float
    ) -> float:
        """
        Fixed Fractional 방식 포지션 크기 계산

        Args:
            capital: 가용 자본
            risk_percent: 리스크 비율 (예: 0.02 = 2%)
            stop_loss_distance: 손절 거리 (가격 차이)
            price: 현재 가격

        Returns:
            매수할 수량
        """
        if stop_loss_distance <= 0 or price <= 0:
            return 0.0
        risk_amount = capital * risk_percent
        quantity = risk_amount / stop_loss_distance
        return min(quantity, capital / price)

    def kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        capital: float
    ) -> float:
        """
        Kelly Criterion 포지션 크기 계산

        Args:
            win_rate: 승률 (0~1)
            avg_win: 평균 수익률
            avg_loss: 평균 손실률 (양수)
            capital: 가용 자본

        Returns:
            투자할 금액
        """
        if avg_loss <= 0:
            return 0.0
        b = avg_win / avg_loss
        kelly_pct = win_rate - (1 - win_rate) / b
        kelly_pct = max(0.0, min(kelly_pct, 0.25))  # 최대 25% 제한
        return capital * kelly_pct
