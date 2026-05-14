#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prediction Models UI - Complete Prediction Interface

?덉륫 紐⑤뜽 愿由щ? ?꾪븳 ?꾩쟾???ъ슜???명꽣?섏씠??
- ?ㅼ뼇??紐⑤뜽 ?좏깮 (LSTM, Transformer, XGBoost, Direction, Anomaly, Meta)
- ?ㅼ떆媛?怨쇨굅 ?곗씠???뚯뒪 ?좏깮
- ?덉륫 湲곌컙 ?ㅼ젙
- ?좊ː???꾧퀎媛?議곗젙
- ?덉륫 寃곌낵 ?쒓컖??
- 諛깊뀒?ㅽ듃 ?깅뒫 硫뷀듃由?
- Feature Importance 遺꾩꽍
- ?ㅼ떆媛?李⑦듃 ?낅뜲?댄듃
- 寃곌낵 ?대낫?닿린
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

try:
    from PyQt5.QtWidgets import QWidget, QDialog, QVBoxLayout, QLabel, QPushButton
except Exception as _e:
    from utils.qt_stub import QtCore, QtGui, QtWidgets
