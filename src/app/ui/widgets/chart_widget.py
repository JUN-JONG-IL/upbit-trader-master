# -*- coding: utf-8 -*-
"""
차트 위젯 - chart 모듈 연동
"""
from __future__ import annotations
import sys
from pathlib import Path

_chart_dir = str(Path(__file__).parents[4] / "chart")
if _chart_dir not in sys.path:
    sys.path.insert(0, _chart_dir)

try:
    from src._chart import ChartWidget  # type: ignore
except ImportError:
    try:
        from chart.ui.widget_chart import ChartWidget  # type: ignore
    except ImportError:
        ChartWidget = None  # type: ignore

if ChartWidget is None:
    # Standalone fallback: lightweight chart placeholder
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PyQt5.QtCore import Qt as _Qt

        class ChartWidget(QWidget):  # type: ignore[no-redef]
            """Fallback 차트 위젯 (플레이스홀더)."""

            def __init__(self, parent=None):
                super().__init__(parent)
                self._current_symbol: str = ""
                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                self._label = QLabel("차트 영역\n심볼을 선택하면 차트가 표시됩니다.", self)
                self._label.setAlignment(_Qt.AlignCenter)
                layout.addWidget(self._label)

            def update_symbol(self, source: str, symbol: str) -> None:
                self._current_symbol = symbol
                self._label.setText(f"차트: {symbol}\n(차트 엔진 로드 중...)")

            def update_data(self, data) -> None:
                pass

            def set_symbol(self, symbol: str) -> None:
                self.update_symbol("", symbol)

            def set_timeframe(self, timeframe: str) -> None:
                pass

    except Exception:
        ChartWidget = None  # type: ignore[assignment]

__all__ = ["ChartWidget"]
