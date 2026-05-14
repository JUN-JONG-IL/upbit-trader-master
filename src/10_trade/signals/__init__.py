"""Backward-compatibility shim. Import from src.10_trade.ui.signals instead."""
from ..ui.signals.widget_signal_list import SignallistWidget  # noqa: F401
from ..ui.signals.widget_signal_select import SignalselectWidget  # noqa: F401

__all__ = ['SignallistWidget', 'SignalselectWidget']