#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
시그널의 매수/매도 탭 선택/해제 화면을 표시하는 위젯입니다.

[Responsibilities]
- signal_select.ui 로드
- 테이블 컬럼 너비 기본 설정

[UI Binding]
- signal_select.ui (src/10_trade/ui/signals/signal_select.ui)
"""
from __future__ import annotations

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except Exception:
    class QWidget:  # type: ignore[no-redef]
        """Minimal QWidget stub for non-GUI environments."""
        def __init__(self, parent=None):
            pass

    class uic:  # type: ignore[no-redef]
        @staticmethod
        def loadUi(path, widget):
            pass


class SignalselectWidget(QWidget):
    """시그널 선택 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "signal_select.ui")
        if os.path.exists(ui_path):
            uic.loadUi(ui_path, self)
