"""Reinforcement learning-based portfolio optimizer."""
from __future__ import annotations


class RLOptimizer:
    def optimize(self, state: dict) -> list[float]:
        raise NotImplementedError
