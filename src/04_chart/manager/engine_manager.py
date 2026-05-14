"""
Engine Manager - Handle chart engine switching and button styling

Responsibilities:
- Initialize engine buttons
- Switch between chart engines (M/L/P)
- Update button colors based on active engine
- Handle engine switching UI feedback

Version: v1.0
Created: 2026-02-10 | Copilot
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox
import logging
log = logging.getLogger(__name__)
import traceback


class EngineManager:
    """Manages chart engine switching and button styling"""
    
    def __init__(self, parent):
        """
        Initialize engine manager.
        
        Args:
            parent: ChartWidget instance
        """
        self.parent = parent
        
        # Engine button styles
        self.selected_style = (
            "QPushButton { border:1px solid #c8c8c8; background:#3b82f6; color:#ffffff; "
            "border-radius:4px; font-weight:bold; } QPushButton:hover { background:#3b82f6; }"
        )
        self.unselected_style = (
            "QPushButton { border:1px solid #c8c8c8; background:#2c2c2c; color:#ffffff; "
            "border-radius:4px; font-weight:bold; } QPushButton:hover { background:#3b82f6; }"
        )
        
        # Engine name mapping
        self.engine_map = {
            "mplfinance": ["mplfinance", "mpl", "matplotlib", "main"],
            "lightweight": ["lightweight", "light", "lwc"],
            "plotly": ["plotly", "plot"]
        }
    
    def initialize(self):
        """Initialize engine buttons and colors"""
        try:
            # Get active engine from settings
            active = None
            if isinstance(self.parent.general_settings, dict):
                active = self.parent.general_settings.get('chart_engine')
            if not active:
                active = self.parent.settings.value("chart_engine", "lightweight")
            
            # Update button colors
            self.update_button_colors(active or "lightweight")
            
            # Wire button click events
            if self.parent.btn_mplfinance:
                self.parent.btn_mplfinance.clicked.connect(
                    lambda: self.switch_engine("mplfinance")
                )
            if self.parent.btn_lightweight:
                self.parent.btn_lightweight.clicked.connect(
                    lambda: self.switch_engine("lightweight")
                )
            if self.parent.btn_plotly:
                self.parent.btn_plotly.clicked.connect(
                    lambda: self.switch_engine("plotly")
                )
        except Exception as e:
            log.error(f"[EngineManager] initialize error: {e}")
            traceback.print_exc()
    
    def switch_engine(self, engine_name: str):
        """
        Switch to a specific chart engine (M/L/P only).
        
        Args:
            engine_name: Engine name to switch to
        """
        try:
            # Update button colors immediately for feedback
            self.update_button_colors(engine_name)
            
            # Store the new engine setting
            if not isinstance(self.parent.general_settings, dict):
                self.parent.general_settings = {}
            self.parent.general_settings['chart_engine'] = engine_name
            self.parent.settings.setValue('general_settings', self.parent.general_settings)
            self.parent.settings.setValue("chart_engine", engine_name)
            
            # Use QTimer.singleShot to ensure execution in main thread
            QTimer.singleShot(0, lambda: self._switch_engine_impl(engine_name))
            
        except Exception as e:
            log.error(f"[EngineManager] switch_engine error: {e}")
            traceback.print_exc()
            QMessageBox.warning(
                self.parent, 
                "엔진 전환 실패", 
                f"엔진 전환 중 오류가 발생했습니다:\n{e}"
            )
    
    def _switch_engine_impl(self, engine_name: str):
        """
        Internal implementation of engine switching (runs in main thread).
        
        Args:
            engine_name: Engine name to switch to
        """
        try:
            # Destroy old canvas
            self.parent.canvas_manager.destroy_canvas()
            
            # Clear layout
            self.parent._clear_main_chart_layout_widgets()
            
            # Create new canvas with selected engine
            canvas, engine = self.parent.canvas_manager.create_canvas(engine_name)
            if canvas is None:
                QMessageBox.warning(
                    self.parent,
                    "엔진 전환 실패",
                    f"'{engine_name}' 엔진을 로드할 수 없습니다."
                )
                return
            
            # Add to layout
            self.parent.main_chart_layout.addWidget(canvas)
            
            # Render current data
            if hasattr(self.parent, 'data_manager'):
                self.parent.data_manager.render_all()
            
            # Update engine badge
            if hasattr(self.parent, 'ui_manager') and self.parent.ui_manager.engine_badge:
                self.parent.ui_manager.update_engine_badge(engine_name)
            
            log.info(f"[EngineManager] Engine switched to: {engine_name}")
            
        except Exception as e:
            log.error(f"[EngineManager] _switch_engine_impl error: {e}")
            traceback.print_exc()
            QMessageBox.warning(
                self.parent,
                "엔진 전환 실패",
                f"엔진 전환 중 오류가 발생했습니다:\n{e}"
            )
    
    def update_button_colors(self, selected_engine: str):
        """
        Update button colors to highlight the selected engine.
        
        Args:
            selected_engine: Name of selected engine
        """
        try:
            # Normalize selected engine name
            selected_normalized = selected_engine.lower()
            for key, aliases in self.engine_map.items():
                if selected_normalized in aliases or \
                   any(alias in selected_normalized for alias in aliases):
                    selected_normalized = key
                    break
            
            # Update each button (M/L/P only)
            if self.parent.btn_mplfinance:
                style = self.selected_style if selected_normalized == "mplfinance" \
                        else self.unselected_style
                self.parent.btn_mplfinance.setStyleSheet(style)
            
            if self.parent.btn_lightweight:
                style = self.selected_style if selected_normalized == "lightweight" \
                        else self.unselected_style
                self.parent.btn_lightweight.setStyleSheet(style)
            
            if self.parent.btn_plotly:
                style = self.selected_style if selected_normalized == "plotly" \
                        else self.unselected_style
                self.parent.btn_plotly.setStyleSheet(style)
                
        except Exception as e:
            log.error(f"[EngineManager] update_button_colors error: {e}")
            traceback.print_exc()