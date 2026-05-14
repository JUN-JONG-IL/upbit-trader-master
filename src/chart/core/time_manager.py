"""
Time Manager - Synchronize time/zoom/scroll across multiple charts

This module provides centralized time synchronization for multi-chart layouts.
It manages the global timeline and broadcasts time changes to all subscribed charts.

Version: v1.0
Last Modified: 2026-02-08 | Copilot
"""

import logging
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
try:
    from PyQt5.QtCore import QObject, pyqtSignal, Qt
except Exception as _e:
    from utils.qt_stub import QtCore as QtCore
    # NOTE: if specific names were imported, they may be accessed via QtCore
