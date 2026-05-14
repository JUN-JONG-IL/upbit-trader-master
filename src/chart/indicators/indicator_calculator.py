# -*- coding: utf-8 -*-
"""
Indicator Calculator - 100+ Technical Indicators
Uses pandas-ta for comprehensive indicator calculations
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
try:
    from PyQt5.QtCore import QObject, pyqtSignal
except Exception as _e:
    from utils.qt_stub import QtCore as QtCore
    # NOTE: if specific names were imported, they may be accessed via QtCore
