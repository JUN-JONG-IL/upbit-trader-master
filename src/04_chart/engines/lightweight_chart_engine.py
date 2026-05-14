"""Lightweight Charts Engine — QWidget wrapper using QWebEngineView"""
from __future__ import annotations

import json
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
    from PyQt5.QtCore import QUrl
    _WEBENGINE_AVAILABLE = True
except Exception:
    _WEBENGINE_AVAILABLE = False

log = logging.getLogger(__name__)

# Minimal HTML template that embeds TradingView Lightweight Charts via CDN
_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; }}
  #chart {{ width: 100vw; height: 100vh; }}
</style>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
<div id="chart"></div>
<script>
var chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  width: window.innerWidth,
  height: window.innerHeight,
  layout: {{ background: {{ color: '#1a1a2e' }}, textColor: '#d1d5db' }},
  grid: {{ vertLines: {{ color: '#2d3748' }}, horzLines: {{ color: '#2d3748' }} }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
}});
window.addEventListener('resize', function() {{
  chart.resize(window.innerWidth, window.innerHeight);
}});
var candleSeries = chart.addCandlestickSeries({{
  upColor: '#22c55e', downColor: '#ef4444',
  borderUpColor: '#22c55e', borderDownColor: '#ef4444',
  wickUpColor: '#22c55e', wickDownColor: '#ef4444',
}});
function updateData(dataJson) {{
  var data = JSON.parse(dataJson);
  candleSeries.setData(data);
  if (data.length > 0) {{ chart.timeScale().fitContent(); }}
}}
</script>
</body>
</html>"""


class LightweightChartEngine(QWidget if _QT_AVAILABLE else object):
    """TradingView Lightweight Charts engine embedded in a QWebEngineView."""

    def __init__(self, parent=None):
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            super().__init__()

        self.chart_data: List[Dict] = []
        self.indicators: List[Dict] = []
        self._web_view = None

        if _QT_AVAILABLE and _WEBENGINE_AVAILABLE:
            self._web_view = QWebEngineView(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._web_view)
            self._web_view.setHtml(_HTML_TEMPLATE)
        elif _QT_AVAILABLE:
            # QWebEngineView not available — show a placeholder label
            from PyQt5.QtWidgets import QLabel
            from PyQt5.QtCore import Qt
            lbl = QLabel("Lightweight Charts\n(QWebEngineView 필요)", self)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#9ca3af; font-size:14px; background:#1a1a2e;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(lbl)

    # ------------------------------------------------------------------
    def update_data(self, data: List[Dict[str, Any]]) -> None:
        """Receive list-of-dicts candle data and push to JS chart."""
        if not data:
            return
        self.chart_data = data
        if self._web_view is None:
            return
        try:
            lw_data = self._to_lw_format(data)
            js = f"updateData({json.dumps(lw_data)});"
            self._web_view.page().runJavaScript(js)
        except Exception as e:
            log.error(f"[LightweightChartEngine] update_data error: {e}")

    def render(self, data: pd.DataFrame, **kwargs) -> Dict:
        """Convert DataFrame to Lightweight Charts format and push to JS."""
        records = []
        for i, row in data.iterrows():
            records.append({
                "o": float(row.get("open", row.get("Open", 0))),
                "h": float(row.get("high", row.get("High", 0))),
                "l": float(row.get("low", row.get("Low", 0))),
                "c": float(row.get("close", row.get("Close", 0))),
                "v": float(row.get("volume", row.get("Volume", 0))),
            })
        self.update_data(records)
        return {"data": self.chart_data, "indicators": self.indicators}

    def add_indicator(self, name: str, params: Dict) -> None:
        self.indicators.append({"name": name, "params": params})

    def clear(self) -> None:
        self.chart_data.clear()
        self.indicators.clear()
        if self._web_view:
            self._web_view.page().runJavaScript("candleSeries.setData([]);")

    # ------------------------------------------------------------------
    @staticmethod
    def _to_lw_format(data: List[Dict[str, Any]]) -> List[Dict]:
        """Convert internal candle dicts to Lightweight Charts OHLCV format."""
        import time as _time
        result = []
        base_ts = int(_time.time()) - len(data) * 60
        for i, c in enumerate(data):
            result.append({
                "time": base_ts + i * 60,
                "open": float(c.get("o", 0) or 0),
                "high": float(c.get("h", 0) or 0),
                "low": float(c.get("l", 0) or 0),
                "close": float(c.get("c", 0) or 0),
            })
        return result

