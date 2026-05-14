"""
[Purpose]
Matplotlib 차트 기본 요소 (Primitives) - 차트 타입별 렌더링

[Features]
✅ 캔들스틱 (Candlestick) - 실시간 트레이딩 차트
✅ OHLC 바 (OHLC Bar) - 전통적인 바 차트
✅ 라인 차트 (Line Chart) - 심플한 가격 추세
✅ 영역 차트 (Area Chart) - 누적 영역 표시
✅ 할로우 캔들 (Hollow Candle) - 추세 강조 차트
✅ 하이켄 아시 (Heikin Ashi) - 노이즈 감소 차트

[Responsibilities]
- matplotlib Artist 생성 (Rectangle, Line2D, PolyCollection)
- 차트 타입별 렌더링 로직
- 색상/스타일 적용

[Engine Compatibility]
- ✅ matplotlib_chart_engine.py (UnifiedChartEngine) - PRIMARY
- ❌ lightweight_chart_engine.py (uses JavaScript)
- ❌ mplfinance_chart_engine.py (uses mplfinance library)
- ❌ plotly_chart_engine.py (uses Plotly)
- ❌ bokeh_chart_engine.py (uses Bokeh)

[Reference]
- furechan/mplchart primitives.py
- matplotlib.patches.Rectangle
- matplotlib.lines.Line2D

[Author] Phase 2 (mplchart integration)
[Created] 2026-01-25
[Modified] 2026-02-10 (파일명 변경: chart_primitives.py → matplotlib_primitives.py)
"""

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection


def draw_candlestick(
    ax: Axes,
    x: np.ndarray,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    width: float = 0.6,
    up_color: str = '#ef4444',
    down_color: str = '#3b82f6'
):
    """
    캔들스틱 차트 그리기
    
    가장 일반적인 금융 차트 타입. 각 캔들은 시가/고가/저가/종가를 표현.
    상승(종가 > 시가): 빨간색, 하락(종가 < 시가): 파란색
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x : np.ndarray
        X 좌표 (인덱스)
    opens, highs, lows, closes : np.ndarray
        OHLC 데이터
    width : float, default=0.6
        캔들 몸통 너비
    up_color : str, default='#ef4444'
        상승 색상 (빨강)
    down_color : str, default='#3b82f6'
        하락 색상 (파랑)
    
    Examples
    --------
    >>> draw_candlestick(ax, x, opens, highs, lows, closes)
    """
    for i in range(len(x)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        
        color = up_color if c >= o else down_color
        
        # 꼬리 (High-Low) - 가는 세로선
        ax.plot([x[i], x[i]], [l, h], color=color, linewidth=1, solid_capstyle='round')
        
        # 몸통 (Open-Close) - 채워진 사각형
        height = abs(c - o) or 0.001  # 0 방지
        bottom = min(o, c)
        
        rect = Rectangle(
            (x[i] - width/2, bottom), width, height,
            facecolor=color, edgecolor=color, linewidth=0
        )
        ax.add_patch(rect)


def draw_ohlc_bar(
    ax: Axes,
    x: np.ndarray,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    width: float = 0.3,
    up_color: str = '#ef4444',
    down_color: str = '#3b82f6'
):
    """
    OHLC 바 차트 그리기
    
    전통적인 바 차트. 왼쪽 가로선(시가), 오른쪽 가로선(종가), 세로선(고가-저가)
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x, opens, highs, lows, closes : np.ndarray
        OHLC 데이터
    width : float, default=0.3
        가로선 길이
    up_color, down_color : str
        상승/하락 색상
    
    Examples
    --------
    >>> draw_ohlc_bar(ax, x, opens, highs, lows, closes, width=0.4)
    """
    for i in range(len(x)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        
        color = up_color if c >= o else down_color
        
        # 세로선 (High-Low)
        ax.plot([x[i], x[i]], [l, h], color=color, linewidth=1)
        
        # 왼쪽 가로선 (Open)
        ax.plot([x[i] - width, x[i]], [o, o], color=color, linewidth=1)
        
        # 오른쪽 가로선 (Close)
        ax.plot([x[i], x[i] + width], [c, c], color=color, linewidth=1)


def draw_line(
    ax: Axes,
    x: np.ndarray,
    data: np.ndarray,
    color: str = '#3b82f6',
    linewidth: float = 1.5,
    alpha: float = 1.0
):
    """
    라인 차트 그리기
    
    가장 심플한 차트. 종가 또는 단일 지표를 선으로 표현.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x : np.ndarray
        X 좌표
    data : np.ndarray
        Y 데이터 (종가 등)
    color : str, default='#3b82f6'
        선 색상
    linewidth : float, default=1.5
        선 두께
    alpha : float, default=1.0
        투명도 (0.0 ~ 1.0)
    
    Examples
    --------
    >>> draw_line(ax, x, closes, color='#ef4444', linewidth=2.0)
    """
    ax.plot(x, data, color=color, linewidth=linewidth, alpha=alpha)


def draw_area(
    ax: Axes,
    x: np.ndarray,
    data: np.ndarray,
    color: str = '#3b82f6',
    alpha: float = 0.3
):
    """
    영역 차트 그리기
    
    라인 차트 + 아래 영역 채우기. 누적 효과 시각화에 유용.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x : np.ndarray
        X 좌표
    data : np.ndarray
        Y 데이터
    color : str, default='#3b82f6'
        영역 색상
    alpha : float, default=0.3
        투명도 (0.0 ~ 1.0)
    
    Examples
    --------
    >>> draw_area(ax, x, volumes, color='#22c55e', alpha=0.2)
    """
    ax.fill_between(x, 0, data, color=color, alpha=alpha)
    ax.plot(x, data, color=color, linewidth=1.5, alpha=1.0)


def draw_hollow_candle(
    ax: Axes,
    x: np.ndarray,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    width: float = 0.6,
    up_color: str = '#ef4444',
    down_color: str = '#3b82f6'
):
    """
    할로우 캔들 그리기
    
    상승 캔들은 빈 사각형(테두리만), 하락 캔들은 채워진 사각형.
    추세 전환을 더 명확하게 보여줌.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x, opens, highs, lows, closes : np.ndarray
        OHLC 데이터
    width : float, default=0.6
        캔들 너비
    up_color, down_color : str
        상승/하락 색상
    
    Features
    --------
    - 상승 (종가 >= 시가): 빈 사각형 (facecolor='none')
    - 하락 (종가 < 시가): 채워진 사각형 (facecolor=down_color)
    
    Examples
    --------
    >>> draw_hollow_candle(ax, x, opens, highs, lows, closes)
    """
    for i in range(len(x)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        
        color = up_color if c >= o else down_color
        
        # 꼬리 (High-Low)
        ax.plot([x[i], x[i]], [l, h], color=color, linewidth=1)
        
        # 몸통 (Open-Close)
        height = abs(c - o) or 0.001
        bottom = min(o, c)
        
        # 상승: 빈 사각형, 하락: 채워진 사각형
        facecolor = 'none' if c >= o else color
        edgecolor = color
        
        rect = Rectangle(
            (x[i] - width/2, bottom), width, height,
            facecolor=facecolor, edgecolor=edgecolor, linewidth=1
        )
        ax.add_patch(rect)


def heikin_ashi(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray
):
    """
    하이켄 아시 변환 (Heikin Ashi Transformation)
    
    일본어로 "평균 바"라는 뜻. 노이즈를 줄이고 추세를 더 명확하게 표현.
    
    Parameters
    ----------
    opens, highs, lows, closes : np.ndarray
        원본 OHLC 데이터
    
    Returns
    -------
    tuple of np.ndarray
        (ha_open, ha_high, ha_low, ha_close)
    
    Algorithm
    ---------
    - HA Close = (Open + High + Low + Close) / 4
    - HA Open = (Previous HA Open + Previous HA Close) / 2
    - HA High = max(High, HA Open, HA Close)
    - HA Low = min(Low, HA Open, HA Close)
    
    Examples
    --------
    >>> ha_o, ha_h, ha_l, ha_c = heikin_ashi(opens, highs, lows, closes)
    """
    ha_close = (opens + highs + lows + closes) / 4
    
    ha_open = np.zeros_like(opens)
    ha_open[0] = (opens[0] + closes[0]) / 2
    
    for i in range(1, len(opens)):
        ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
    
    ha_high = np.maximum(highs, np.maximum(ha_open, ha_close))
    ha_low = np.minimum(lows, np.minimum(ha_open, ha_close))
    
    return ha_open, ha_high, ha_low, ha_close


def draw_heikin_ashi(
    ax: Axes,
    x: np.ndarray,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    width: float = 0.6,
    up_color: str = '#ef4444',
    down_color: str = '#3b82f6'
):
    """
    하이켄 아시 차트 그리기
    
    내부적으로 heikin_ashi() 변환 후 캔들스틱 렌더링.
    노이즈가 적고 추세가 명확한 차트.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        그릴 대상 Axes
    x, opens, highs, lows, closes : np.ndarray
        원본 OHLC 데이터
    width : float, default=0.6
        캔들 너비
    up_color, down_color : str
        상승/하락 색상
    
    Examples
    --------
    >>> draw_heikin_ashi(ax, x, opens, highs, lows, closes)
    """
    ha_open, ha_high, ha_low, ha_close = heikin_ashi(opens, highs, lows, closes)
    
    draw_candlestick(ax, x, ha_open, ha_high, ha_low, ha_close, width, up_color, down_color)