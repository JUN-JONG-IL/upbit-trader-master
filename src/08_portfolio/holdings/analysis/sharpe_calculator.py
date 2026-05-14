"""Sharpe ratio calculator."""
from __future__ import annotations


class SharpeCalculator:
    def calculate(self, returns: list[float], risk_free_rate: float = 0.0) -> float:
        raise NotImplementedError
