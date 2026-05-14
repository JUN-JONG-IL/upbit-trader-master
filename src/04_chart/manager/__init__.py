"""
Chart Manager Package - Modular chart management components

This package contains specialized managers for different aspects of chart functionality.
Each manager handles a specific responsibility, keeping the main ChartWidget clean.

Managers:
- UIManager: UI initialization and widget binding
- PeriodManager: Period menu, chips, and slider management
- EngineManager: Chart engine switching and button styling
- DataManager: Data fetching, processing, and rendering
- EventManager: Event handler aggregation (optional)

Version: v1.0
Created: 2026-02-10 | Copilot
"""

from .ui_manager import UIManager
from .period_manager import PeriodManager
from .engine_manager import EngineManager
from .data_manager import DataManager

__all__ = [
    'UIManager',
    'PeriodManager',
    'EngineManager',
    'DataManager',
]