"""Backward-compatibility shim. Use src.trade.trade.ui.widget_trade instead."""
from ...trade.ui.widget_trade import TradeWidget  # noqa: F401

__all__ = ['TradeWidget']
