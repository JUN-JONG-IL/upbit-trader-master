"""
Data Manager - Handle data fetching, processing, and rendering

Responsibilities:
- Request candle data (initial and incremental)
- Process fetched data and realtime updates
- Render data to canvas
- Manage render throttling
- Add test markers (optional)

Version: v1.0
Created: 2026-02-10 | Copilot
"""

import time
import traceback
from typing import Dict, Any, List

from ..workers.candle_worker import CandleRequest

import logging
log = logging.getLogger(__name__)


class DataManager:
    """Manages data fetching and rendering for ChartWidget"""
    
    def __init__(self, parent):
        """
        Initialize data manager.
        
        Args:
            parent: ChartWidget instance
        """
        self.parent = parent
        self._last_render_ts = 0.0
        self._render_throttle_sec = 0.5
        self._test_markers_added = False
    
    def request_initial(self):
        """Request initial candle data"""
        count = self._safe_int(
            self.parent.candle_count_edit.text() 
            if self.parent.candle_count_edit else None,
            200
        )
        req = self._make_request_from_ui(count)
        if self.parent._worker:
            self.parent._last_requested_id = self.parent._worker.request_fetch(req)
        else:
            self.parent._last_requested_id = 0
    
    def request_from_count_edit(self):
        """Request data when count edit changes (debounced)"""
        count = self._safe_int(
            self.parent.candle_count_edit.text() 
            if self.parent.candle_count_edit else None,
            200
        )
        req = self._make_request_from_ui(count)
        if self.parent._worker:
            self.parent._last_requested_id = self.parent._worker.request_fetch(req)
    
    def on_data_fetched(self, payload: dict):
        """
        Handle fetched candle data.
        
        Args:
            payload: Data payload from worker
        """
        try:
            req: CandleRequest = payload["req"]
            df = payload["df"]
            request_id: int = int(payload.get("request_id", 0))
            
            if request_id != self.parent._last_requested_id:
                return
            
            if df is None or df.empty:
                return
            
            self.parent._candle_data = []
            last_idx = None
            
            for idx, row in df.iterrows():
                last_idx = idx
                self.parent._candle_data.append({
                    'o': float(row['open']),
                    'h': float(row['high']),
                    'l': float(row['low']),
                    'c': float(row['close']),
                    'v': float(row.get('volume', 0)),
                    'is_closed': True,
                    'indicators': {}
                })
            
            if last_idx is not None:
                self.parent._last_candle_timestamp = last_idx
            
            self.render_all()
            
        except Exception as e:
            log.error(f"[DataManager] on_data_fetched error: {e}")
            traceback.print_exc()
    
    def on_realtime_candle(self, candle: dict):
        """
        Handle realtime candle update.
        
        Args:
            candle: Realtime candle data
        """
        try:
            is_closed = candle.get('is_closed', False)
            if not self.parent._candle_data:
                return
            
            if is_closed:
                # New candle
                self.parent._candle_data.append({
                    'o': candle['o'],
                    'h': candle['h'],
                    'l': candle['l'],
                    'c': candle['c'],
                    'v': candle.get('v', 0),
                    'is_closed': True,
                    'indicators': candle.get('indicators', {})
                })
            else:
                # Update last candle
                last = self.parent._candle_data[-1]
                updated = {
                    'o': last['o'],
                    'h': max(last['h'], candle['h']),
                    'l': min(last['l'], candle['l']),
                    'c': candle['c'],
                    'v': candle.get('v', 0),
                    'is_closed': False,
                    'indicators': candle.get('indicators', {})
                }
                self.parent._candle_data[-1] = updated
            
            # Update canvas if possible
            canvas = self.parent.canvas_manager.canvas
            if canvas:
                if hasattr(canvas, 'update_last_candle'):
                    canvas.update_last_candle(self.parent._candle_data[-1])
                else:
                    canvas.update_data(self.parent._candle_data[-10:])
                    
        except Exception as e:
            log.error(f"[DataManager] on_realtime_candle error: {e}")
            traceback.print_exc()
    
    def render_all(self):
        """Render all candle data to canvas with throttling"""
        now = time.time()
        if (now - self._last_render_ts) < self._render_throttle_sec:
            return
        
        if not self.parent._candle_data:
            return
        
        self._last_render_ts = now
        
        try:
            canvas = self.parent.canvas_manager.canvas
            if not canvas:
                return
            
            # Set active indicators
            if hasattr(canvas, 'set_active_indicators'):
                canvas.set_active_indicators(self.parent.active_indicators)
            
            # Update data
            if hasattr(canvas, 'update_data'):
                canvas.update_data(self.parent._candle_data)
            elif hasattr(canvas, 'set'):
                canvas.set(self.parent._candle_data)
            else:
                log.warning("[DataManager] canvas has no update_data/set method")
            
            # Add test markers (once)
            if not self._test_markers_added:
                self._add_test_markers()
                self._test_markers_added = True
                
        except Exception as e:
            log.error(f"[DataManager] render_all engine update error: {e}")
            traceback.print_exc()
    
    def _add_test_markers(self):
        """Add test markers to chart (buy/sell/trend lines)"""
        if not self.parent._candle_data or len(self.parent._candle_data) < 50:
            return
        
        try:
            canvas = self.parent.canvas_manager.canvas
            
            # Buy marker
            if len(self.parent._candle_data) > 10 and hasattr(canvas, 'add_buy_marker'):
                buy_candle = self.parent._candle_data[10]
                canvas.add_buy_marker(10, buy_candle['l'], "매수")
            
            # Sell marker
            if len(self.parent._candle_data) > 30 and hasattr(canvas, 'add_sell_marker'):
                sell_candle = self.parent._candle_data[30]
                canvas.add_sell_marker(30, sell_candle['h'], "매도")
            
            # Trend line
            if len(self.parent._candle_data) > 50 and hasattr(canvas, 'add_trend_line'):
                start_candle = self.parent._candle_data[0]
                mid_candle = self.parent._candle_data[50]
                canvas.add_trend_line(0, start_candle['c'], 50, mid_candle['c'])
            
            # Horizontal line (average price)
            if hasattr(canvas, 'add_horizontal_line'):
                avg_price = sum(c['c'] for c in self.parent._candle_data[-20:]) / 20
                canvas.add_horizontal_line(avg_price, "평균가")
            
            log.info("[DataManager] Test markers added")
            
        except Exception as e:
            log.error(f"[DataManager] Test markers error: {e}")
            traceback.print_exc()
    
    def _safe_int(self, text: str, default: int) -> int:
        """
        Safely convert text to int.
        
        Args:
            text: Text to convert
            default: Default value if conversion fails
            
        Returns:
            Converted int or default
        """
        try:
            v = int((text or "").strip())
            return v if v > 0 else default
        except Exception:
            return default
    
    def _make_request_from_ui(self, count: int) -> CandleRequest:
        """
        Create candle request from UI state.
        
        Args:
            count: Number of candles to request
            
        Returns:
            CandleRequest object
        """
        interval = self.parent.period_manager.applied_interval \
                   if hasattr(self.parent, 'period_manager') \
                   else self.parent.applied_interval
        
        return CandleRequest(self.parent._code, interval, count, None)