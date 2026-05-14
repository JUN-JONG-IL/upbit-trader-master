"""Markowitz mean-variance portfolio optimizer."""
from __future__ import annotations


class MarkowitzOptimizer:
    def optimize(self, returns: list[list[float]]) -> list[float]:
        raise NotImplementedError
