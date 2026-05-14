# 기술적 지표 모듈 (scanner/indicators)

## 개요

`indicators/` 패키지는 종목 스캐너에서 사용하는 모든 기술적 지표 계산 함수를 제공합니다.
TA-Lib 없이도 동작하도록 순수 `pandas`/`numpy` 기반으로 구현하였습니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `trend.py` | 추세 지표: MA, EMA, MACD, 골든크로스/데드크로스 |
| `momentum.py` | 모멘텀 지표: RSI, Stochastic, CCI |
| `volatility.py` | 변동성 지표: Bollinger Bands, ATR |
| `volume.py` | 거래량 지표: OBV, Volume MA, 급등 감지 |

---

## 주요 함수

### 추세 (trend.py)
```python
from scanner.indicators import calc_ma, calc_ema, calc_macd
from scanner.indicators import detect_golden_cross, detect_dead_cross

ma5 = calc_ma(df['close'], 5)
ema20 = calc_ema(df['close'], 20)
macd, signal, hist = calc_macd(df['close'])
is_golden = detect_golden_cross(df['close'], 5, 20)
```

### 모멘텀 (momentum.py)
```python
from scanner.indicators import calc_rsi, calc_stochastic, calc_cci

rsi = calc_rsi(df['close'], 14)
k, d = calc_stochastic(df['high'], df['low'], df['close'])
cci = calc_cci(df['high'], df['low'], df['close'], 20)
```

### 변동성 (volatility.py)
```python
from scanner.indicators import calc_bollinger_bands, calc_atr, detect_bb_squeeze

upper, mid, lower = calc_bollinger_bands(df['close'])
atr = calc_atr(df['high'], df['low'], df['close'])
is_squeeze = detect_bb_squeeze(df['close'])
```

### 거래량 (volume.py)
```python
from scanner.indicators import calc_obv, calc_volume_ma, detect_volume_surge

obv = calc_obv(df['close'], df['volume'])
vol_ma = calc_volume_ma(df['volume'], 20)
is_surge = detect_volume_surge(df['volume'], ratio=3.0)
```

---

## 설계 원칙

- **순수 함수**: 모든 함수는 상태 없이 입력 → 출력만 처리
- **pandas 기반**: `pd.Series` 입출력으로 DataFrame과 자연스럽게 결합
- **타입 힌팅**: 모든 함수에 타입 힌트 적용
- **TA-Lib 독립**: TA-Lib 없이도 동작 (선택적으로 `scanner_rules_extended.py` 에서 TA-Lib 사용)
