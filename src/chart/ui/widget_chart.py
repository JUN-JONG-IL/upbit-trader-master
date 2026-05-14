# src/chart/ui/widget_chart.py
# -*- coding: utf-8 -*-
"""
Chart widget (controller) — Refactored with modular managers

This file serves as the main controller, delegating responsibilities to:
- UIManager: UI initialization and widget binding
- PeriodManager: Period menu, chips, and slider
- EngineManager: Engine switching and button styling
- DataManager: Data fetching and rendering
- CanvasManager: Chart engine loading
- WorkerManager: Worker lifecycle

CHANGELOG:
- 2026-02-10 | Copilot | 모듈화 (1047줄 → ~350줄): manager 폴더 생성, 책임 분리
- 2026-02-10 | Copilot | Bokeh 엔진 제거 (M/L/P만 유지)
"""
from __future__ import annotations

import os
from typing import Dict, Any, List, Optional

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QDialog, QSizePolicy,
    QLabel, QMessageBox
)
from PyQt5.uic import loadUi

import logging
log = logging.getLogger(__name__)

# Managers
from ..manager import UIManager, PeriodManager, EngineManager, DataManager
from ..core.canvas_manager import CanvasManager
from ..workers.worker_manager import start_worker, stop_worker
from ..manager.settings_manager import load_general, save_general, load_indicators, save_indicators
from ..utils.export_manager import ExportManager


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class ChartWidget(QWidget):
    """
    Main chart widget controller.
    
    Responsibilities are delegated to specialized managers:
    - UIManager: UI initialization
    - PeriodManager: Period/timeframe management
    - EngineManager: Chart engine switching
    - DataManager: Data fetch/render
    - CanvasManager: Engine loading
    """

    def __init__(self, parent=None, ui_state_manager=None):
        super().__init__(parent)
        loadUi(_ui_file_path("chart.ui"), self)

        # QSettings
        self.settings = QSettings("UpbitTrader", "ChartSettings")

        # UIStateManager (external)
        self.ui_state_manager = ui_state_manager
        if self.ui_state_manager:
            try:
                self.ui_state_manager.symbol_changed.connect(self._on_symbol_changed)
                self.ui_state_manager.timeframe_changed.connect(self._on_timeframe_changed)
            except Exception:
                pass

        # State
        self._code = "KRW-BTC"
        self._candle_data: List[Dict[str, Any]] = []
        self._last_candle_timestamp = None
        self._last_requested_id = 0

        # Settings
        self.active_indicators = load_indicators(self.settings) or {
            'sma_20': False, 'ema_20': True, 'wma_20': False,
            'bb': True, 'atr_14': False,
            'rsi_14': True, 'macd': False, 'stochastic': False, 'adx_14': False,
            'volume': True, 'obv': False,
            'ichimoku': False,
        }
        self.general_settings = load_general(self.settings) or {}

        # Debounce timer for candle count edit
        self._count_edit_debounce_timer = QTimer(self)
        self._count_edit_debounce_timer.setSingleShot(True)
        self._count_edit_debounce_timer.setInterval(250)
        self._count_edit_debounce_timer.timeout.connect(self._on_count_edit_debounced)

        # Initialize managers
        self.ui_manager = UIManager(self)
        self.period_manager = PeriodManager(self)
        self.engine_manager = EngineManager(self)
        self.data_manager = DataManager(self)
        self.canvas_manager = CanvasManager(self)
        
        self._worker = None

        # Initialize UI and components
        self._init_all()

    def _init_all(self):
        """Initialize all components in order"""
        # 1. Bind UI widgets
        self.ui_manager.bind_widgets()
        
        # 2. Initialize UI
        self.ui_manager.initialize_ui()
        
        # 3. Create engine badge
        self.ui_manager.create_engine_badge()
        
        # 4. Initialize period manager
        self.period_manager.initialize()
        
        # 5. Initialize engine buttons
        self.engine_manager.initialize()
        
        # 6. Initialize canvas
        self._init_canvas()
        
        # 7. Connect signals
        self._connect_signals()
        
        # 8. Initialize worker
        self._init_worker()
        
        # 9. Initial data request
        self.data_manager.request_initial()
    
    def _connect_signals(self):
        """Connect UI signals to handlers"""
        if self.candle_count_edit:
            self.candle_count_edit.textChanged.connect(self._on_count_edit_text_changed)
        
        if self.snapshot_button:
            self.snapshot_button.clicked.connect(self.save_chart_snapshot)
        
        if self.multi_chart_button:
            self.multi_chart_button.clicked.connect(self.open_multi_chart_dialog)
        
        if self.settings_button:
            self.settings_button.clicked.connect(self.open_settings_dialog)
        
        if self.period_slider:
            self.period_slider.valueChanged.connect(self.period_manager.on_slider_changed)
    
    def _init_canvas(self):
        """Initialize chart canvas"""
        try:
            canvas, engine = self.canvas_manager.create_canvas(
                self.general_settings.get('chart_engine')
            )
            if canvas is not None:
                self._ensure_main_chart_layout()
                self.main_chart_layout.addWidget(canvas)
        except Exception:
            log.exception("[ChartWidget] canvas init failed")
    
    def _ensure_main_chart_layout(self):
        """Ensure main chart layout exists"""
        if hasattr(self, "main_chart_layout") and self.main_chart_layout is not None:
            return
        self.main_chart_layout = QVBoxLayout(self.main_chart)
        self.main_chart_layout.setContentsMargins(0, 0, 0, 0)
    
    def _clear_main_chart_layout_widgets(self):
        """Clear all widgets from main chart layout"""
        try:
            if not hasattr(self, "main_chart_layout") or self.main_chart_layout is None:
                return
            layout = self.main_chart_layout
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    try:
                        if hasattr(widget, 'crosshair_signal'):
                            widget.crosshair_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        if hasattr(widget, 'indicator_clicked'):
                            widget.indicator_clicked.disconnect()
                    except Exception:
                        pass
                    widget.setParent(None)
                    widget.deleteLater()
        except Exception:
            import traceback
            traceback.print_exc()
    
    def _init_worker(self):
        """Initialize candle fetch worker"""
        try:
            self._worker = start_worker(
                self,
                self.data_manager.on_data_fetched,
                self.data_manager.on_realtime_candle
            )
        except Exception:
            self._worker = None
    
    def __del__(self):
        if hasattr(self, "_worker") and self._worker:
            stop_worker(self._worker)
    
    def closeEvent(self, event):
        if hasattr(self, "_worker") and self._worker:
            stop_worker(self._worker)
        super().closeEvent(event)
    
    # ---------------- Event handlers ----------------
    
    def _on_count_edit_text_changed(self, _text: str):
        """Handle candle count edit text change (debounced)"""
        self._count_edit_debounce_timer.start()
    
    def _on_count_edit_debounced(self):
        """Handle debounced candle count edit"""
        self.data_manager.request_from_count_edit()
    
    def _on_crosshair_moved(self, x: float, y: float):
        """Handle crosshair moved event"""
        if self.ui_state_manager:
            self.ui_state_manager.crosshair_moved(x, y)
    
    def _on_indicator_clicked(self, indicator_name: str):
        """Handle indicator clicked event"""
        log.info(f"[ChartWidget] Indicator clicked: {indicator_name}")
    
    def _on_symbol_changed(self, exchange: str, symbol: str):
        """Handle symbol changed event from UIStateManager"""
        if exchange != "upbit":
            return
        self.set_coin(symbol)
    
    def _on_timeframe_changed(self, timeframe: str):
        """Handle timeframe changed event from UIStateManager"""
        tf_map = {
            'min_1': 'minute1', 'min_3': 'minute3', 'min_5': 'minute5',
            'min_10': 'minute10', 'min_15': 'minute15', 'min_30': 'minute30',
            'min_60': 'minute60', 'min_240': 'minute240',
            'day': 'day', 'week': 'week', 'month': 'month',
        }
        mapped_tf = tf_map.get(timeframe, 'minute1')
        if mapped_tf in self.period_manager.valid_intervals:
            self.period_manager.apply_interval_from_chip(mapped_tf)
    
    def resizeEvent(self, event):
        """Handle widget resize event"""
        super().resizeEvent(event)
        self.period_manager.reflow_chips()
        
        # Update engine badge position
        if hasattr(self.ui_manager, 'engine_badge') and \
           self.ui_manager.engine_badge and \
           self.ui_manager.engine_badge.isVisible():
            w = max(1, self.main_chart.width())
            badge_w = self.ui_manager.engine_badge.sizeHint().width()
            x = max(8, w - badge_w - 12)
            self.ui_manager.engine_badge.move(x, 8)
    
    # ---------------- Public methods ----------------
    
    def set_coin(self, code: str):
        """
        Set trading symbol.
        
        Args:
            code: Symbol code (e.g., "KRW-BTC")
        """
        self._code = code
        if self._worker:
            self._worker.set_symbol_timeframe(code, self.period_manager.applied_interval)
        self.data_manager.request_initial()
    
    def open_multi_chart_dialog(self):
        """Open multi-chart dialog (placeholder)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("멀티차트 (Phase 6 구현 예정)")
        dialog.setMinimumSize(400, 300)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            "멀티차트 레이아웃 (1/2/4분할)\n\n"
            "Phase 6 구현 예정:\n- GridSpec 기반 레이아웃\n- 패널별 독립 데이터\n- 시간축/십자선 동기화",
            dialog
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #6b7280; font-size: 14px;")
        layout.addWidget(label)
        dialog.exec_()
    
    def open_settings_dialog(self):
        """Open chart settings dialog"""
        try:
            from .chart_settings_dialog import ChartSettingsDialog
            dialog = ChartSettingsDialog(self)
            dialog.settings_saved.connect(self._on_settings_saved)
            dialog.exec_()
        except Exception as e:
            log.error(f"[ChartWidget] Settings dialog error: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_settings_saved(self, settings: dict):
        """
        Handle settings saved event.
        
        Args:
            settings: Saved settings dict
        """
        try:
            self.active_indicators = settings.get('indicators', {})
            self.general_settings = settings.get('general', {})
            save_indicators(self.settings, self.active_indicators)
            save_general(self.settings, self.general_settings)

            # Re-create canvas if engine changed
            chosen = None
            if isinstance(self.general_settings, dict):
                chosen = (self.general_settings.get('chart_engine') or
                          self.settings.value("chart_engine", None))
            if chosen:
                self.settings.setValue("chart_engine", chosen)
                self.canvas_manager.destroy_canvas()
                canvas, engine = self.canvas_manager.create_canvas(chosen)
                self._clear_main_chart_layout_widgets()
                self.main_chart_layout.addWidget(canvas)

            # Apply chart type if supported
            if self.canvas_manager.canvas:
                chart_type = self.general_settings.get('chart_type', 'candlestick')
                if hasattr(self.canvas_manager.canvas, 'set_chart_type'):
                    self.canvas_manager.canvas.set_chart_type(chart_type)

            self.data_manager.render_all()

        except Exception as e:
            log.error(f"[ChartWidget] _on_settings_saved error: {e}")
            import traceback
            traceback.print_exc()
    
    def save_chart_snapshot(self):
        """Save chart as image using ExportManager"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"chart_{self._code}_{timestamp}.png"
        
        canvas = self.canvas_manager.canvas
        if not canvas:
            QMessageBox.warning(self, "저장 실패", "차트 캔버스가 없습니다.")
            return
        
        # Use ExportManager for PNG export
        success = ExportManager.export_widget_to_png(canvas, default_filename, scale=2.0)
        
        if success:
            QMessageBox.information(self, "저장 완료", "차트 이미지가 저장되었습니다.")
        else:
            QMessageBox.warning(self, "저장 실패", "차트 이미지 저장에 실패했습니다.")


# End of file