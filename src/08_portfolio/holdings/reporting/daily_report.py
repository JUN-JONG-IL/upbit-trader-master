"""Daily portfolio report generator."""
from __future__ import annotations


class DailyReport:
    def generate(self, date: str, portfolio: dict) -> str:
        raise NotImplementedError
