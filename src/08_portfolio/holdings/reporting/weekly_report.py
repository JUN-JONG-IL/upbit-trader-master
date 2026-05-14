"""Weekly portfolio report generator."""
from __future__ import annotations


class WeeklyReport:
    def generate(self, week: str, portfolio: dict) -> str:
        raise NotImplementedError
