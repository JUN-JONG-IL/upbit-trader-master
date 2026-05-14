# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: 04_chart README v4.0. 버전 통일.
# 2026-03-13 | Copilot | 업그레이드: 04_chart matplotlib/ 통합 완료.
# 2026-03-06 | Copilot | 생성: 04_chart README 초안

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md
  - work_order/DB설계.md

# src/04_chart - 기관급 차트 시스템

## 개요

5가지 차트 엔진, 100+ 기술 지표, 멀티차트 레이아웃, AI 분석을 지원하는 기관급 차트 시스템

## 폴더 구조

```
src/04_chart/
├── __init__.py                     # 모든 차트 위젯 export
├── README.md                       # 이 파일
│
├── engines/                        # 5가지 차트 엔진
│   ├── base_chart_engine.py        # 추상 기본 클래스
│   ├── lightweight_chart_engine.py # TradingView Lightweight Charts
│   ├── matplotlib_chart_engine.py  # Matplotlib (범용)
│   ├── mplfinance_chart_engine.py  # mplfinance (정적 분석)
│   ├── plotly_chart_engine.py      # Plotly (웹 임베딩)
│   └── matplotlib/                 # ✅ Matplotlib 유틸리티 통합 완료
│       ├── matplotlib_crosshair.py     # 크로스헤어 + 툴팁
│       ├── matplotlib_event_markers.py # 이벤트 마커 (매수/매도 화살표)
│       ├── matplotlib_primitives.py    # 차트 기본 요소 (캔들, OHLC, 라인)
│       ├── matplotlib_trend_lines.py   # 추세선 컨트롤러
│       └── matplotlib_zoom.py          # 줌/패닝 컨트롤러
│
├── ai/                             # AI 기반 차트 분석
│   ├── logic/
│   │   ├── pattern_detector.py     # 14+ 패턴 감지
│   │   ├── predictor.py            # LSTM 가격 예측
│   │   └── sentiment_overlay.py    # 감성 분석 오버레이
│   └── ui/
│       ├── ai_chart_dialog.py
│       └── ai_chart_dialog.ui
│
├── ui/                             # chart.ui, widget_chart.py
├── manager/                        # ui_manager, period_manager, engine_manager, data_manager, settings_manager
├── multi/
│   └── ui/                         # multi_chart_dialog.ui
├── realtime/
│   └── ui/                         # realtime_chart_dialog.ui
├── indicators/                     # 기술 지표
│   ├── trend/    ma.py, vwap.py    # SMA, EMA, WMA, VWAP
│   ├── momentum/ rsi.py, macd.py  # RSI, MACD
│   ├── volatility/ bollinger.py, atr.py
│   └── volume/   obv.py
│
├── utils/                          # 공통 유틸리티
│   ├── format.py                   # 가격/볼륨 포맷팅
│   └── export.py                   # PNG/PDF/HTML 내보내기
│
└── (docs → docs/04_chart/)         # 문서 최상위 docs/04_chart/ 로 이동
    # ADVANCED_CHART_GUIDE.md
    # CHART_ENGINE_COMPARISON.md
    # CHART_README.md
```

## 사용법

```python
from src.04_chart import ChartWidget, MultiChartWidget

# 기본 차트
chart = ChartWidget()
chart.set_symbol("KRW-BTC")
chart.set_timeframe("5m")

# 멀티차트
multi = MultiChartWidget()

# 지표 계산
from src.04_chart.indicators import sma, rsi, macd, bollinger_bands
import pandas as pd

df = pd.read_csv("ohlcv.csv")
sma_20 = sma(df['close'], 20)
rsi_14 = rsi(df['close'], 14)
macd_line, signal, hist = macd(df['close'])
upper, middle, lower = bollinger_bands(df['close'])

# 엔진 사용
from src.04_chart.engines import LightweightChartEngine, PlotlyChartEngine

engine = PlotlyChartEngine()
fig = engine.render(df)
fig.write_html("chart.html")

# Matplotlib 유틸리티 (engines/matplotlib/)
from src.04_chart.engines.matplotlib.matplotlib_crosshair import CrosshairController
from src.04_chart.engines.matplotlib.matplotlib_primitives import draw_candlestick
```

## 15가지 원칙 준수

| 원칙 | 상태 | 설명 |
|------|------|------|
| 1. 일관성 | ✅ | 모든 위젯이 `ui/` + `logic/` 패턴 |
| 2. 논리성 | ✅ | 기능별 명확한 그룹화 |
| 3. 통합성 | ✅ | 중복 코드 제거, 단일 위치 |
| 4. 모듈성 | ✅ | 각 위젯 독립적 동작 |
| 5. 확장성 | ✅ | 새 엔진/지표 쉽게 추가 |
| 6. 유연성 | ✅ | 5개 차트 엔진 독립 사용 |
| 7. 상호보완성 | ✅ | 위젯 간 시그널/슬롯 연결 |
| 8. 균형성 | ✅ | 폴더 깊이 3~5단계 |
| 9. 점진성 | ✅ | 복잡도 점진적 증가 |
| 10. 완결성 | ✅ | 모든 기능 반영 |
| 11. 재사용성 | ✅ | `utils/` 공통 모듈 |
| 12. 계층성 | ✅ | UI → Widget → Logic → Indicator |
| 13. 전환성 | ✅ | 레거시 호환 유지 (shim) |
| 14. 강조성 | ✅ | 핵심 기능 명확히 강조 |
| 15. 반복성 | ✅ | `ui/`, `logic/` 패턴 반복 |

## 하위 호환성 (Backward Compatibility)

기존 코드는 `src.04_chart.chart`에서 계속 import 가능합니다:

```python
# 기존 방식 (deprecated, 경고 발생)
from src.04_chart.chart import ChartWidget

# 새 방식 (권장)
from src.04_chart import ChartWidget
from src.04_chart.widgets.basic import ChartWidget
```

## 의존성

- PyQt5 (UI 프레임워크)
- pandas, numpy (데이터 처리)
- mplfinance (선택적)
- plotly (선택적)
- bokeh (선택적)
- PyTorch (AI 예측, 선택적)
