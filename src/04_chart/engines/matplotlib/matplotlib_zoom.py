"""
[Purpose]
Matplotlib 차트 줌/패닝 컨트롤러

[Features]
✅ 마우스 휠 줌 (anchor 기준, 1.2배 확대/축소)
✅ 드래그 패닝 (마우스 좌클릭 + 드래그)
✅ 최대 2000개 캔들 제한
✅ 최소 50개 캔들 제한
✅ Prefetch 자동 트리거 (20% 이동 시)
✅ 실시간 업데이트 (draw_idle)
✅ 멀티 패널 동기화 (sharex)

[Responsibilities]
- 마우스 휠 줌 (anchor_time 기준)
- 드래그 패닝 (좌클릭)
- visible_count 관리
- Prefetch 트리거 (20% 이동)
- 차트 업데이트 요청

[Engine Compatibility]
- ✅ matplotlib_chart_engine.py (UnifiedChartEngine) - PRIMARY
- ❌ lightweight_chart_engine.py (uses JavaScript timeScale API)
- ❌ mplfinance_chart_engine.py (uses built-in zoom)
- ❌ plotly_chart_engine.py (uses Plotly zoom API)
- ❌ bokeh_chart_engine.py (uses WheelZoomTool/PanTool)

[Integration]
- matplotlib_chart_engine.py (UnifiedChartEngine)
- widget_chart.py (ChartWidget)

[Reference]
- furechan/mplchart ZoomPan 구현
- anchor 기준 줌 (마우스 위치 유지)
- scale_factor 1.2/0.8 (20% 변화)
- set_xlim/set_ylim 동적 조정

[Author] Phase 2 (mplchart 반영 완료)
[Created] 2026-01-25
[Modified] 2026-02-10 (파일명 변경: zoom_controller.py → matplotlib_zoom.py)
"""

from typing import Optional, Callable, List
import numpy as np
from matplotlib.axes import Axes


class ZoomController:
    """
    Matplotlib 차트 줌/패닝 컨트롤러
    
    Features:
    - 마우스 휠 줌 (anchor 기준, 1.2배)
    - 드래그 패닝 (좌클릭)
    - visible_count 관리 (50~2000)
    - Prefetch 트리거 (20% 이동)
    
    Usage:
        >>> zoom = ZoomController(ax_main, ax_volume)
        >>> zoom.setup_events(canvas)
        >>> zoom.set_data_range(0, 1000)  # 전체 데이터 범위
    """
    
    def __init__(
        self,
        *axes: Axes,
        prefetch_callback: Optional[Callable] = None,
        update_callback: Optional[Callable] = None
    ):
        """
        초기화
        
        Parameters
        ----------
        *axes : matplotlib.axes.Axes
            줌/패닝을 적용할 Axes (메인, 거래량, 지표 등)
        prefetch_callback : Callable, optional
            Prefetch 콜백 (20% 이동 시 호출)
        update_callback : Callable, optional
            차트 업데이트 콜백 (범위 변경 시 호출)
        """
        self.axes: List[Axes] = list(axes)
        self.prefetch_callback = prefetch_callback
        self.update_callback = update_callback
        
        # 줌 설정
        self.visible_count = 200  # 현재 표시 개수
        self.min_visible = 50  # 최소 표시 개수
        self.max_visible = 2000  # 최대 표시 개수
        
        # 데이터 범위
        self.data_start = 0  # 전체 데이터 시작 인덱스
        self.data_end = 0  # 전체 데이터 끝 인덱스
        
        # 표시 범위
        self.view_start = 0  # 현재 표시 시작 인덱스
        self.view_end = 200  # 현재 표시 끝 인덱스
        
        # 패닝 상태
        self.is_panning = False
        self.pan_start_x = None
        self.pan_start_xlim = None
        
        # Prefetch 설정
        self.prefetch_threshold = 0.2  # 20% 이동 시 트리거
        self.last_prefetch_start = 0
        
        # Canvas 참조
        self.canvas = None
    
    def setup_events(self, canvas):
        """
        matplotlib 이벤트 핸들러 설정
        
        Parameters
        ----------
        canvas : matplotlib.backends.backend_qt5agg.FigureCanvasQTAgg
            FigureCanvas 인스턴스
        
        Events:
        - scroll_event: 마우스 휠 (줌)
        - button_press_event: 마우스 버튼 누름 (패닝 시작)
        - button_release_event: 마우스 버튼 떼기 (패닝 종료)
        - motion_notify_event: 마우스 이동 (패닝)
        """
        self.canvas = canvas
        canvas.mpl_connect('scroll_event', self.on_scroll)
        canvas.mpl_connect('button_press_event', self.on_press)
        canvas.mpl_connect('button_release_event', self.on_release)
        canvas.mpl_connect('motion_notify_event', self.on_motion)
    
    def set_data_range(self, start: int, end: int):
        """
        전체 데이터 범위 설정
        
        Parameters
        ----------
        start : int
            시작 인덱스
        end : int
            끝 인덱스 (exclusive)
        """
        self.data_start = start
        self.data_end = end
        
        # 초기 표시 범위 (최신 200개)
        self.view_end = end
        self.view_start = max(start, end - self.visible_count)
    
    def on_scroll(self, event):
        """
        마우스 휠 이벤트 처리 (anchor 기준 줌)
        
        Flow:
        1. anchor 계산 (마우스 X 좌표)
        2. scale_factor 계산 (up=0.8, down=1.2)
        3. visible_count 조정
        4. anchor 기준 범위 재계산
        5. 차트 업데이트
        
        Parameters
        ----------
        event : matplotlib.backend_bases.MouseEvent
            scroll event
        """
        if event.inaxes not in self.axes:
            return
        
        # Anchor 계산 (마우스 위치, 없으면 중앙)
        if event.xdata is not None:
            anchor_x = event.xdata
        else:
            anchor_x = (self.view_start + self.view_end) / 2
        
        # Scale factor (mplchart 스타일)
        scale_factor = 0.8 if event.button == 'up' else 1.2
        
        # 새로운 visible_count
        new_visible = int(self.visible_count * scale_factor)
        new_visible = max(self.min_visible, min(self.max_visible, new_visible))
        
        if new_visible == self.visible_count:
            return
        
        # Anchor 기준 비율 계산
        anchor_ratio = (anchor_x - self.view_start) / max(1, self.view_end - self.view_start)
        
        # 새로운 범위 계산 (anchor 유지)
        self.visible_count = new_visible
        new_start = anchor_x - (new_visible * anchor_ratio)
        new_end = new_start + new_visible
        
        # 범위 제한
        if new_start < self.data_start:
            new_start = self.data_start
            new_end = new_start + new_visible
        
        if new_end > self.data_end:
            new_end = self.data_end
            new_start = max(self.data_start, new_end - new_visible)
        
        self.view_start = new_start
        self.view_end = new_end
        
        # 차트 업데이트
        self._update_chart()
    
    def on_press(self, event):
        """
        마우스 버튼 누름 이벤트 처리 (패닝 시작)
        
        Parameters
        ----------
        event : matplotlib.backend_bases.MouseEvent
            button press event
        """
        if event.button != 1:  # 좌클릭만
            return
        
        if event.inaxes not in self.axes:
            return
        
        self.is_panning = True
        self.pan_start_x = event.xdata
        self.pan_start_xlim = (self.view_start, self.view_end)
    
    def on_release(self, event):
        """
        마우스 버튼 떼기 이벤트 처리 (패닝 종료)
        
        Parameters
        ----------
        event : matplotlib.backend_bases.MouseEvent
            button release event
        """
        if event.button != 1:
            return
        
        self.is_panning = False
        self.pan_start_x = None
        self.pan_start_xlim = None
    
    def on_motion(self, event):
        """
        마우스 이동 이벤트 처리 (드래그 패닝)
        
        Flow:
        1. 이동 거리 계산 (dx)
        2. 범위 이동 (view_start, view_end)
        3. 범위 제한 (data_start, data_end)
        4. Prefetch 체크 (20% 이동)
        5. 차트 업데이트
        
        Parameters
        ----------
        event : matplotlib.backend_bases.MouseEvent
            motion notify event
        """
        if not self.is_panning:
            return
        
        if event.xdata is None or self.pan_start_x is None:
            return
        
        # 이동 거리
        dx = event.xdata - self.pan_start_x
        
        # 새로운 범위 계산
        old_start, old_end = self.pan_start_xlim
        new_start = old_start - dx
        new_end = old_end - dx
        
        # 범위 제한
        if new_start < self.data_start:
            new_start = self.data_start
            new_end = new_start + (old_end - old_start)
        
        if new_end > self.data_end:
            new_end = self.data_end
            new_start = new_end - (old_end - old_start)
        
        self.view_start = new_start
        self.view_end = new_end
        
        # Prefetch 체크 (20% 이동)
        move_distance = abs(self.view_start - self.last_prefetch_start)
        if move_distance > self.visible_count * self.prefetch_threshold:
            self._trigger_prefetch()
        
        # 차트 업데이트
        self._update_chart()
    
    def _update_chart(self):
        """
        차트 업데이트 (xlim 설정 + 콜백)
        
        Flow:
        1. 모든 Axes의 xlim 설정
        2. update_callback 호출
        3. draw_idle() 호출
        """
        # xlim 설정 (모든 패널 동기화)
        for ax in self.axes:
            ax.set_xlim(self.view_start, self.view_end)
        
        # 콜백 호출
        if self.update_callback:
            try:
                self.update_callback(int(self.view_start), int(self.view_end))
            except Exception as e:
                print(f"[ZoomController] Update callback error: {e}")
        
        # 렌더링
        if self.canvas:
            self.canvas.draw_idle()
    
    def _trigger_prefetch(self):
        """
        Prefetch 트리거 (20% 이동 시)
        
        Flow:
        1. last_prefetch_start 업데이트
        2. prefetch_callback 호출
        """
        self.last_prefetch_start = self.view_start
        
        if self.prefetch_callback:
            try:
                self.prefetch_callback()
            except Exception as e:
                print(f"[ZoomController] Prefetch callback error: {e}")
    
    def zoom_in(self):
        """줌 인 (프로그래매틱, 중앙 기준)"""
        new_visible = int(self.visible_count * 0.8)
        new_visible = max(self.min_visible, new_visible)
        
        if new_visible == self.visible_count:
            return
        
        # 중앙 기준 줌
        center = (self.view_start + self.view_end) / 2
        self.visible_count = new_visible
        self.view_start = center - new_visible / 2
        self.view_end = center + new_visible / 2
        
        # 범위 제한
        if self.view_start < self.data_start:
            self.view_start = self.data_start
            self.view_end = self.view_start + new_visible
        
        if self.view_end > self.data_end:
            self.view_end = self.data_end
            self.view_start = self.view_end - new_visible
        
        self._update_chart()
    
    def zoom_out(self):
        """줌 아웃 (프로그래매틱, 중앙 기준)"""
        new_visible = int(self.visible_count * 1.2)
        new_visible = min(self.max_visible, new_visible)
        
        if new_visible == self.visible_count:
            return
        
        # 중앙 기준 줌
        center = (self.view_start + self.view_end) / 2
        self.visible_count = new_visible
        self.view_start = center - new_visible / 2
        self.view_end = center + new_visible / 2
        
        # 범위 제한
        if self.view_start < self.data_start:
            self.view_start = self.data_start
            self.view_end = self.view_start + new_visible
        
        if self.view_end > self.data_end:
            self.view_end = self.data_end
            self.view_start = self.view_end - new_visible
        
        self._update_chart()
    
    def pan_left(self, amount: int = 10):
        """왼쪽 패닝 (과거 방향)"""
        new_start = self.view_start - amount
        new_end = self.view_end - amount
        
        if new_start < self.data_start:
            new_start = self.data_start
            new_end = new_start + (self.view_end - self.view_start)
        
        self.view_start = new_start
        self.view_end = new_end
        
        self._update_chart()
    
    def pan_right(self, amount: int = 10):
        """오른쪽 패닝 (최신 방향)"""
        new_start = self.view_start + amount
        new_end = self.view_end + amount
        
        if new_end > self.data_end:
            new_end = self.data_end
            new_start = new_end - (self.view_end - self.view_start)
        
        self.view_start = new_start
        self.view_end = new_end
        
        self._update_chart()
    
    def reset(self):
        """
        줌/패닝 초기화 (최신 200개 표시)
        
        Flow:
        1. visible_count = 200
        2. view_end = data_end
        3. view_start = data_end - 200
        """
        self.visible_count = 200
        self.view_end = self.data_end
        self.view_start = max(self.data_start, self.data_end - self.visible_count)
        
        self._update_chart()
    
    def fit_to_screen(self):
        """전체 데이터 표시 (범위 제한 내)"""
        total_count = self.data_end - self.data_start
        self.visible_count = min(self.max_visible, total_count)
        self.view_start = self.data_start
        self.view_end = self.view_start + self.visible_count
        
        self._update_chart()
    
    def add_axes(self, *axes: Axes):
        """
        패널 추가 (멀티 패널 지원)
        
        Parameters
        ----------
        *axes : matplotlib.axes.Axes
            추가할 Axes
        """
        for ax in axes:
            if ax not in self.axes:
                self.axes.append(ax)
    
    def remove_axes(self, *axes: Axes):
        """
        패널 제거
        
        Parameters
        ----------
        *axes : matplotlib.axes.Axes
            제거할 Axes
        """
        for ax in axes:
            if ax in self.axes:
                self.axes.remove(ax)