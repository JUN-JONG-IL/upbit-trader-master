# -*- coding: utf-8 -*-
"""
전략 관리 위젯 컨트롤러

UI File: strategy_manager.ui
Features:
- 전략 목록 표시 및 선택
- 전략 추가/제거/수정
- 전략 파라미터 표시
"""
from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except ImportError:
    QWidget = object
    uic = None


class StrategyManagerWidget(QWidget):
    """전략 관리 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_ui()
        self._init_connections()

    def _load_ui(self) -> None:
        """UI 파일 로드"""
        if uic is None:
            return
        ui_path = Path(__file__).parent / "strategy_manager.ui"
        if ui_path.exists():
            uic.loadUi(str(ui_path), self)

    def _init_connections(self) -> None:
        """시그널/슬롯 연결"""
        try:
            self.btnAddStrategy.clicked.connect(self.on_add_strategy)
            self.btnRemoveStrategy.clicked.connect(self.on_remove_strategy)
            self.btnEditStrategy.clicked.connect(self.on_edit_strategy)
            self.listStrategies.itemClicked.connect(self.on_strategy_selected)
        except AttributeError:
            pass

    def on_add_strategy(self) -> None:
        """전략 추가"""
        pass

    def on_remove_strategy(self) -> None:
        """전략 제거"""
        pass

    def on_edit_strategy(self) -> None:
        """전략 수정"""
        pass

    def on_strategy_selected(self, item) -> None:
        """전략 선택 시 파라미터 표시"""
        pass
