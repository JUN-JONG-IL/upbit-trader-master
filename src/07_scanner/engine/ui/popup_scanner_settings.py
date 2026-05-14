# -*- coding: utf-8 -*-
"""
[Purpose]
- "스캐너 설정창" 다이얼로그를 제공한다.

[Responsibilities]
- popup_scanner_settings.ui 로드 및 UI 초기화(기간/코인 목록)
- 사용자가 선택한 설정 값을 dict로 반환(get_settings)
- 저장 버튼 클릭 시 accept()로 종료

[Main Flow]
- ScannerFrameWidget.open_settings()에서 ScannerSettingsPopup 실행(exec_)
- 사용자가 설정 후 저장 버튼 클릭 → accept()
- ScannerFrameWidget에서 popup.get_settings()로 설정 dict 수신

[Dependencies]
- PyQt5(QDialog, uic)
- server.static.chart.coins: 코인 목록 채우기
- (리소스) 같은 폴더의 popup_scanner_settings.ui

[UI Binding]
- popup_scanner_settings.ui
"""
from __future__ import annotations

import os
from typing import Any, Dict

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic
except Exception:
    from utils.qt_stub import QtWidgets
    QDialog = QtWidgets.QDialog
    uic = None

try:
    import server.static as static
    HAS_STATIC = True
except ImportError:
    HAS_STATIC = False


def _ui_file_path(filename: str) -> str:
    """ui/ 폴더(현재 파일과 같은 디렉토리)의 파일 경로를 반환한다."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


class ScannerSettingsPopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        if uic is not None:
            uic.loadUi(_ui_file_path("popup_scanner_settings.ui"), self)

            self.saveButton.clicked.connect(self.accept)

            # 콤보박스 초기화 (예: 기간 목록)
            periods = [
                "틱1",
                "틱3",
                "틱5",
                "틱10",
                "틱30",
                "틱60",
                "초",
                "1분",
                "3분",
                "5분",
                "10분",
                "15분",
                "30분",
                "60분",
                "240분",
                "일",
                "주",
                "월",
                "년",
            ]
            self.intervalCombo.clear()
            self.intervalCombo.addItems(periods)

            # 코인 목록 (static.chart에서 가져옴)
            coins: list = []
            if HAS_STATIC and hasattr(static, "chart") and hasattr(static.chart, "coins"):
                coins = [coin.code for coin in static.chart.coins.values()]
            self.coinCombo.clear()
            self.coinCombo.addItems(coins)

    def get_settings(self) -> Dict[str, Any]:
        # NOTE: 현재는 UI 항목이 일부만 연결되어 있어, 나머지는 기본값을 반환한다.
        # 이후 이미지 기반 옵션(골든/데드, 이동평균 조건, RSI 등)을 UI와 1:1로 매핑하는 단계가 필요.
        if uic is None:
            return {}
        return {
            "coin": self.coinCombo.currentText(),
            "interval": self.intervalCombo.currentText(),
            "ma_direction": self.maDirectionCombo.currentText(),
            "rsi_period": 14,
            "rsi_value": 30,
            "ma_short": 5,
            "ma_long": 20,
            "auto_interval": 60,  # 초
        }
