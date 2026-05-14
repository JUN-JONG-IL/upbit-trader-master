"""
Canvas manager: handles loading/unloading of chart engines.

Supports 4 chart engines (Bokeh removed - 2026-02-10):
1. matplotlib (UnifiedChartEngine) - Matplotlib-based static charts
2. lightweight - TradingView Lightweight Charts (web-based, real-time)
3. mplfinance - mplfinance library (static analysis, PDF reports)
4. plotly - Plotly interactive web charts

This module dynamically loads the preferred engine and provides fallback logic.

CHANGELOG:
- 2026-02-10 | Copilot | Bokeh 엔진 제거 (4개 엔진만 지원: matplotlib, lightweight, mplfinance, plotly)
"""
from typing import Tuple, Optional
import traceback
import importlib.util
try:
    from PyQt5.QtWidgets import QLabel
    from PyQt5.QtCore import Qt
except Exception:
    QLabel = None  # type: ignore[assignment,misc]
    Qt = None  # type: ignore[assignment]

import logging
log = logging.getLogger(__name__)


class CanvasManager:
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.canvas = None
        self.used_engine = None
        self._is_lightweight = False

    def _is_webengine_available(self) -> bool:
        """Check if PyQt5.QtWebEngineWidgets is available for web-based engines"""
        try:
            return importlib.util.find_spec("PyQt5.QtWebEngineWidgets") is not None
        except Exception:
            return False

    def create_canvas(self, preferred_engine: str = None) -> Tuple[Optional[object], Optional[str]]:
        """
        Create/attach a chart canvas. Returns (canvas_object, engine_name) or (None, None) on failure.

        Supports 4 engines (Bokeh removed):
        - 'matplotlib': Matplotlib-based UnifiedChartEngine (default fallback)
        - 'lightweight': TradingView Lightweight Charts (requires WebEngine)
        - 'mplfinance': mplfinance static charts (PDF/analysis)
        - 'plotly': Plotly interactive web charts (requires WebEngine)

        Args:
            preferred_engine: Engine name to load. If None, uses settings or defaults to 'lightweight'

        Returns:
            Tuple of (canvas_widget, engine_name) or (None, None) on error
        """
        # Determine preferred engine from settings
        preferred = preferred_engine or getattr(self.parent, "general_settings", {}).get("chart_engine") \
            or self.parent.settings.value("chart_engine", None) or "mplfinance"

        log.info(f"[CanvasManager] Preferred engine: {preferred!r}")

        def _load_matplotlib():
            """Load matplotlib-based MatplotlibChartEngine (static charts)"""
            try:
                from ..engines.matplotlib_chart_engine import MatplotlibChartEngine
                return MatplotlibChartEngine(), "matplotlib"
            except Exception as e:
                log.error(f"[CanvasManager] Failed to load MatplotlibChartEngine: {e}")
                traceback.print_exc()
                return None, None

        def _load_mplfinance():
            """Load mplfinance engine (static analysis, PDF reports)"""
            try:
                from ..engines.mplfinance_chart_engine import MplfinanceChartEngine
                return MplfinanceChartEngine(), "mplfinance"
            except Exception as e:
                log.error(f"[CanvasManager] Failed to load MplfinanceChartEngine: {e}")
                # Fallback to matplotlib MatplotlibChartEngine
                log.warning("[CanvasManager] Falling back to matplotlib MatplotlibChartEngine")
                return _load_matplotlib()

        def _load_lightweight():
            """Load lightweight-charts engine (web-based, real-time)"""
            if not self._is_webengine_available():
                log.warning("[CanvasManager] WebEngine not available for lightweight")
                return None, None
            try:
                from ..engines.lightweight_chart_engine import LightweightChartEngine
                return LightweightChartEngine(), "lightweight"
            except Exception as e:
                log.error(f"[CanvasManager] Failed to load LightweightChartEngine: {e}")
                traceback.print_exc()
                return None, None

        def _load_plotly():
            """Load plotly engine (interactive web-based)"""
            if not self._is_webengine_available():
                log.warning("[CanvasManager] WebEngine not available for plotly")
                return None, None
            try:
                from ..engines.plotly_chart_engine import PlotlyChartEngine
                return PlotlyChartEngine(), "plotly"
            except Exception as e:
                log.error(f"[CanvasManager] Failed to load PlotlyChartEngine: {e}")
                traceback.print_exc()
                return None, None

        try:
            canvas = None
            used = None

            # Load the preferred engine with fallback logic
            if preferred == "lightweight":
                canvas, used = _load_lightweight()
                # Fallback to matplotlib if lightweight fails
                if canvas is None:
                    log.warning("[CanvasManager] Lightweight failed, fallback to matplotlib")
                    canvas, used = _load_matplotlib()
            elif preferred == "plotly":
                canvas, used = _load_plotly()
                # Fallback to matplotlib if plotly fails
                if canvas is None:
                    log.warning("[CanvasManager] Plotly failed, fallback to matplotlib")
                    canvas, used = _load_matplotlib()
            elif preferred == "mplfinance":
                canvas, used = _load_mplfinance()
            elif preferred == "matplotlib":
                canvas, used = _load_matplotlib()
            else:
                # Unknown engine (including legacy 'bokeh'), default to matplotlib
                log.warning(f"[CanvasManager] Unknown/unsupported engine '{preferred}', using matplotlib")
                canvas, used = _load_matplotlib()

            # Final fallback to matplotlib if everything else failed
            if canvas is None:
                log.warning("[CanvasManager] All engines failed, final fallback to matplotlib")
                canvas, used = _load_matplotlib()

            if canvas is None:
                raise RuntimeError("No chart engine available")

            # Connect known signals if present
            try:
                if hasattr(canvas, "crosshair_signal"):
                    canvas.crosshair_signal.connect(self.parent._on_crosshair_moved)
            except Exception:
                log.warning("[CanvasManager] crosshair_signal connect failed")

            try:
                if hasattr(canvas, "indicator_clicked"):
                    canvas.indicator_clicked.connect(self.parent._on_indicator_clicked)
            except Exception:
                log.warning("[CanvasManager] indicator_clicked connect failed")

            self.canvas = canvas
            self.used_engine = used
            self._is_lightweight = (used == "lightweight")

            # Adjust throttle based on engine type
            if used in ["lightweight", "plotly"]:
                self.parent._render_throttle_sec = 0.1  # Fast for web-based engines
            else:
                self.parent._render_throttle_sec = 0.5  # Slower for static engines

            log.info(f"[CanvasManager] Canvas created with engine: {used}")
            return canvas, used

        except Exception as e:
            log.error(f"[CanvasManager] create_canvas error: {e}")
            traceback.print_exc()
            return None, None

    def destroy_canvas(self):
        """Safely destroy the current canvas and disconnect all signals"""
        try:
            if self.canvas:
                try:
                    if hasattr(self.canvas, "crosshair_signal"):
                        try:
                            self.canvas.crosshair_signal.disconnect()
                        except Exception:
                            pass
                    if hasattr(self.canvas, "indicator_clicked"):
                        try:
                            self.canvas.indicator_clicked.disconnect()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if hasattr(self.canvas, "close"):
                        try:
                            self.canvas.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                self.canvas = None
                self.used_engine = None
                self._is_lightweight = False
        except Exception:
            traceback.print_exc()

    def get_canvas(self):
        """Get the current canvas widget"""
        return self.canvas

    def get_engine_name(self):
        """Get the name of the currently active engine"""
        return self.used_engine
