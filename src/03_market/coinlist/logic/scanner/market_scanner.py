"""Market scanner for detecting trading opportunities."""
from __future__ import annotations


class MarketScanner:
    """Scans market data for configured signals."""

    def scan(self) -> list[dict]:
        raise NotImplementedError
