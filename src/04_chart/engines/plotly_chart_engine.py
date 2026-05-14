"""Plotly Chart Engine — QWidget wrapper using QWebEngineView"""
from __future__ import annotations

import logging
from typing import Dict, List, Any

import pandas as pd

try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_AVAILABLE = True
except Exception:
    _WEBENGINE_AVAILABLE = False

try:
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except Exception:
    _PLOTLY_AVAILABLE = False

log = logging.getLogger(__name__)


class PlotlyChartEngine(QWidget if _QT_AVAILABLE else object):
    """Plotly interactive chart engine embedded in a QWebEngineView."""

    def __init__(self, parent=None):
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            super().__init__()

        self.indicators: List[str] = []
        self._data: List[Dict[str, Any]] = []
        self._web_view = None

        if _QT_AVAILABLE and _WEBENGINE_AVAILABLE:
            self._web_view = QWebEngineView(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._web_view)
            # Show empty chart on startup
            self._show_empty()
        elif _QT_AVAILABLE:
            from PyQt5.QtWidgets import QLabel
            from PyQt5.QtCore import Qt
            lbl = QLabel("Plotly Charts\n(QWebEngineView 필요)", self)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#9ca3af; font-size:14px; background:#1a1a2e;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(lbl)

    # ------------------------------------------------------------------
    def update_data(self, data: List[Dict[str, Any]]) -> None:
        """Receive list-of-dicts candle data and re-render via Plotly HTML."""
        if not data:
            return
        self._data = data
        try:
            df = self._to_dataframe(data)
            if df.empty:
                return
            self.render(df)
        except Exception as e:
            log.error(f"[PlotlyChartEngine] update_data error: {e}")

    def render(self, data: pd.DataFrame, **kwargs) -> None:
        """Render DataFrame as Plotly candlestick chart."""
        if not _PLOTLY_AVAILABLE or self._web_view is None:
            return
        try:
            df = self._normalize_columns(data)
            fig = go.Figure(data=[
                go.Candlestick(
                    x=list(range(len(df))),
                    open=df["Open"].tolist(),
                    high=df["High"].tolist(),
                    low=df["Low"].tolist(),
                    close=df["Close"].tolist(),
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                )
            ])
            fig.update_layout(
                paper_bgcolor="#1a1a2e",
                plot_bgcolor="#1a1a2e",
                font_color="#d1d5db",
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(showgrid=True, gridcolor="#2d3748"),
                yaxis=dict(showgrid=True, gridcolor="#2d3748"),
                xaxis_rangeslider_visible=False,
            )
            html = fig.to_html(
                full_html=True,
                include_plotlyjs="cdn",
                config={"responsive": True},
            )
            self._web_view.setHtml(html)
        except Exception as e:
            log.error(f"[PlotlyChartEngine] render error: {e}")

    def add_indicator(self, name: str, params: Dict) -> None:
        self.indicators.append(name)

    def clear(self) -> None:
        self.indicators.clear()
        self._show_empty()

    def _show_empty(self) -> None:
        """Show an empty chart placeholder."""
        if self._web_view is None:
            return
        html = (
            "<html><body style='margin:0;background:#1a1a2e;display:flex;"
            "align-items:center;justify-content:center;height:100vh;'>"
            "<span style='color:#4b5563;font-family:sans-serif;font-size:14px;'>"
            "데이터 로딩 중...</span></body></html>"
        )
        self._web_view.setHtml(html)

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_columns(data: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to Title Case (Open/High/Low/Close/Volume)."""
        col_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
            "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume",
        }
        renamed = {c: col_map[c.lower()] for c in data.columns if c.lower() in col_map}
        return data.rename(columns=renamed)

    @staticmethod
    def _to_dataframe(data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert list-of-dicts candle data to a DataFrame."""
        rows = []
        for c in data:
            rows.append({
                "Open": float(c.get("o", 0) or 0),
                "High": float(c.get("h", 0) or 0),
                "Low": float(c.get("l", 0) or 0),
                "Close": float(c.get("c", 0) or 0),
                "Volume": float(c.get("v", 0) or 0),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df[df["Close"] > 0]

