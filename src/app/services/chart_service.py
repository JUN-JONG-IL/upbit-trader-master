# -*- coding: utf-8 -*-
"""
chart 모듈 인터페이스
차트 위젯 및 데이터 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

_chart_dir = str(Path(__file__).parents[3] / "chart")
if _chart_dir not in sys.path:
    sys.path.insert(0, _chart_dir)


class ChartService:
    """chart 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._chart_widget: Optional[Any] = None
        self._advanced_chart_widget: Optional[Any] = None

    def get_chart_widget(self) -> Any:
        if self._chart_widget is None:
            try:
                from chart.ui.widget_chart import ChartWidget  # type: ignore
                self._chart_widget = ChartWidget
            except ImportError:
                pass
        return self._chart_widget

    def get_advanced_chart_widget(self) -> Any:
        if self._advanced_chart_widget is None:
            try:
                from chart.ui.advanced_chart_dialog import AdvancedChartDialog  # type: ignore
                self._advanced_chart_widget = AdvancedChartDialog
            except ImportError:
                pass
        return self._advanced_chart_widget
