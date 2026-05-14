# -*- coding: utf-8 -*-
"""
Advanced Chart Dialog - 고급 차트 도구 다이얼로그
advanced_chart_dialog.ui 파일을 로드하여 표시합니다.
"""
import os

try:
    from PyQt5.QtWidgets import QDialog, QVBoxLayout
    from PyQt5.QtCore import Qt
    from PyQt5.uic import loadUi
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

import logging
log = logging.getLogger(__name__)


def _ui_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class AdvancedChartDialog(QDialog if _QT_AVAILABLE else object):
    """
    고급 차트 도구 다이얼로그.

    advanced_chart_dialog.ui 파일을 로드하여 보여줍니다.
    """

    def __init__(self, parent=None, symbol: str = "KRW-BTC"):
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            super().__init__()

        self._symbol = symbol

        ui_file = _ui_path("advanced_chart_dialog.ui")
        if _QT_AVAILABLE and os.path.exists(ui_file):
            try:
                loadUi(ui_file, self)
                log.info(f"[AdvancedChartDialog] UI loaded from {ui_file}")
            except Exception as e:
                log.error(f"[AdvancedChartDialog] loadUi failed: {e}")
                self._build_fallback_ui()
        else:
            self._build_fallback_ui()

        # 비모달 설정 (메인과 동시 조작 가능)
        if _QT_AVAILABLE:
            self.setModal(False)
            self.setWindowFlags(self.windowFlags() | Qt.Window)

        self._connect_signals()

    # ------------------------------------------------------------------
    def _build_fallback_ui(self) -> None:
        """Minimal fallback UI when .ui file is not available."""
        if not _QT_AVAILABLE:
            return
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import Qt
        self.setWindowTitle("고급 차트 도구")
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        lbl = QLabel("고급 차트 도구", self)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

    def _connect_signals(self) -> None:
        """버튼 및 시그널 연결."""
        try:
            if hasattr(self, "comboSymbol") and self._symbol:
                idx = self.comboSymbol.findText(self._symbol)
                if idx >= 0:
                    self.comboSymbol.setCurrentIndex(idx)
        except Exception:
            pass

        # Close / Cancel 버튼 연결
        for btn_name in ("btnClose", "btn_close", "closeButton",
                         "buttonClose", "cancelButton", "btnCancel"):
            btn = getattr(self, btn_name, None)
            if btn is not None:
                try:
                    btn.clicked.connect(self.reject)
                except Exception:
                    pass
                break
