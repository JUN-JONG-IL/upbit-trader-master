"""
coinlist package entrypoint.

Exports:
- CoinlistWidget (preferred)
"""

from .ui.widget_coin_list import CoinlistWidget  # type: ignore

__all__ = ["CoinlistWidget"]