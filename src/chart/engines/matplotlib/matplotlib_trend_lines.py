"""
[Purpose]
Matplotlib 트렌드 라인 컨트롤러

[Features]
✅ 트렌드 라인 (직선)
✅ 수평선 (지지/저항)
✅ 피보나치 되돌림 (0%, 23.6%, 38.2%, 50%, 61.8%, 100%)
✅ 드래그로 그리기 (향후 구현 예정)

[Responsibilities]
- 트렌드 라인 생성/삭제
- matplotlib Line2D 관리
- 색상/스타일 설정

[Engine Compatibility]
- ✅ matplotlib_chart_engine.py (UnifiedChartEngine) - PRIMARY
- ❌ lightweight_chart_engine.py (uses JavaScript createTrendLine API)
- ❌ mplfinance_chart_engine.py (uses addplot parameter)
- ❌ plotly_chart_engine.py (uses fig.add_shape)
- ❌ bokeh_chart_engine.py (uses Segment glyph)

[Reference]
- furechan/mplchart trend lines
- matplotlib.lines.Line2D
- matplotlib.axes.Axes.plot()

[Author] Phase 3 (Trend Lines)
[Created] 2026-01-25
[Modified] 2026-02-10 (파일명 변경: trend_lines.py → matplotlib_trend_lines.py)
"""

from typing import List, Optional, Tuple
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


class TrendLine:
    """
    트렌드 라인 (단일 라인)
    
    Attributes:
    - x1, y1: 시작점 좌표
    - x2, y2: 끝점 좌표
    - line_type: 'trend', 'horizontal', 'fibonacci'
    - color: 색상
    - style: 선 스타일 ('-', '--', ':', '-.')
    - linewidth: 선 두께
    - artist: matplotlib Line2D 객체
    - labels: 피보나치 라벨 리스트
    """
    
    def __init__(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        line_type: str = 'trend',
        color: str = '#3b82f6',
        style: str = '-',
        linewidth: float = 1.5
    ):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.line_type = line_type
        self.color = color
        self.style = style
        self.linewidth = linewidth
        
        # matplotlib Artist
        self.artist = None
        self.labels = []  # 피보나치 라벨


class TrendLinesController:
    """
    Matplotlib 트렌드 라인 컨트롤러
    
    Features:
    - 트렌드 라인 (두 점을 연결하는 직선)
    - 수평선 (지지선/저항선)
    - 피보나치 되돌림 (6개 레벨)
    - 라인 관리 (추가/삭제/전체 삭제)
    
    Usage:
        >>> trends = TrendLinesController(ax_main)
        >>> trends.add_trend_line(0, 50000, 100, 51000)
        >>> trends.add_horizontal_line(50500, "저항선")
        >>> trends.add_fibonacci(10, 50000, 50, 52000)
        >>> trends.render()
    """
    
    def __init__(self, ax: Axes):
        """
        초기화
        
        Parameters
        ----------
        ax : matplotlib.axes.Axes
            트렌드 라인을 표시할 Axes
        """
        self.ax = ax
        self.lines: List[TrendLine] = []
    
    def add_trend_line(
        self, 
        x1: float, y1: float, 
        x2: float, y2: float,
        color: str = '#3b82f6',
        style: str = '-'
    ):
        """
        트렌드 라인 추가
        
        Parameters
        ----------
        x1, y1 : float
            시작점 좌표 (X, Y)
        x2, y2 : float
            끝점 좌표 (X, Y)
        color : str, default='#3b82f6'
            선 색상
        style : str, default='-'
            선 스타일 ('-', '--', ':', '-.')
        """
        line = TrendLine(x1, y1, x2, y2, 'trend', color, style)
        self.lines.append(line)
    
    def add_horizontal_line(
        self, 
        y: float, 
        label: str = '',
        color: str = '#6b7280',
        style: str = '--'
    ):
        """
        수평선 추가 (지지선/저항선)
        
        Parameters
        ----------
        y : float
            Y 좌표 (가격)
        label : str, optional
            라벨 텍스트
        color : str, default='#6b7280'
            선 색상
        style : str, default='--'
            선 스타일
        """
        xlim = self.ax.get_xlim()
        line = TrendLine(xlim[0], y, xlim[1], y, 'horizontal', color, style, 1.0)
        self.lines.append(line)
    
    def add_fibonacci(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        color: str = '#8b5cf6'
    ):
        """
        피보나치 되돌림 추가
        
        피보나치 레벨:
        - 0.0% (y1 - 시작점)
        - 23.6%
        - 38.2%
        - 50.0%
        - 61.8%
        - 100.0% (y2 - 끝점)
        
        Parameters
        ----------
        x1, y1 : float
            시작점 좌표 (저점)
        x2, y2 : float
            끝점 좌표 (고점)
        color : str, default='#8b5cf6'
            선 색상 (보라색)
        """
        levels = [0, 0.236, 0.382, 0.5, 0.618, 1.0]
        level_labels = ['0%', '23.6%', '38.2%', '50%', '61.8%', '100%']
        
        for level, label in zip(levels, level_labels):
            y = y1 + (y2 - y1) * level
            line = TrendLine(x1, y, x2, y, 'fibonacci', color, '--', 1.0)
            self.lines.append(line)
    
    def render(self):
        """
        모든 라인 렌더링
        
        Flow:
        1. 기존 Artist 제거
        2. 라인 타입별 렌더링
        3. Artist 저장
        """
        self.clear_artists()
        
        for line in self.lines:
            if line.line_type in ['trend', 'horizontal', 'fibonacci']:
                line.artist = self._render_line(line)
    
    def _render_line(self, line: TrendLine) -> Line2D:
        """
        라인 렌더링
        
        Parameters
        ----------
        line : TrendLine
            렌더링할 트렌드 라인
        
        Returns
        -------
        Line2D
            matplotlib Line2D 객체
        """
        line_obj, = self.ax.plot(
            [line.x1, line.x2],
            [line.y1, line.y2],
            color=line.color,
            linestyle=line.style,
            linewidth=line.linewidth,
            alpha=0.7
        )
        
        return line_obj
    
    def clear_artists(self):
        """모든 Artist 제거 (렌더링된 객체만)"""
        for line in self.lines:
            if line.artist:
                try:
                    line.artist.remove()
                except Exception:
                    pass
                line.artist = None
            
            for label in line.labels:
                try:
                    label.remove()
                except Exception:
                    pass
            line.labels.clear()
    
    def clear_all(self):
        """모든 라인 삭제 (데이터 + Artist)"""
        self.clear_artists()
        self.lines.clear()
    
    def remove_line(self, index: int):
        """
        특정 라인 삭제
        
        Parameters
        ----------
        index : int
            삭제할 라인 인덱스
        """
        if 0 <= index < len(self.lines):
            line = self.lines.pop(index)
            if line.artist:
                try:
                    line.artist.remove()
                except Exception:
                    pass