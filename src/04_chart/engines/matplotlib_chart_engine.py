"""Matplotlib Chart Engine — QWidget wrapper"""
from __future__ import annotations

import logging
from typing import Dict, List, Any

import pandas as pd

try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

log = logging.getLogger(__name__)


class MatplotlibChartEngine(QWidget if _QT_AVAILABLE else object):
    """Matplotlib-based chart engine embedded in a QWidget."""

    def __init__(self, parent=None):
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            super().__init__()

        self.indicators: List[str] = []
        self._data: List[Dict[str, Any]] = []

        if _QT_AVAILABLE:
            self.figure = plt.Figure(figsize=(12, 6), tight_layout=True)
            self.mpl_canvas = FigureCanvasQTAgg(self.figure)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.mpl_canvas)
        else:
            self.figure = None
            self.mpl_canvas = None

    # ------------------------------------------------------------------
    def update_data(self, data: List[Dict[str, Any]]) -> None:
        """Receive list-of-dicts candle data and re-render."""
        if not data:
            return
        self._data = data
        try:
            df = self._to_dataframe(data)
            self.render(df)
        except Exception as e:
            log.error(f"[MatplotlibChartEngine] update_data error: {e}")

    def render(self, data: pd.DataFrame, **kwargs) -> None:
        """Render data using Matplotlib."""
        if self.figure is None:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if "close" in data.columns:
            ax.plot(data.index, data["close"], label="Close", color="#3b82f6")
        for ind in self.indicators:
            if ind in data.columns:
                ax.plot(data.index, data[ind], label=ind)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_facecolor("#1a1a2e")
        self.figure.patch.set_facecolor("#1a1a2e")
        if self.mpl_canvas:
            self.mpl_canvas.draw()

    def add_indicator(self, name: str, params: Dict) -> None:
        self.indicators.append(name)

    def clear(self) -> None:
        self.indicators.clear()
        if self.figure:
            self.figure.clear()
            if self.mpl_canvas:
                self.mpl_canvas.draw()

    # ------------------------------------------------------------------
    @staticmethod
    def _to_dataframe(data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert list-of-dicts candle data to a DataFrame."""
        rows = []
        for i, c in enumerate(data):
            rows.append({
                "open": c.get("o", 0),
                "high": c.get("h", 0),
                "low": c.get("l", 0),
                "close": c.get("c", 0),
                "volume": c.get("v", 0),
            })
        return pd.DataFrame(rows)

