"""
portfolio package: Portfolio management and user information widgets.

Exports:
- PortfolioWidget (from holdings)
- UserinfoWidget (from userinfo)
"""

import logging

try:
    from .holdings import PortfolioWidget
except Exception as e:
    logging.exception("Failed to import PortfolioWidget: %s", e)

    class PortfolioWidget:  # type: ignore[no-redef]
        """Placeholder PortfolioWidget (PyQt not available)."""

        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PortfolioWidget (no GUI).")

try:
    from .userinfo import UserinfoWidget
except Exception as e:
    logging.exception("Failed to import UserinfoWidget: %s", e)

    class UserinfoWidget:  # type: ignore[no-redef]
        """Placeholder UserinfoWidget (PyQt not available)."""

        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder UserinfoWidget (no GUI).")

__all__ = ["PortfolioWidget", "UserinfoWidget"]
