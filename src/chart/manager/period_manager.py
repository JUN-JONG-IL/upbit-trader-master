"""
Period Manager - Handle period/timeframe menu, chips, and slider

Responsibilities:
- Manage period intervals and selection state
- Build and control period menu
- Handle period chips display and reflow
- Manage period slider
- Apply interval changes

Version: v1.0
Created: 2026-02-10 | Copilot
"""

from typing import List, Tuple, Set
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QCheckBox, QToolButton

from ..core.period_menu_helper import build_period_menu
from ..core.chip_manager import reflow_chips


class PeriodManager:
    """Manages period/timeframe selection UI and state"""
    
    def __init__(self, parent):
        """
        Initialize period manager.
        
        Args:
            parent: ChartWidget instance
        """
        self.parent = parent
        self.intervals: List[Tuple[str, str]] = []
        self.label_by_interval: dict = {}
        self.order: List[str] = []
        self.valid_intervals: Set[str] = set()
        
        self.pending_selected_set: Set[str] = set()
        self.applied_interval: str = "minute1"
        
        self.period_menu = None
        self._menu_rows: dict = {}
        
        # Chip window state
        self.chip_window_start = 0
        self.chip_window_size = 4
        self._reflowing = False
    
    def initialize(self):
        """Initialize period intervals and menu"""
        # Define intervals
        self.intervals = [
            ("1틱", "tick1"), ("3틱", "tick3"), ("5틱", "tick5"), ("10틱", "tick10"),
            ("30틱", "tick30"), ("60틱", "tick60"), ("초", "second"),
            ("1분", "minute1"), ("3분", "minute3"), ("5분", "minute5"),
            ("10분", "minute10"), ("15분", "minute15"), ("30분", "minute30"),
            ("60분", "minute60"), ("240분", "minute240"),
            ("일", "day"), ("주", "week"), ("월", "month"), ("년", "year"),
        ]
        
        self.label_by_interval = {v: l for l, v in self.intervals}
        self.order = [v for _, v in self.intervals]
        self.valid_intervals = set(self.order)
        
        # Load saved state
        pending_list = self.parent.settings.value("pending_selected_intervals", [], type=list)
        if not pending_list:
            pending_list = ["minute1"]
        pending_list = [p for p in pending_list if p in self.valid_intervals]
        self.pending_selected_set = set(pending_list)
        
        self.applied_interval = self.parent.settings.value("interval", "minute1")
        if self.applied_interval not in self.label_by_interval:
            self.applied_interval = "minute1"
        
        # Build period menu
        self._build_menu()
    
    def _build_menu(self):
        """Build period selection menu"""
        try:
            self.period_menu, self._menu_rows = build_period_menu(
                self.parent,
                self.intervals,
                self.pending_selected_set,
                self._on_period_checkbox_toggled
            )
            
            if self.parent.period_dropdown_button:
                if isinstance(self.parent.period_dropdown_button, QToolButton):
                    self.parent.period_dropdown_button.setPopupMode(QToolButton.InstantPopup)
                    self.parent.period_dropdown_button.setMenu(self.period_menu)
                else:
                    self.parent.period_dropdown_button.clicked.connect(self.toggle_period_menu)
            
            if self.period_menu:
                self.period_menu.aboutToShow.connect(self._on_menu_show)
                self.period_menu.aboutToHide.connect(self._on_menu_hide)
        except Exception:
            import traceback
            traceback.print_exc()
            self.period_menu = None
            self._menu_rows = {}
    
    def _on_period_checkbox_toggled(self, interval: str, checked: bool):
        """
        Handle period checkbox toggle.
        
        Args:
            interval: Interval key
            checked: Whether checkbox is checked
        """
        try:
            if checked:
                self.pending_selected_set.add(interval)
            else:
                self.pending_selected_set.discard(interval)
            self.reflow_chips()
        except Exception:
            import traceback
            traceback.print_exc()
    
    def toggle_period_menu(self):
        """Toggle period menu visibility"""
        if not self.period_menu:
            return
        if self.period_menu.isVisible():
            self.period_menu.close()
            return
        pos = self.parent.period_dropdown_button.mapToGlobal(
            self.parent.period_dropdown_button.rect().bottomLeft()
        )
        self.period_menu.popup(pos)
    
    def _on_menu_show(self):
        """Handle menu show event"""
        if hasattr(self.parent, 'ui_manager'):
            self.parent.ui_manager.set_dropdown_icon(opened=True)
        self._sync_menu_rows_from_state()
    
    def _on_menu_hide(self):
        """Handle menu hide event"""
        if hasattr(self.parent, 'ui_manager'):
            self.parent.ui_manager.set_dropdown_icon(opened=False)
        self._save_pending()
        self.reflow_chips()
    
    def _sync_menu_rows_from_state(self):
        """Sync menu checkbox states from pending selection"""
        for interval, widget in self._menu_rows.items():
            if isinstance(widget, QCheckBox):
                widget.setChecked(interval in self.pending_selected_set)
    
    def _save_pending(self):
        """Save pending selected intervals to settings"""
        self.parent.settings.setValue("pending_selected_intervals", self._sorted_pending_list())
    
    def _sorted_pending_list(self) -> list:
        """Get sorted list of pending selected intervals"""
        return [itv for itv in self.order if itv in self.pending_selected_set]
    
    def reflow_chips(self):
        """Reflow period chips based on current window state"""
        if self._reflowing:
            return
        self._reflowing = True
        
        try:
            selected = self._sorted_pending_list()
            if not selected:
                self._clear_chip_layout(hard=True)
                if self.parent.period_slider:
                    self.parent.period_slider.hide()
                return
            
            # Calculate chip window size
            available_width = max(1, self.parent.period_chip_container.width() 
                                if self.parent.period_chip_container else 1)
            approx_chip_width = 58
            max_count = max(1, min(len(selected), max(1, available_width // approx_chip_width)))
            self.chip_window_size = max_count
            max_start = max(0, len(selected) - self.chip_window_size)
            
            if self.chip_window_start > max_start:
                self.chip_window_start = max_start
            
            # Show/hide slider
            if len(selected) > self.chip_window_size:
                if self.parent.period_slider:
                    self.parent.period_slider.setRange(0, max_start)
                    if self.parent.period_slider.value() != self.chip_window_start:
                        self.parent.period_slider.setValue(self.chip_window_start)
                    self.parent.period_slider.show()
            else:
                if self.parent.period_slider:
                    self.parent.period_slider.hide()
                self.chip_window_start = 0
            
            # Build chip list
            show_keys = selected[self.chip_window_start: self.chip_window_start + self.chip_window_size]
            show_list = []
            for k in show_keys:
                show_list.append({"label": self.label_by_interval.get(k, k), "key": k})
            
            # Reflow chips using chip_manager
            reflow_chips(
                self.parent.period_chip_layout,
                self.parent.period_chip_container,
                show_list,
                self.applied_interval,
                self.apply_interval_from_chip,
                self.chip_window_start,
                self.chip_window_size,
                self.parent.period_slider
            )
            
            # Add ellipsis if more chips exist
            if self.chip_window_start + self.chip_window_size < len(selected):
                more = QLabel("…", self.parent.period_chip_container)
                more.setStyleSheet("font-size: 12px; color: #6b7280; padding: 0px 2px;")
                more.setFixedHeight(24)
                self.parent.period_chip_layout.addWidget(more)
        
        finally:
            self._reflowing = False
    
    def _clear_chip_layout(self, hard: bool = False):
        """Clear chip layout"""
        layout = self.parent.period_chip_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                if hard:
                    w.setParent(None)
                w.deleteLater()
    
    def on_slider_changed(self, value: int):
        """
        Handle slider value change.
        
        Args:
            value: New slider value
        """
        self.chip_window_start = int(value)
        self.reflow_chips()
    
    def apply_interval_from_chip(self, interval: str):
        """
        Apply selected interval from chip click.
        
        Args:
            interval: Interval key to apply
        """
        self.applied_interval = interval
        self.parent.settings.setValue("interval", self.applied_interval)
        self.reflow_chips()
        
        # Update worker if exists
        if self.parent._worker:
            self.parent._worker.set_symbol_timeframe(self.parent._code, self.applied_interval)
        
        # Request new data
        if hasattr(self.parent, 'data_manager'):
            self.parent.data_manager.request_initial()