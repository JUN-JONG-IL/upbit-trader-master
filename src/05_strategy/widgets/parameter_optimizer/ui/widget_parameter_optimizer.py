# -*- coding: utf-8 -*-
"""
파라미터 최적화 위젯 컨트롤러

UI File: parameter_optimizer.ui
Features:
- 최적화 파라미터 범위 설정
- 유전 알고리즘 / Grid Search 선택
- 최적화 결과 표시
"""
from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except ImportError:
    QWidget = object
    uic = None


class ParameterOptimizerWidget(QWidget):
    """파라미터 최적화 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_ui()
        self._init_connections()

    def _load_ui(self) -> None:
        """UI 파일 로드"""
        if uic is None:
            return
        ui_path = Path(__file__).parent / "parameter_optimizer.ui"
        if ui_path.exists():
            uic.loadUi(str(ui_path), self)

    def _init_connections(self) -> None:
        """시그널/슬롯 연결"""
        try:
            self.btnOptimize.clicked.connect(self.on_optimize)
        except AttributeError:
            pass

    def on_optimize(self) -> None:
        """최적화 실행"""
        pass
