# -*- coding: utf-8 -*-
"""
Drawing Manager - Manage all drawing tools with mouse interactions
Implements 17 drawing tools with save/load functionality
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
try:
    from PyQt5.QtCore import QObject, pyqtSignal, Qt, QPointF
except Exception as _e:
    from utils.qt_stub import QtCore as QtCore
    # NOTE: if specific names were imported, they may be accessed via QtCore
