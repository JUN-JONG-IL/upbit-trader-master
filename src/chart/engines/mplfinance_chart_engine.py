"""mplfinance Chart Engine — QWidget wrapper"""
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
    import mplfinance as mpf
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

log = logging.getLogger(__name__)


class MplfinanceChartEngine(QWidget if _QT_AVAILABLE else object):
    """mplfinance-based candlestick chart engine embedded in a QWidget."""

    def __init__(self, parent=None):
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            super().__init__()

        self.style = "charles"
        self.indicators: List[Dict] = []
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
            if df.empty:
                return
            self.render(df)
        except Exception as e:
            log.error(f"[MplfinanceChartEngine] update_data error: {e}")

    def render(self, data: pd.DataFrame, **kwargs) -> None:
        """Render OHLCV DataFrame using mplfinance."""
        if self.figure is None or data is None or data.empty:
            return
        self.figure.clear()
        try:
            mpf.plot(
                data,
                type="candle",
                style=self.style,
                volume=True,
                returnfig=False,
                ax=self.figure.add_subplot(211),
                volume_ax=self.figure.add_subplot(212),
                **{k: v for k, v in kwargs.items()
                   if k not in ("ax", "volume_ax")},
            )
        except Exception:
            # Fallback: simple close line
            ax = self.figure.add_subplot(111)
            if "Close" in data.columns:
                ax.plot(data.index, data["Close"], color="#3b82f6")
        if self.mpl_canvas:
            self.mpl_canvas.draw()

    def add_indicator(self, name: str, params: Dict) -> None:
        self.indicators.append({"name": name, "params": params})

    def clear(self) -> None:
        self.indicators.clear()
        if self.figure:
            self.figure.clear()
            if self.mpl_canvas:
                self.mpl_canvas.draw()

    # ------------------------------------------------------------------
    @staticmethod
    def _to_dataframe(data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert list-of-dicts candle data to a mplfinance-compatible DataFrame."""
        import datetime
        rows = []
        for i, c in enumerate(data):
            rows.append({
                "Open": float(c.get("o", 0) or 0),
                "High": float(c.get("h", 0) or 0),
                "Low": float(c.get("l", 0) or 0),
                "Close": float(c.get("c", 0) or 0),
                "Volume": float(c.get("v", 0) or 0),
            })
        if not rows:
            return pd.DataFrame()
        base = datetime.datetime(2024, 1, 1)
        index = [base + datetime.timedelta(minutes=i) for i in range(len(rows))]
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
        # mplfinance requires positive OHLCV values
        df = df[df["Close"] > 0]
        return df

