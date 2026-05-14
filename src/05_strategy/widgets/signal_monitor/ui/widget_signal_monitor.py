# -*- coding: utf-8 -*-
"""
실시간 시그널 모니터링 위젯 컨트롤러

UI File: signal_monitor.ui
Features:
- 실시간 시그널 목록 표시
- 시그널 필터링 (코인, 방향)
- 시그널 히스토리 조회
"""
from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except ImportError:
    QWidget = object
    uic = None


class SignalMonitorWidget(QWidget):
    """실시간 시그널 모니터링 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_ui()
        self._init_connections()

    def _load_ui(self) -> None:
        """UI 파일 로드"""
        if uic is None:
            return
        ui_path = Path(__file__).parent / "signal_monitor.ui"
        if ui_path.exists():
            uic.loadUi(str(ui_path), self)

    def _init_connections(self) -> None:
        """시그널/슬롯 연결"""
        try:
            self.btnClear.clicked.connect(self.on_clear)
            self.btnRefresh.clicked.connect(self.on_refresh)
        except AttributeError:
            pass

    def on_clear(self) -> None:
        """시그널 목록 초기화"""
        pass

    def on_refresh(self) -> None:
        """시그널 목록 갱신"""
        pass

    def add_signal(self, signal: dict) -> None:
        """새 시그널 추가"""
        pass
