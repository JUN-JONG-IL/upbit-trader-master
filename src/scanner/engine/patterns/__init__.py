"""
[Purpose]
- scanner/patterns 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- 캔들스틱 패턴 및 차트 패턴 함수를 외부에서 쉽게 import할 수 있도록 재노출한다.

[Dependencies]
- .candlestick (Doji, Hammer, Shooting Star, Engulfing)
- .chart_patterns (Golden Cross pattern, Triangle, Head & Shoulders)

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from .candlestick import (
    detect_doji,
    detect_hammer,
    detect_shooting_star,
    detect_bullish_engulfing,
    detect_bearish_engulfing,
)
from .chart_patterns import (
    detect_triangle,
    detect_double_top,
    detect_double_bottom,
    detect_head_and_shoulders,
    detect_flag,
)

__all__ = [
    # Candlestick patterns
    'detect_doji',
    'detect_hammer',
    'detect_shooting_star',
    'detect_bullish_engulfing',
    'detect_bearish_engulfing',
    # Chart patterns
    'detect_triangle',
    'detect_double_top',
    'detect_double_bottom',
    'detect_head_and_shoulders',
    'detect_flag',
]
