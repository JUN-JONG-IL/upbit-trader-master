"""
[Purpose]
- Order book calculation and aggregation logic

[Responsibilities]
- Calculate bid-ask spread
- Aggregate order quantities by price level
- Calculate total order book depth
"""
from __future__ import annotations

from typing import Dict, List


class OrderbookCalculator:
    """Calculates order book metrics."""

    @staticmethod
    def calculate_spread(bids: List[Dict], asks: List[Dict]) -> float:
        """Calculate bid-ask spread."""
        if not bids or not asks:
            return 0.0
        best_bid = max(bids, key=lambda x: x['price'])['price']
        best_ask = min(asks, key=lambda x: x['price'])['price']
        return best_ask - best_bid

    @staticmethod
    def aggregate_levels(orders: List[Dict], num_levels: int = 15) -> List[Dict]:
        """Aggregate order book to specified number of levels."""
        # TODO: Implement aggregation logic
        return orders[:num_levels]
