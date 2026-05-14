"""
[Purpose]
Matplotlib 차트 십자선(Crosshair) + Tooltip 컨트롤러

[Features]
✅ 마우스 추적 십자선 (세로선/가로선)
✅ 시간/가격 라벨 (배경 박스)
✅ Tooltip (OHLCV 정보 표시)
✅ Throttle 16~33ms (30~60fps)
✅ Blit 렌더링 지원
✅ 멀티 패널 지원

[Tooltip Format]
O: 50,000 H: 51,000 L: 49,000 C: 50,500 V: 123.45

[Engine Compatibility]
- ✅ matplotlib_chart_engine.py (UnifiedChartEngine) - PRIMARY
- ❌ lightweight_chart_engine.py (uses JavaScript crosshair)
- ❌ mplfinance_chart_engine.py (uses built-in crosshair)
- ❌ plotly_chart_engine.py (uses Plotly API)
- ❌ bokeh_chart_engine.py (uses CrosshairTool)

[Author] Phase 3 (Tooltip 추가 완료)
[Created] 2026-01-25
[Modified] 2026-02-10 (파일명 변경: crosshair_controller.py → matplotlib_crosshair.py)
"""

import time
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any

from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.axes import Axes


class CrosshairController:
    """
    Matplotlib 차트 십자선 + Tooltip 컨트롤러
    
    Features:
    - 세로선/가로선 (axvline/axhline)
    - 시간/가격 라벨 (배경 박스)
    - Tooltip (OHLCV 정보)
    - Throttle 16~33ms (성능 최적화)
    - 멀티 패널 지원
    
    Usage:
        >>> crosshair = CrosshairController(ax_main, ax_volume)
        >>> crosshair.set_candle_data(candles)  # 캔들 데이터 설정
        >>> crosshair.setup_events(canvas)
        >>> crosshair.enable()
    """
    
    def __init__(
        self, 
        *axes: Axes,
        format_time_callback: Optional[Callable[[float], str]] = None,
        format_price_callback: Optional[Callable[[float], str]] = None,
        throttle_ms: int = 16
    ):
        """
        초기화
        
        Parameters
        ----------
        *axes : matplotlib.axes.Axes
            십자선을 표시할 Axes (멀티 패널 지원)
        format_time_callback : Callable[[float], str], optional
            시간 포맷 콜백 함수
        format_price_callback : Callable[[float], str], optional
            가격 포맷 콜백 함수
        throttle_ms : int, default=16
            업데이트 throttle 간격 (16ms = 60fps)
        """
        self.axes: List[Axes] = list(axes)
        self.format_time = format_time_callback
        self.format_price = format_price_callback
        
        # Throttle
        self.throttle_ms = throttle_ms
        self.last_update_ts = 0.0
        
        # 십자선 요소
        self.vlines: List[Line2D] = []
        self.hlines: List[Line2D] = []
        self.time_label: Optional[Text] = None
        self.price_label: Optional[Text] = None
        self.tooltip_label: Optional[Text] = None
        
        # 상태
        self.visible = False
        self.enabled = False
        
        # Canvas
        self.canvas = None
        
        # 캔들 데이터 (Tooltip용)
        self.candle_data: List[Dict[str, Any]] = []
        self.data_start_index = 0  # Zoom 시작 인덱스
    
    def set_candle_data(self, candles: List[Dict[str, Any]], start_index: int = 0):
        """
        캔들 데이터 설정 (Tooltip용)
        
        Parameters
        ----------
        candles : List[Dict[str, Any]]
            캔들 데이터 리스트 (키: 'o', 'h', 'l', 'c', 'v')
        start_index : int, default=0
            데이터 시작 인덱스 (Zoom용)
        """
        self.candle_data = candles
        self.data_start_index = start_index
    
    def setup_events(self, canvas):
        """matplotlib 이벤트 핸들러 설정"""
        self.canvas = canvas
        canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        canvas.mpl_connect('axes_leave_event', self.on_mouse_leave)
    
    def on_mouse_move(self, event):
        """마우스 이동 이벤트 (throttle 적용)"""
        if not self.enabled:
            return
        
        # Throttle
        now = time.time()
        if (now - self.last_update_ts) < (self.throttle_ms / 1000.0):
            return
        self.last_update_ts = now
        
        # 차트 영역 체크
        if event.inaxes not in self.axes:
            self._hide()
            return
        
        # 좌표 유효성
        if event.xdata is None or event.ydata is None:
            self._hide()
            return
        
        # 십자선 + Tooltip 표시
        self._show(event.xdata, event.ydata, event.inaxes)
    
    def on_mouse_leave(self, event):
        """마우스 차트 영역 벗어남"""
        self._hide()
    
    def _show(self, x: float, y: float, current_ax: Axes):
        """
        십자선 + Tooltip 표시
        
        Flow:
        1. 세로선 (모든 패널)
        2. 가로선 (현재 패널)
        3. 시간/가격 라벨
        4. Tooltip (OHLCV 정보)
        5. draw_idle()
        """
        # 1. 세로선 (모든 패널)
        while len(self.vlines) < len(self.axes):
            self.vlines.append(None)
        
        for i, ax in enumerate(self.axes):
            if self.vlines[i] is None:
                self.vlines[i] = ax.axvline(
                    x, color='#6b7280', linestyle='--', 
                    linewidth=0.8, alpha=0.6, visible=True
                )
            else:
                self.vlines[i].set_xdata([x])
                self.vlines[i].set_visible(True)
        
        # 2. 가로선 (현재 패널만)
        while len(self.hlines) < len(self.axes):
            self.hlines.append(None)
        
        for i, ax in enumerate(self.axes):
            if ax == current_ax:
                if self.hlines[i] is None:
                    self.hlines[i] = ax.axhline(
                        y, color='#6b7280', linestyle='--', 
                        linewidth=0.8, alpha=0.6, visible=True
                    )
                else:
                    self.hlines[i].set_ydata([y])
                    self.hlines[i].set_visible(True)
            else:
                if self.hlines[i] is not None:
                    self.hlines[i].set_visible(False)
        
        # 3. 라벨 업데이트
        self._update_labels(x, y, current_ax)
        
        # 4. Tooltip 업데이트
        self._update_tooltip(x, current_ax)
        
        self.visible = True
        
        # 5. 렌더링
        if self.canvas:
            self.canvas.draw_idle()
    
    def _hide(self):
        """십자선 + Tooltip 숨기기"""
        if not self.visible:
            return
        
        # 세로선 숨김
        for vline in self.vlines:
            if vline is not None:
                vline.set_visible(False)
        
        # 가로선 숨김
        for hline in self.hlines:
            if hline is not None:
                hline.set_visible(False)
        
        # 라벨 숨김
        if self.time_label:
            self.time_label.set_visible(False)
        
        if self.price_label:
            self.price_label.set_visible(False)
        
        # Tooltip 숨김
        if self.tooltip_label:
            self.tooltip_label.set_visible(False)
        
        self.visible = False
        
        # 렌더링
        if self.canvas:
            self.canvas.draw_idle()
    
    def _update_labels(self, x: float, y: float, ax: Axes):
        """시간/가격 라벨 업데이트"""
        # 시간 라벨 (X축 하단)
        time_str = self._format_time_value(x)
        
        if self.time_label is None:
            self.time_label = ax.text(
                0.5, -0.05, time_str,
                transform=ax.transAxes,
                ha='center', va='top',
                fontsize=8, color='#1f2937',
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='#fef3c7',
                    edgecolor='#d1d5db',
                    alpha=0.8
                )
            )
        else:
            self.time_label.set_text(time_str)
            self.time_label.set_visible(True)
        
        # 가격 라벨 (Y축 우측)
        price_str = self._format_price_value(y)
        
        if self.price_label is None:
            self.price_label = ax.text(
                1.01, 0.5, price_str,
                transform=ax.get_yaxis_transform(),
                ha='left', va='center',
                fontsize=8, color='#1f2937',
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='#fef3c7',
                    edgecolor='#d1d5db',
                    alpha=0.8
                )
            )
        else:
            self.price_label.set_position((1.01, y))
            self.price_label.set_text(price_str)
            self.price_label.set_visible(True)
    
    def _update_tooltip(self, x: float, ax: Axes):
        """
        Tooltip 업데이트 (OHLCV 정보)
        
        Flow:
        1. X 좌표 → 캔들 인덱스 변환
        2. 캔들 데이터 추출 (OHLCV)
        3. 포맷 문자열 생성
        4. Text Artist 업데이트
        
        Format:
            O: 50,000 H: 51,000 L: 49,000 C: 50,500 V: 123.45
        """
        # X 좌표 → 캔들 인덱스
        candle_idx = int(round(x)) - self.data_start_index
        
        # 범위 체크
        if candle_idx < 0 or candle_idx >= len(self.candle_data):
            if self.tooltip_label:
                self.tooltip_label.set_visible(False)
            return
        
        # 캔들 데이터 추출
        candle = self.candle_data[candle_idx]
        
        # OHLCV 포맷
        o = candle.get('o', 0)
        h = candle.get('h', 0)
        l = candle.get('l', 0)
        c = candle.get('c', 0)
        v = candle.get('v', 0)
        
        # 포맷 문자열 생성
        tooltip_str = (
            f"O: {self._format_price_value(o)}  "
            f"H: {self._format_price_value(h)}  "
            f"L: {self._format_price_value(l)}  "
            f"C: {self._format_price_value(c)}  "
            f"V: {v:,.2f}"
        )
        
        # Tooltip 라벨 생성/업데이트
        if self.tooltip_label is None:
            # 좌상단에 표시 (mplchart 스타일)
            self.tooltip_label = ax.text(
                0.02, 0.98, tooltip_str,
                transform=ax.transAxes,
                ha='left', va='top',
                fontsize=9, color='#1f2937',
                family='monospace',  # 고정폭 폰트
                bbox=dict(
                    boxstyle='round,pad=0.5',
                    facecolor='#fef3c7',
                    edgecolor='#d1d5db',
                    alpha=0.9
                )
            )
        else:
            self.tooltip_label.set_text(tooltip_str)
            self.tooltip_label.set_visible(True)
    
    def _format_time_value(self, x: float) -> str:
        """시간 포맷"""
        if self.format_time:
            try:
                return self.format_time(x)
            except Exception as e:
                print(f"[CrosshairController] format_time error: {e}")
        
        return f"{int(x)}"
    
    def _format_price_value(self, y: float) -> str:
        """가격 포맷"""
        if self.format_price:
            try:
                return self.format_price(y)
            except Exception as e:
                print(f"[CrosshairController] format_price error: {e}")
        
        # 기본 포맷
        if y >= 1_000_000:
            return f'{int(y):,}'
        elif y >= 100:
            return f'{y:,.1f}'
        elif y >= 1:
            return f'{y:,.2f}'
        else:
            return f'{y:,.4f}'
    
    def enable(self):
        """십자선 활성화"""
        self.enabled = True
    
    def disable(self):
        """십자선 비활성화"""
        self.enabled = False
        self._hide()
    
    def clear(self):
        """십자선 완전 제거"""
        # 세로선 제거
        for vline in self.vlines:
            if vline is not None:
                try:
                    vline.remove()
                except Exception:
                    pass
        self.vlines.clear()
        
        # 가로선 제거
        for hline in self.hlines:
            if hline is not None:
                try:
                    hline.remove()
                except Exception:
                    pass
        self.hlines.clear()
        
        # 라벨 제거
        if self.time_label:
            try:
                self.time_label.remove()
            except Exception:
                pass
            self.time_label = None
        
        if self.price_label:
            try:
                self.price_label.remove()
            except Exception:
                pass
            self.price_label = None
        
        # Tooltip 제거
        if self.tooltip_label:
            try:
                self.tooltip_label.remove()
            except Exception:
                pass
            self.tooltip_label = None
        
        self.visible = False
    
    def add_axes(self, *axes: Axes):
        """패널 추가"""
        for ax in axes:
            if ax not in self.axes:
                self.axes.append(ax)
    
    def remove_axes(self, *axes: Axes):
        """패널 제거"""
        for ax in axes:
            if ax in self.axes:
                idx = self.axes.index(ax)
                self.axes.remove(ax)
                
                if idx < len(self.vlines) and self.vlines[idx]:
                    try:
                        self.vlines[idx].remove()
                    except Exception:
                        pass
                    self.vlines[idx] = None
                
                if idx < len(self.hlines) and self.hlines[idx]:
                    try:
                        self.hlines[idx].remove()
                    except Exception:
                        pass
                    self.hlines[idx] = None