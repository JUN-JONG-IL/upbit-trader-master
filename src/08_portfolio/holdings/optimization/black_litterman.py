"""Black-Litterman portfolio optimization model."""
from __future__ import annotations


class BlackLittermanOptimizer:
    def optimize(self, market_weights: list[float], views: dict) -> list[float]:
        raise NotImplementedError
