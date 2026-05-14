"""
Portfolio Optimization Module

Exports:
- PortfolioWidget (main UI widget)
- PortfolioOptimizer (portfolio optimization engine)
"""

import logging

from .optimizer import PortfolioOptimizer

try:
    from .ui import PortfolioWidget
except Exception as e:
    logging.exception("Failed to import PortfolioWidget: %s", e)

    class PortfolioWidget:  # type: ignore[no-redef]
        """Placeholder PortfolioWidget (PyQt not available)."""

        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PortfolioWidget (no GUI).")

__all__ = ["PortfolioWidget", "PortfolioOptimizer"]

