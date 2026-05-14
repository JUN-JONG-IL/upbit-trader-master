"""Drawdown tracker for portfolio analysis."""
from __future__ import annotations


class DrawdownTracker:
    def max_drawdown(self, equity_curve: list[float]) -> float:
        raise NotImplementedError
