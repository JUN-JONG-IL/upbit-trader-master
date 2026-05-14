"""
Layout Schema - JSON schema definition for multi-chart layouts

This module defines the JSON schema for saving and loading multi-chart layouts.
It supports versioning, migration, and validation of layout configurations.

Version: v1.0
Last Modified: 2026-02-08 | Copilot
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


# Schema version 1.0
LAYOUT_SCHEMA_V1 = {
    "version": "1.0",
    "name": str,
    "created_at": str,  # ISO 8601 timestamp
    "grid": {
        "cols": int,  # Number of grid columns
        "rows": int   # Number of grid rows
    },
    "widgets": [
        {
            "id": str,              # Unique widget ID
            "type": str,            # Widget type: "candles", "volume", "indicators"
            "engine": str,          # Engine: "lightweight", "mplfinance", "plotly", "bokeh"
            "symbol": str,          # Trading symbol (e.g., "KRW-BTC")
            "timeframe": str,       # Timeframe (e.g., "1m", "5m", "1h")
            "x": int,               # Grid X position
            "y": int,               # Grid Y position
            "w": int,               # Grid width (in cells)
            "h": int,               # Grid height (in cells)
            "settings": dict        # Widget-specific settings
        }
    ],
    "sync": {
        "time": bool,           # Synchronize time across charts
        "symbol": bool,         # Synchronize symbol across charts
        "crosshair": bool       # Synchronize crosshair position
    }
}


class LayoutSchema:
    """Helper class for creating and validating layout schemas"""
    
    VERSION = "1.0"
    
    @staticmethod
    def create_empty_layout(name: str = "Untitled Layout") -> Dict[str, Any]:
        """
        Create an empty layout with default values.
        
        Args:
            name: Layout name
        
        Returns:
            Dictionary with default layout structure
        """
        return {
            "version": LayoutSchema.VERSION,
            "name": name,
            "created_at": datetime.utcnow().isoformat(),
            "grid": {
                "cols": 12,
                "rows": 6
            },
            "widgets": [],
            "sync": {
                "time": True,
                "symbol": False,
                "crosshair": True
            }
        }
    
    @staticmethod
    def create_widget(
        widget_id: str,
        widget_type: str,
        engine: str,
        symbol: str,
        timeframe: str,
        x: int,
        y: int,
        w: int,
        h: int,
        settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a widget configuration.
        
        Args:
            widget_id: Unique widget identifier
            widget_type: Type of widget
            engine: Chart engine to use
            symbol: Trading symbol
            timeframe: Timeframe string
            x, y: Grid position
            w, h: Grid size
            settings: Additional widget settings
        
        Returns:
            Widget configuration dictionary
        """
        return {
            "id": widget_id,
            "type": widget_type,
            "engine": engine,
            "symbol": symbol,
            "timeframe": timeframe,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "settings": settings or {}
        }
    
    @staticmethod
    def validate_layout(layout: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate a layout configuration.
        
        Args:
            layout: Layout dictionary to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check required top-level fields
            if "version" not in layout:
                return False, "Missing 'version' field"
            
            if "name" not in layout:
                return False, "Missing 'name' field"
            
            if "created_at" not in layout:
                return False, "Missing 'created_at' field"
            
            if "grid" not in layout:
                return False, "Missing 'grid' field"
            
            if "widgets" not in layout:
                return False, "Missing 'widgets' field"
            
            if "sync" not in layout:
                return False, "Missing 'sync' field"
            
            # Validate grid
            grid = layout["grid"]
            if "cols" not in grid or "rows" not in grid:
                return False, "Grid must have 'cols' and 'rows'"
            
            if not isinstance(grid["cols"], int) or not isinstance(grid["rows"], int):
                return False, "Grid cols and rows must be integers"
            
            if grid["cols"] < 1 or grid["rows"] < 1:
                return False, "Grid cols and rows must be >= 1"
            
            # Validate widgets
            if not isinstance(layout["widgets"], list):
                return False, "'widgets' must be a list"
            
            widget_ids = set()
            for i, widget in enumerate(layout["widgets"]):
                # Check required widget fields
                required_fields = ["id", "type", "engine", "symbol", "timeframe", 
                                 "x", "y", "w", "h", "settings"]
                for field in required_fields:
                    if field not in widget:
                        return False, f"Widget {i} missing '{field}' field"
                
                # Check for duplicate IDs
                if widget["id"] in widget_ids:
                    return False, f"Duplicate widget ID: {widget['id']}"
                widget_ids.add(widget["id"])
                
                # Validate widget position and size
                if widget["x"] < 0 or widget["y"] < 0:
                    return False, f"Widget {widget['id']} has negative position"
                
                if widget["w"] <= 0 or widget["h"] <= 0:
                    return False, f"Widget {widget['id']} has invalid size"
                
                # Validate widget fits in grid
                if widget["x"] + widget["w"] > grid["cols"]:
                    return False, f"Widget {widget['id']} exceeds grid width"
                
                if widget["y"] + widget["h"] > grid["rows"]:
                    return False, f"Widget {widget['id']} exceeds grid height"
                
                # Validate engine type
                valid_engines = ["lightweight", "mplfinance", "plotly", "bokeh"]
                if widget["engine"] not in valid_engines:
                    return False, f"Widget {widget['id']} has invalid engine: {widget['engine']}"
            
            # Validate sync options
            sync = layout["sync"]
            for key in ["time", "symbol", "crosshair"]:
                if key not in sync:
                    return False, f"Sync options missing '{key}'"
                if not isinstance(sync[key], bool):
                    return False, f"Sync option '{key}' must be boolean"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    @staticmethod
    def save_to_file(layout: Dict[str, Any], filepath: str) -> bool:
        """
        Save layout to JSON file.
        
        Args:
            layout: Layout dictionary
            filepath: Path to save file
        
        Returns:
            True if successful
        """
        try:
            # Validate before saving
            is_valid, error = LayoutSchema.validate_layout(layout)
            if not is_valid:
                logger.error(f"Cannot save invalid layout: {error}")
                return False
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(layout, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Layout saved to: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save layout: {e}", exc_info=True)
            return False
    
    @staticmethod
    def load_from_file(filepath: str) -> Optional[Dict[str, Any]]:
        """
        Load layout from JSON file.
        
        Args:
            filepath: Path to load from
        
        Returns:
            Layout dictionary or None if failed
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                layout = json.load(f)
            
            # Validate loaded layout
            is_valid, error = LayoutSchema.validate_layout(layout)
            if not is_valid:
                logger.error(f"Loaded layout is invalid: {error}")
                return None
            
            # Check if migration is needed
            if layout.get("version") != LayoutSchema.VERSION:
                logger.warning(f"Layout version mismatch: {layout.get('version')} != {LayoutSchema.VERSION}")
                # TODO: Implement migration logic
            
            logger.info(f"Layout loaded from: {filepath}")
            return layout
            
        except Exception as e:
            logger.error(f"Failed to load layout: {e}", exc_info=True)
            return None
    
    @staticmethod
    def to_json(layout: Dict[str, Any]) -> str:
        """
        Convert layout to JSON string.
        
        Args:
            layout: Layout dictionary
        
        Returns:
            JSON string
        """
        return json.dumps(layout, indent=2, ensure_ascii=False)
    
    @staticmethod
    def from_json(json_str: str) -> Optional[Dict[str, Any]]:
        """
        Parse layout from JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            Layout dictionary or None if failed
        """
        try:
            layout = json.loads(json_str)
            
            # Validate
            is_valid, error = LayoutSchema.validate_layout(layout)
            if not is_valid:
                logger.error(f"Parsed layout is invalid: {error}")
                return None
            
            return layout
            
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}", exc_info=True)
            return None


# Example layout configurations
EXAMPLE_SINGLE_CHART = {
    "version": "1.0",
    "name": "Single Chart",
    "created_at": "2026-02-08T00:00:00Z",
    "grid": {"cols": 12, "rows": 6},
    "widgets": [
        {
            "id": "chart-1",
            "type": "candles",
            "engine": "lightweight",
            "symbol": "KRW-BTC",
            "timeframe": "1m",
            "x": 0, "y": 0, "w": 12, "h": 6,
            "settings": {"indicators": ["MA20", "MA50"]}
        }
    ],
    "sync": {"time": True, "symbol": False, "crosshair": True}
}

EXAMPLE_QUAD_CHART = {
    "version": "1.0",
    "name": "Quad Chart (2x2)",
    "created_at": "2026-02-08T00:00:00Z",
    "grid": {"cols": 12, "rows": 12},
    "widgets": [
        {
            "id": "chart-1m",
            "type": "candles",
            "engine": "lightweight",
            "symbol": "KRW-BTC",
            "timeframe": "1m",
            "x": 0, "y": 0, "w": 6, "h": 6,
            "settings": {"indicators": ["MA20"]}
        },
        {
            "id": "chart-5m",
            "type": "candles",
            "engine": "lightweight",
            "symbol": "KRW-BTC",
            "timeframe": "5m",
            "x": 6, "y": 0, "w": 6, "h": 6,
            "settings": {"indicators": ["MA20"]}
        },
        {
            "id": "chart-15m",
            "type": "candles",
            "engine": "lightweight",
            "symbol": "KRW-BTC",
            "timeframe": "15m",
            "x": 0, "y": 6, "w": 6, "h": 6,
            "settings": {"indicators": ["MA50"]}
        },
        {
            "id": "chart-1h",
            "type": "candles",
            "engine": "lightweight",
            "symbol": "KRW-BTC",
            "timeframe": "1h",
            "x": 6, "y": 6, "w": 6, "h": 6,
            "settings": {"indicators": ["MA50", "RSI"]}
        }
    ],
    "sync": {"time": True, "symbol": True, "crosshair": True}
}
