"""Backward-compatibility shim. Use src.10_trade.ui.signals.widget_signal_list instead."""
from ...ui.signals.widget_signal_list import SignallistWidget  # noqa: F401

__all__ = ['SignallistWidget']
