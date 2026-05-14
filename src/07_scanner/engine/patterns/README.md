# 패턴 인식 모듈 (scanner/patterns)

## 개요

`patterns/` 패키지는 캔들스틱 패턴과 차트 패턴 감지 함수를 제공합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `candlestick.py` | 캔들 패턴: Doji, Hammer, Shooting Star, Engulfing |
| `chart_patterns.py` | 차트 패턴: Triangle, Double Top/Bottom, Head & Shoulders, Flag |

---

## 사용 예제

### 캔들스틱 패턴
```python
from scanner.patterns import detect_doji, detect_hammer, detect_shooting_star
from scanner.patterns import detect_bullish_engulfing, detect_bearish_engulfing

is_doji = detect_doji(df['open'], df['high'], df['low'], df['close'])
is_hammer = detect_hammer(df['open'], df['high'], df['low'], df['close'])
is_star = detect_shooting_star(df['open'], df['high'], df['low'], df['close'])
is_bull = detect_bullish_engulfing(df['open'], df['close'])
is_bear = detect_bearish_engulfing(df['open'], df['close'])
```

### 차트 패턴
```python
from scanner.patterns import (
    detect_triangle, detect_double_top, detect_double_bottom,
    detect_head_and_shoulders, detect_flag,
)

is_triangle = detect_triangle(df['high'], df['low'], 30)
is_dtop = detect_double_top(df['close'], 50)
is_dbot = detect_double_bottom(df['close'], 50)
is_hs = detect_head_and_shoulders(df['close'], 60)
is_flag = detect_flag(df['close'], 20)
```

---

## 설계 원칙

- **순수 함수**: 상태 없이 입력 → bool/float 반환
- **lookback 파라미터**: 탐색 기간을 조절 가능
- **tolerance 파라미터**: 패턴 허용 오차 조절 가능
