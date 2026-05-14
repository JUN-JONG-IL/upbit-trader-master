"""
portfolio/ui package: Portfolio UI widgets.

Exports:
- PortfolioWidget (main portfolio widget)
- DetailholdinglistWidget (보유자산 세부 목록 위젯)
- HoldingListWidget (보유자산 목록 위젯)
"""

import logging

try:
    from .widget_portfolio import PortfolioWidget
except Exception as e:
    logging.exception("Failed to import PortfolioWidget: %s", e)

    class PortfolioWidget:  # type: ignore[no-redef]
        """Placeholder PortfolioWidget (PyQt not available)."""

        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PortfolioWidget (no GUI).")

try:
    from .widget_detail_holding import DetailholdinglistWidget
except Exception as e:
    logging.warning("DetailholdinglistWidget import failed: %s", e)
    DetailholdinglistWidget = None  # type: ignore[assignment,misc]

try:
    from .widget_holding_list import HoldingListWidget
except Exception as e:
    logging.warning("HoldingListWidget import failed: %s", e)
    HoldingListWidget = None  # type: ignore[assignment,misc]

__all__ = ["PortfolioWidget", "DetailholdinglistWidget", "HoldingListWidget"]
