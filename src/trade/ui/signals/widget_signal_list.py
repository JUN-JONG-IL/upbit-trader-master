#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
전략/SignalManager가 생성한 시그널 리스트를 DB에서 읽어 테이블로 표시합니다.

[Responsibilities]
- signal_list.ui 로드 및 테이블 컬럼/폰트 크기 설정
- SignalListWorker(QThread)로 DB 조회 후 DataFrame을 UI로 전달
- 전달된 데이터로 테이블 아이템을 갱신하면 자동으로 리렌더

[UI Binding]
- signal_list.ui (src/trade/ui/signals/signal_list.ui)
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


class SignallistWidget(QWidget):
    """시그널 리스트 표시 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "signal_list.ui")
        if os.path.exists(ui_path):
            uic.loadUi(ui_path, self)
