"""
[Purpose]
- Aggregate and process trade data for display

[Responsibilities]
- Filter duplicate trades
- Aggregate trades by time window
- Calculate trade statistics
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List


class TradeAggregator:
    """Aggregates trade data for efficient display."""

    def __init__(self, max_trades: int = 100):
        self.max_trades = max_trades
        self.trades: deque = deque(maxlen=max_trades)

    def add_trade(self, trade: Dict):
        """Add a new trade to the aggregator."""
        self.trades.append(trade)

    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent trades up to limit."""
        return list(self.trades)[-limit:]
