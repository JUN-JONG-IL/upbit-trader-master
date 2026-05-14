"""Backward-compatibility shim. Use src.trade.ui.signals.widget_signal_select instead."""
from ...ui.signals.widget_signal_select import SignalselectWidget  # noqa: F401

__all__ = ['SignalselectWidget']
