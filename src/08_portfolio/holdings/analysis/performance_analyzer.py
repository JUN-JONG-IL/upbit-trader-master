"""Portfolio performance analyzer."""
from __future__ import annotations


class PerformanceAnalyzer:
    def analyze(self, returns: list[float]) -> dict:
        raise NotImplementedError
