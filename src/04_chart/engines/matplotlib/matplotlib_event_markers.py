"""
[Purpose]
Matplotlib 이벤트 마커 컨트롤러

[Features]
✅ 매수/매도 화살표 (↑↓)
✅ 텍스트 라벨
✅ 수직선 (이벤트 표시)
✅ 커스텀 마커

[Responsibilities]
- 이벤트 마커 생성/삭제
- matplotlib Artist 관리
- 색상/스타일 설정

[Engine Compatibility]
- ✅ matplotlib_chart_engine.py (UnifiedChartEngine) - PRIMARY
- ❌ lightweight_chart_engine.py (uses JavaScript markers API)
- ❌ mplfinance_chart_engine.py (uses addplot parameter)
- ❌ plotly_chart_engine.py (uses fig.add_annotation)
- ❌ bokeh_chart_engine.py (uses Span/Label widgets)

[Reference]
- furechan/mplchart event markers
- matplotlib.axes.Axes.annotate()
- matplotlib.patches.FancyArrowPatch

[Author] Phase 3 (Event Markers)
[Created] 2026-01-25
[Modified] 2026-02-10 (파일명 변경: event_markers.py → matplotlib_event_markers.py)
"""

from typing import List, Optional, Tuple
from matplotlib.axes import Axes
from matplotlib.patches import FancyArrowPatch
from matplotlib.text import Annotation


class EventMarker:
    """
    이벤트 마커 (단일 마커)
    
    Attributes:
    - x: X 좌표 (인덱스)
    - y: Y 좌표 (가격)
    - marker_type: 'buy', 'sell', 'text', 'vline'
    - text: 표시할 텍스트
    - color: 색상
    - artist: matplotlib Artist (Annotation 또는 Line2D)
    """
    
    def __init__(
        self, 
        x: float, 
        y: float, 
        marker_type: str = 'buy',
        text: str = '',
        color: Optional[str] = None
    ):
        self.x = x
        self.y = y
        self.marker_type = marker_type
        self.text = text
        self.color = color or self._default_color(marker_type)
        
        # matplotlib Artist
        self.artist = None
    
    def _default_color(self, marker_type: str) -> str:
        """기본 색상"""
        if marker_type == 'buy':
            return '#22c55e'  # 녹색
        elif marker_type == 'sell':
            return '#ef4444'  # 빨강
        else:
            return '#3b82f6'  # 파랑


class EventMarkersController:
    """
    Matplotlib 이벤트 마커 컨트롤러
    
    Features:
    - 매수/매도 화살표 (↑↓)
    - 텍스트 라벨
    - 수직선 (이벤트 표시)
    - 마커 관리 (추가/삭제/전체 삭제)
    
    Usage:
        >>> markers = EventMarkersController(ax_main)
        >>> markers.add_buy_marker(10, 50000, "매수")
        >>> markers.add_sell_marker(20, 51000, "매도")
        >>> markers.render()
    """
    
    def __init__(self, ax: Axes):
        """
        초기화
        
        Parameters
        ----------
        ax : matplotlib.axes.Axes
            마커를 표시할 Axes
        """
        self.ax = ax
        self.markers: List[EventMarker] = []
    
    def add_buy_marker(self, x: float, y: float, text: str = ''):
        """
        매수 마커 추가 (↑ 녹색 화살표)
        
        Parameters
        ----------
        x : float
            X 좌표 (캔들 인덱스)
        y : float
            Y 좌표 (가격)
        text : str, optional
            표시할 텍스트 (기본: '▲')
        """
        marker = EventMarker(x, y, 'buy', text)
        self.markers.append(marker)
    
    def add_sell_marker(self, x: float, y: float, text: str = ''):
        """
        매도 마커 추가 (↓ 빨강 화살표)
        
        Parameters
        ----------
        x : float
            X 좌표
        y : float
            Y 좌표
        text : str, optional
            표시할 텍스트 (기본: '▼')
        """
        marker = EventMarker(x, y, 'sell', text)
        self.markers.append(marker)
    
    def add_text_marker(self, x: float, y: float, text: str, color: str = '#3b82f6'):
        """
        텍스트 마커 추가
        
        Parameters
        ----------
        x : float
            X 좌표
        y : float
            Y 좌표
        text : str
            표시할 텍스트
        color : str, default='#3b82f6'
            텍스트 색상
        """
        marker = EventMarker(x, y, 'text', text, color)
        self.markers.append(marker)
    
    def add_vline_marker(self, x: float, text: str = '', color: str = '#6b7280'):
        """
        수직선 마커 추가
        
        Parameters
        ----------
        x : float
            X 좌표
        text : str, optional
            표시할 텍스트 (상단)
        color : str, default='#6b7280'
            선 색상
        """
        marker = EventMarker(x, 0, 'vline', text, color)
        self.markers.append(marker)
    
    def render(self):
        """
        모든 마커 렌더링
        
        Flow:
        1. 기존 Artist 제거
        2. 마커 타입별 렌더링
        3. Artist 저장
        """
        # 기존 Artist 제거
        self.clear_artists()
        
        for marker in self.markers:
            if marker.marker_type == 'buy':
                marker.artist = self._render_buy_arrow(marker)
            elif marker.marker_type == 'sell':
                marker.artist = self._render_sell_arrow(marker)
            elif marker.marker_type == 'text':
                marker.artist = self._render_text(marker)
            elif marker.marker_type == 'vline':
                marker.artist = self._render_vline(marker)
    
    def _render_buy_arrow(self, marker: EventMarker) -> Annotation:
        """
        매수 화살표 렌더링 (↑)
        
        Style:
        - 녹색 화살표 (아래 → 위)
        - 텍스트: 화살표 위
        """
        text = marker.text or '▲'
        
        ann = self.ax.annotate(
            text,
            xy=(marker.x, marker.y),
            xytext=(0, -30),  # 30px 아래
            textcoords='offset points',
            ha='center', va='top',
            fontsize=10,
            color=marker.color,
            fontweight='bold',
            bbox=dict(
                boxstyle='round,pad=0.3',
                facecolor='white',
                edgecolor=marker.color,
                linewidth=2,
                alpha=0.9
            ),
            arrowprops=dict(
                arrowstyle='->',
                color=marker.color,
                lw=2,
                shrinkA=0,
                shrinkB=5
            )
        )
        
        return ann
    
    def _render_sell_arrow(self, marker: EventMarker) -> Annotation:
        """
        매도 화살표 렌더링 (↓)
        
        Style:
        - 빨강 화살표 (위 → 아래)
        - 텍스트: 화살표 아래
        """
        text = marker.text or '▼'
        
        ann = self.ax.annotate(
            text,
            xy=(marker.x, marker.y),
            xytext=(0, 30),  # 30px 위
            textcoords='offset points',
            ha='center', va='bottom',
            fontsize=10,
            color=marker.color,
            fontweight='bold',
            bbox=dict(
                boxstyle='round,pad=0.3',
                facecolor='white',
                edgecolor=marker.color,
                linewidth=2,
                alpha=0.9
            ),
            arrowprops=dict(
                arrowstyle='->',
                color=marker.color,
                lw=2,
                shrinkA=0,
                shrinkB=5
            )
        )
        
        return ann
    
    def _render_text(self, marker: EventMarker) -> Annotation:
        """텍스트 마커 렌더링"""
        ann = self.ax.annotate(
            marker.text,
            xy=(marker.x, marker.y),
            xytext=(0, 0),
            ha='center', va='center',
            fontsize=9,
            color=marker.color,
            fontweight='bold',
            bbox=dict(
                boxstyle='round,pad=0.4',
                facecolor='white',
                edgecolor=marker.color,
                linewidth=1.5,
                alpha=0.9
            )
        )
        
        return ann
    
    def _render_vline(self, marker: EventMarker):
        """수직선 마커 렌더링"""
        line = self.ax.axvline(
            marker.x,
            color=marker.color,
            linestyle='--',
            linewidth=1.5,
            alpha=0.7
        )
        
        # 텍스트 (상단)
        if marker.text:
            ylim = self.ax.get_ylim()
            y_pos = ylim[1] - (ylim[1] - ylim[0]) * 0.05
            
            self.ax.text(
                marker.x, y_pos,
                marker.text,
                ha='center', va='top',
                fontsize=8,
                color=marker.color,
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='white',
                    edgecolor=marker.color,
                    alpha=0.8
                )
            )
        
        return line
    
    def clear_artists(self):
        """모든 Artist 제거 (렌더링된 객체만)"""
        for marker in self.markers:
            if marker.artist:
                try:
                    marker.artist.remove()
                except Exception:
                    pass
                marker.artist = None
    
    def clear_all(self):
        """모든 마커 삭제 (데이터 + Artist)"""
        self.clear_artists()
        self.markers.clear()
    
    def remove_marker(self, index: int):
        """
        특정 마커 삭제
        
        Parameters
        ----------
        index : int
            삭제할 마커 인덱스
        """
        if 0 <= index < len(self.markers):
            marker = self.markers.pop(index)
            if marker.artist:
                try:
                    marker.artist.remove()
                except Exception:
                    pass