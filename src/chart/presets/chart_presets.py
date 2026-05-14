"""
Chart Presets - Predefined multi-chart layout templates

This module provides ready-to-use chart layout presets for common trading scenarios.
Users can quickly switch between different layout configurations.

Version: v1.0
Last Modified: 2026-02-08 | Copilot
"""

from typing import Dict, Any, List
from datetime import datetime


class ChartPresets:
    """Collection of predefined chart layout presets"""
    
    @staticmethod
    def single_chart(symbol: str = "KRW-BTC", timeframe: str = "1m") -> Dict[str, Any]:
        """
        Single chart layout - one main chart with volume.
        
        Best for: Focused analysis on a single timeframe
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
        
        Returns:
            Layout configuration
        """
        return {
            "version": "1.0",
            "name": "Single Chart",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 8},
            "widgets": [
                {
                    "id": "main-chart",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "x": 0, "y": 0, "w": 12, "h": 8,
                    "settings": {
                        "indicators": ["MA20", "MA50"],
                        "show_volume": True
                    }
                }
            ],
            "sync": {
                "time": True,
                "symbol": False,
                "crosshair": True
            }
        }
    
    @staticmethod
    def dual_timeframe(symbol: str = "KRW-BTC") -> Dict[str, Any]:
        """
        Dual timeframe layout - two charts side by side.
        
        Best for: Comparing short-term and long-term trends
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Layout configuration
        """
        return {
            "version": "1.0",
            "name": "Dual Timeframe",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 6},
            "widgets": [
                {
                    "id": "chart-1m",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "1m",
                    "x": 0, "y": 0, "w": 6, "h": 6,
                    "settings": {
                        "indicators": ["MA20"],
                        "show_volume": True
                    }
                },
                {
                    "id": "chart-1h",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 6, "y": 0, "w": 6, "h": 6,
                    "settings": {
                        "indicators": ["MA50", "MA200"],
                        "show_volume": True
                    }
                }
            ],
            "sync": {
                "time": True,
                "symbol": True,
                "crosshair": True
            }
        }
    
    @staticmethod
    def quad_chart(symbol: str = "KRW-BTC") -> Dict[str, Any]:
        """
        Quad chart layout (2x2) - four different timeframes.
        
        Best for: Multi-timeframe analysis
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Layout configuration
        """
        return {
            "version": "1.0",
            "name": "Quad Chart (2x2)",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 12},
            "widgets": [
                {
                    "id": "chart-1m",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "1m",
                    "x": 0, "y": 0, "w": 6, "h": 6,
                    "settings": {"indicators": ["MA20"]}
                },
                {
                    "id": "chart-5m",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "5m",
                    "x": 6, "y": 0, "w": 6, "h": 6,
                    "settings": {"indicators": ["MA20"]}
                },
                {
                    "id": "chart-15m",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "15m",
                    "x": 0, "y": 6, "w": 6, "h": 6,
                    "settings": {"indicators": ["MA50"]}
                },
                {
                    "id": "chart-1h",
                    "type": "candles",
                    "engine": "lightweight",
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 6, "y": 6, "w": 6, "h": 6,
                    "settings": {"indicators": ["MA50", "RSI"]}
                }
            ],
            "sync": {
                "time": True,
                "symbol": True,
                "crosshair": True
            }
        }
    
    @staticmethod
    def comparison_chart(symbols: List[str] = None) -> Dict[str, Any]:
        """
        Comparison chart - compare multiple symbols side by side.
        
        Best for: Relative performance analysis
        
        Args:
            symbols: List of trading symbols (default: BTC, ETH, XRP)
        
        Returns:
            Layout configuration
        """
        if symbols is None:
            symbols = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
        
        # Ensure we have at most 3 symbols
        symbols = symbols[:3]
        
        # Calculate widget width
        num_symbols = len(symbols)
        widget_width = 12 // num_symbols
        
        widgets = []
        for i, symbol in enumerate(symbols):
            widgets.append({
                "id": f"chart-{symbol}",
                "type": "candles",
                "engine": "lightweight",
                "symbol": symbol,
                "timeframe": "1h",
                "x": i * widget_width,
                "y": 0,
                "w": widget_width,
                "h": 6,
                "settings": {
                    "indicators": ["MA20", "MA50"],
                    "show_volume": True
                }
            })
        
        return {
            "version": "1.0",
            "name": "Symbol Comparison",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 6},
            "widgets": widgets,
            "sync": {
                "time": True,
                "symbol": False,  # Don't sync symbols for comparison
                "crosshair": True
            }
        }
    
    @staticmethod
    def report_view(symbol: str = "KRW-BTC") -> Dict[str, Any]:
        """
        Report view layout - static charts for PDF export.
        
        Best for: Generating analysis reports
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Layout configuration
        """
        return {
            "version": "1.0",
            "name": "Report View",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 12},
            "widgets": [
                {
                    "id": "main-chart",
                    "type": "candles",
                    "engine": "mplfinance",  # Use mplfinance for PDF export
                    "symbol": symbol,
                    "timeframe": "1d",
                    "x": 0, "y": 0, "w": 12, "h": 8,
                    "settings": {
                        "indicators": ["MA20", "MA50", "RSI", "MACD"],
                        "style": "charles"
                    }
                },
                {
                    "id": "volume-chart",
                    "type": "volume",
                    "engine": "mplfinance",
                    "symbol": symbol,
                    "timeframe": "1d",
                    "x": 0, "y": 8, "w": 12, "h": 4,
                    "settings": {}
                }
            ],
            "sync": {
                "time": True,
                "symbol": False,
                "crosshair": False
            }
        }
    
    @staticmethod
    def analysis_workspace(symbol: str = "KRW-BTC") -> Dict[str, Any]:
        """
        Analysis workspace - main chart with indicator panels.
        
        Best for: Detailed technical analysis
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Layout configuration
        """
        return {
            "version": "1.0",
            "name": "Analysis Workspace",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 12},
            "widgets": [
                {
                    "id": "main-chart",
                    "type": "candles",
                    "engine": "plotly",  # Interactive chart
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 0, "y": 0, "w": 12, "h": 6,
                    "settings": {
                        "indicators": ["MA20", "MA50", "MA200"],
                        "show_volume": True
                    }
                },
                {
                    "id": "rsi-panel",
                    "type": "indicators",
                    "engine": "plotly",
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 0, "y": 6, "w": 6, "h": 3,
                    "settings": {
                        "indicators": ["RSI"]
                    }
                },
                {
                    "id": "macd-panel",
                    "type": "indicators",
                    "engine": "plotly",
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 6, "y": 6, "w": 6, "h": 3,
                    "settings": {
                        "indicators": ["MACD"]
                    }
                },
                {
                    "id": "volume-panel",
                    "type": "volume",
                    "engine": "plotly",
                    "symbol": symbol,
                    "timeframe": "1h",
                    "x": 0, "y": 9, "w": 12, "h": 3,
                    "settings": {}
                }
            ],
            "sync": {
                "time": True,
                "symbol": False,
                "crosshair": True
            }
        }
    
    @staticmethod
    def dashboard_view(symbols: List[str] = None) -> Dict[str, Any]:
        """
        Dashboard view - multiple symbols in grid layout.
        
        Best for: Market overview and monitoring
        
        Args:
            symbols: List of trading symbols (default: top 4 coins)
        
        Returns:
            Layout configuration
        """
        if symbols is None:
            symbols = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA"]
        
        # Ensure we have at most 4 symbols
        symbols = symbols[:4]
        
        widgets = []
        positions = [(0, 0), (6, 0), (0, 6), (6, 6)]
        
        for i, symbol in enumerate(symbols):
            x, y = positions[i]
            widgets.append({
                "id": f"chart-{symbol}",
                "type": "candles",
                "engine": "bokeh",  # Web dashboard engine
                "symbol": symbol,
                "timeframe": "5m",
                "x": x, "y": y, "w": 6, "h": 6,
                "settings": {
                    "indicators": ["MA20"],
                    "show_volume": True
                }
            })
        
        return {
            "version": "1.0",
            "name": "Dashboard View",
            "created_at": datetime.utcnow().isoformat(),
            "grid": {"cols": 12, "rows": 12},
            "widgets": widgets,
            "sync": {
                "time": True,
                "symbol": False,
                "crosshair": False
            }
        }
    
    @staticmethod
    def get_all_presets() -> Dict[str, callable]:
        """
        Get all available presets.
        
        Returns:
            Dictionary of preset_name -> function
        """
        return {
            "Single Chart": ChartPresets.single_chart,
            "Dual Timeframe": ChartPresets.dual_timeframe,
            "Quad Chart (2x2)": ChartPresets.quad_chart,
            "Symbol Comparison": ChartPresets.comparison_chart,
            "Report View": ChartPresets.report_view,
            "Analysis Workspace": ChartPresets.analysis_workspace,
            "Dashboard View": ChartPresets.dashboard_view
        }
    
    @staticmethod
    def get_preset_names() -> List[str]:
        """
        Get list of available preset names.
        
        Returns:
            List of preset names
        """
        return list(ChartPresets.get_all_presets().keys())
