"""
UI Manager - Handle UI initialization and widget binding

Responsibilities:
- Bind UI widgets from .ui file
- Initialize UI elements (validators, icons, layouts)
- Configure widget properties (size, style, etc.)
- Create engine badge overlay

Version: v1.0
Created: 2026-02-10 | Copilot
"""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtGui import QIntValidator


class UIManager:
    """Manages UI initialization and widget binding for ChartWidget"""
    
    def __init__(self, parent):
        """
        Initialize UI manager.
        
        Args:
            parent: ChartWidget instance
        """
        self.parent = parent
        self.engine_badge = None
        self._period_icon_down = None
        self._period_icon_up = None
    
    def bind_widgets(self):
        """Bind UI widgets from chart.ui to parent attributes"""
        # Toolbar widgets
        self.parent.candle_count_edit = getattr(self.parent, "candle_count_edit", None)
        self.parent.snapshot_button = getattr(self.parent, "snapshot_button", None)
        self.parent.multi_chart_button = getattr(self.parent, "multi_chart_button", None)
        self.parent.settings_button = getattr(self.parent, "settings_button", None)
        
        # Chart engine buttons (M/L/P only)
        self.parent.btn_mplfinance = getattr(self.parent, "btn_mplfinance", None)
        self.parent.btn_lightweight = getattr(self.parent, "btn_lightweight", None)
        self.parent.btn_plotly = getattr(self.parent, "btn_plotly", None)
        
        # Period row
        self.parent.period_dropdown_button = getattr(self.parent, "period_button", None)
        self.parent.period_chip_container = getattr(self.parent, "period_chip_container", None)
        self.parent.period_chip_layout = getattr(self.parent, "period_chip_layout", None)
        
        # Slider and splitter areas
        self.parent.period_slider = getattr(self.parent, "period_slider", None)
        self.parent.main_chart = getattr(self.parent, "main_chart", None)
        self.parent.indicator_area = getattr(self.parent, "indicator_area", None)
        self.parent.chart_splitter = getattr(self.parent, "chart_splitter", None)
    
    def initialize_ui(self):
        """Initialize all UI elements"""
        self._setup_layouts()
        self._setup_size_policies()
        self._setup_validators()
        self._setup_icons()
        self._setup_slider()
        self._hide_indicator_area()
    
    def _setup_layouts(self):
        """Setup layout margins and spacing"""
        try:
            if self.parent.period_chip_layout:
                self.parent.period_chip_layout.setAlignment(Qt.AlignVCenter)
        except Exception:
            pass
        
        try:
            if hasattr(self.parent, "verticalLayout"):
                self.parent.verticalLayout.setContentsMargins(0, 0, 0, 0)
                self.parent.verticalLayout.setSpacing(0)
            if hasattr(self.parent, "horizontalLayout_toolbar"):
                self.parent.horizontalLayout_toolbar.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
    
    def _setup_size_policies(self):
        """Setup widget size policies"""
        self.parent.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def _setup_validators(self):
        """Setup input validators"""
        if self.parent.candle_count_edit:
            self.parent.candle_count_edit.setValidator(QIntValidator(0, 9999, self.parent))
            if not self.parent.candle_count_edit.text():
                self.parent.candle_count_edit.setText("200")
    
    def _setup_icons(self):
        """Setup icons for buttons"""
        try:
            # Period dropdown icons
            if self.parent.period_dropdown_button:
                self.parent.period_dropdown_button.setIconSize(QSize(18, 18))
                style = self.parent.style()
                self._period_icon_down = style.standardIcon(style.SP_ArrowDown)
                self._period_icon_up = style.standardIcon(style.SP_ArrowUp)
                self.parent.period_dropdown_button.setIcon(self._period_icon_down)
                self.parent.period_dropdown_button.show()
                # Hide native menu indicator
                self.parent.period_dropdown_button.setStyleSheet(
                    "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
                )
            
            # Toolbar button icons
            if self.parent.snapshot_button:
                self.parent.snapshot_button.setIconSize(QSize(18, 18))
            if self.parent.multi_chart_button:
                self.parent.multi_chart_button.setIconSize(QSize(18, 18))
            if self.parent.settings_button:
                self.parent.settings_button.setIconSize(QSize(18, 18))
        except Exception:
            pass
    
    def _setup_slider(self):
        """Setup period slider"""
        if self.parent.period_slider:
            self.parent.period_slider.setFixedHeight(10)
            self.parent.period_slider.hide()
    
    def _hide_indicator_area(self):
        """Hide indicator area initially"""
        if self.parent.indicator_area:
            self.parent.indicator_area.hide()
        if self.parent.chart_splitter:
            self.parent.chart_splitter.setSizes([self.parent.height(), 0])
    
    def create_engine_badge(self):
        """Create engine badge overlay on main chart"""
        if not hasattr(self, "engine_badge") or self.engine_badge is None:
            try:
                self.engine_badge = QLabel(self.parent.main_chart)
                self.engine_badge.setStyleSheet("""
                    QLabel { 
                        background-color: rgba(17,24,39,0.85); 
                        color: white;
                        padding: 4px 8px; 
                        border-radius: 6px; 
                        font-size: 11px; 
                    }
                """)
                self.engine_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
                self.engine_badge.hide()
            except Exception:
                self.engine_badge = None
    
    def update_engine_badge(self, engine_name: str):
        """
        Update engine badge text and position.
        
        Args:
            engine_name: Name of current engine
        """
        if self.engine_badge:
            self.engine_badge.setText(f"engine: {engine_name}")
            self.engine_badge.show()
            w = max(1, self.parent.main_chart.width())
            badge_w = self.engine_badge.sizeHint().width()
            x = max(8, w - badge_w - 12)
            self.engine_badge.move(x, 8)
    
    def set_dropdown_icon(self, opened: bool):
        """
        Set period dropdown button icon (up/down arrow).
        
        Args:
            opened: True if menu is open, False if closed
        """
        try:
            if not self.parent.period_dropdown_button:
                return
            if opened:
                icon = self._period_icon_up if self._period_icon_up else \
                       self.parent.style().standardIcon(self.parent.style().SP_ArrowUp)
            else:
                icon = self._period_icon_down if self._period_icon_down else \
                       self.parent.style().standardIcon(self.parent.style().SP_ArrowDown)
            self.parent.period_dropdown_button.setIcon(icon)
        except Exception:
            pass