# -*- coding: utf-8 -*-
"""
백테스트 실행 위젯 컨트롤러

UI File: backtest_runner.ui
Features:
- 백테스트 파라미터 설정
- 백테스트 실행 및 진행 상태 표시
- 결과 요약 표시
"""
from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except ImportError:
    QWidget = object
    uic = None


class BacktestRunnerWidget(QWidget):
    """백테스트 실행 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_ui()
        self._init_connections()

    def _load_ui(self) -> None:
        """UI 파일 로드"""
        if uic is None:
            return
        ui_path = Path(__file__).parent / "backtest_runner.ui"
        if ui_path.exists():
            uic.loadUi(str(ui_path), self)

    def _init_connections(self) -> None:
        """시그널/슬롯 연결"""
        try:
            self.btnRun.clicked.connect(self.on_run_backtest)
            self.btnStop.clicked.connect(self.on_stop_backtest)
        except AttributeError:
            pass

    def on_run_backtest(self) -> None:
        """백테스트 실행"""
        pass

    def on_stop_backtest(self) -> None:
        """백테스트 중지"""
        pass
