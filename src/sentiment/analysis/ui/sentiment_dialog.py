#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Dialog

NLP 및 감성 분석 UI 다이얼로그 모듈
"""

import logging
from pathlib import Path

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QDialog = object

logger = logging.getLogger(__name__)

_UI_FILE = Path(__file__).parent / "sentiment_dialog.ui"


class SentimentDialog(QDialog if _HAS_QT else object):
    """뉴스 및 소셜 감성 분석 다이얼로그"""

    def __init__(self, parent=None):
        if _HAS_QT:
            super().__init__(parent)
        else:
            super().__init__()

        if _HAS_QT and _UI_FILE.exists():
            try:
                uic.loadUi(str(_UI_FILE), self)
                logger.info("SentimentDialog UI loaded from %s", _UI_FILE)
            except Exception as e:
                logger.warning("Failed to load dialog UI: %s", e)
