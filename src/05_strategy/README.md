# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: 05_strategy README v4.0. 버전 통일.
# 2026-03-13 | Copilot | 업그레이드: 05_strategy README v2.0. 전체 템플릿(개요/구조/기능/예시/의존성/참고) 추가.
# 2026-03-06 | Copilot | 생성: 05_strategy README 초안

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md
  - work_order/DB설계.md

# src/05_strategy — 트레이딩 전략 시스템

## 개요

기관 에이전트급 자동매매를 위한 **전략 프레임워크** 모듈입니다.
시그널 관리, 다양한 전략 구현(변동성돌파·추세추종·DCA·그리드·차익거래), 백테스팅, 파라미터 최적화, 리스크 관리를 통합하여 PAPER/LIVE 모드에서 운영합니다.

## 디렉토리 구조

```
src/05_strategy/
├── __init__.py                    # 모듈 진입점 (주요 클래스 재노출)
├── README.md                      # 이 파일
├── core/                          # 전략 인프라
│   ├── __init__.py
│   ├── signal_manager.py          # 시그널 수집·배분·이벤트 발행
│   ├── base_strategy.py           # 추상 기본 전략 클래스
│   └── strategy_registry.py      # 전략 등록/조회 레지스트리
├── strategies/                    # 실제 전략 구현체
│   ├── __init__.py
│   ├── volatility_breakout.py     # 변동성 돌파 전략
│   ├── trend_following.py         # 추세 추종 전략
│   ├── mean_reversion.py          # 평균 회귀 전략
│   ├── dca_strategy.py            # DCA (Dollar Cost Averaging)
│   ├── grid_strategy.py           # 그리드 전략
│   └── arbitrage_strategy.py     # 차익거래 전략
├── widgets/                       # 전략 관리 UI
│   ├── __init__.py
│   ├── backtest/                  # 백테스팅 UI
│   │   ├── __init__.py
│   │   └── ui/
│   └── parameter_optimizer/       # 파라미터 최적화 UI
│       ├── __init__.py
│       └── ui/
├── risk/                          # 리스크 관리
│   ├── __init__.py
│   ├── position_sizer.py          # 포지션 크기 결정
│   ├── stop_loss.py               # 손절매 관리
│   └── portfolio_risk.py         # 포트폴리오 리스크
└── utils/                         # 공통 유틸리티
    ├── __init__.py
    ├── technical_indicators.py    # 기술 지표 헬퍼
    └── strategy_validator.py     # 전략 유효성 검증
```

## 주요 기능

- **전략 레지스트리**: `StrategyRegistry`로 전략을 동적으로 등록·조회·실행
- **시그널 관리**: `SignalManager`로 다중 전략의 시그널을 수집하고 이벤트 버스에 발행
- **백테스팅 엔진**: 과거 데이터로 전략 성능 평가 (수익률, MDD, 샤프 지수)
- **파라미터 최적화**: Grid Search / Bayesian Optimization 기반 파라미터 튜닝
- **리스크 관리**: 포지션 크기 조정, 손절매, 포트폴리오 수준 리스크 제어
- **전략 구현체**: 변동성돌파, 추세추종, 평균회귀, DCA, 그리드, 차익거래

## 사용 예시

```python
from src._05_strategy import SignalManager, VolatilityBreakoutStrategy

# 시그널 매니저 초기화
manager = SignalManager(config, db_ip, db_port, db_id, db_password, queue)
manager.register("volatility_breakout", VolatilityBreakoutStrategy(queue))
manager.start()

# 전략 직접 실행
strategy = VolatilityBreakoutStrategy(queue)
signal = strategy.generate_signal("KRW-BTC", candle_data)
print(signal)  # Signal(action='BUY', price=50000000, confidence=0.85)
```

## 의존성

- `src/01_core/` : 설정 관리, 이벤트 버스, 기본 인프라
- `src/data_01/` : TimescaleDB (OHLCV 데이터), Redis (시그널 캐시)
- `src/04_chart/indicators/` : 기술 지표 (MA, RSI, MACD 등)
- `src/13_compute/` : 지표 계산 엔진 (O(1) 증분 계산)
- PyQt5 : UI 위젯
- pandas, numpy : 데이터 처리

## 참고 문서

- [`work_order/6_단계_PAPER_모드_구현.md`](../../work_order/6_단계_PAPER_모드_구현.md)
- [`work_order/7_단계_LIVE_모드_구현.md`](../../work_order/7_단계_LIVE_모드_구현.md)
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
