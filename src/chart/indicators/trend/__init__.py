"""Trend indicators: moving averages, VWAP."""
from .ma import sma, ema, wma
from .vwap import vwap

__all__ = ["sma", "ema", "wma", "vwap"]
