# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: portfolio README v4.0. 폴더명 holdings 최신화.
# 2026-03-13 | Copilot | 업그레이드: portfolio README v2.0. 한국어 전체 템플릿으로 업그레이드.
# 2026-03-06 | Copilot | 생성: portfolio README 초안

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/16_단계_포트폴리오_분석.md
  - work_order/DB설계.md

# src/portfolio — 포트폴리오 관리

## 개요

보유자산 현황, 수익률 분석, 포트폴리오 최적화를 통합한 **포트폴리오 관리 모듈**입니다.
보유 종목의 평단·수익률·파이차트 시각화와 함께, Markowitz·Black-Litterman 기반 포트폴리오 최적화를 제공합니다.

## 디렉토리 구조

```
src/portfolio/
├── __init__.py                    # 모듈 진입점 (PortfolioWidget, UserinfoWidget 재노출)
├── README.md                      # 이 파일
├── holdings/                      # 보유자산 분석 서브모듈
│   ├── __init__.py
│   ├── ui/                        # detailholdinglist.ui, widget_portfolio.py, widget_detail_holding.py
│   ├── logic/                     # 포트폴리오 분석 파사드
│   ├── analysis/                  # 수익률·MDD·Sharpe 분석
│   ├── optimization/              # Markowitz, Black-Litterman, RL 최적화
│   ├── reporting/                 # 일간·주간·PDF 리포트
│   └── workers/                   # 백그라운드 분석 워커
└── userinfo/                      # 사용자 정보 서브모듈
    ├── __init__.py
    ├── ui/                        # userinfo.ui, widget_piechart.py, widget_userinfo.py
    ├── logic/                     # 잔고·평가금액·수익률 계산 로직
    └── workers/                   # 잔고 업데이트 워커
```

## 주요 기능

- **보유자산 현황**: 종목별 평단·평가금액·수익률·수익금 표시
- **파이차트**: 보유자산 비중 시각화 (matplotlib 기반)
- **포트폴리오 분석**: 총 수익률, MDD (Max Drawdown), Sharpe Ratio, 기여도 분석
- **포트폴리오 최적화**: Markowitz 효율적 포트폴리오, Black-Litterman, RL 기반 최적화
- **정기 리포트**: 일간·주간 성과 리포트 생성 (PDF 포함)
- **실시간 업데이트**: 업비트 잔고 API 폴링으로 보유자산 자동 갱신

## 사용 예시

```python
from src._portfolio import PortfolioWidget, UserinfoWidget

# 메인 위젯 생성
portfolio = PortfolioWidget()
userinfo = UserinfoWidget()

portfolio.show()
userinfo.show()

# 포트폴리오 최적화 직접 사용
from src._portfolio.holdings.optimization import MarkowitzOptimizer
optimizer = MarkowitzOptimizer()
weights = optimizer.optimize(returns_df, risk_tolerance=0.5)
print(weights)  # {'KRW-BTC': 0.4, 'KRW-ETH': 0.35, 'KRW-SOL': 0.25}
```

## 의존성

- `src/core/` : 설정 관리, 이벤트 버스
- `src/data_01/timescale/` : OHLCV 데이터 (수익률 계산)
- `src/data_01/mongodb/` : 포트폴리오 스냅샷 저장
- PyQt5 : UI 위젯
- matplotlib : 파이차트, 수익률 차트
- scipy, numpy : 포트폴리오 최적화 계산

## 참고 문서

- [`work_order/16_단계_포트폴리오_분석.md`](../../work_order/16_단계_포트폴리오_분석.md)
- [`work_order/DB설계.md`](../../work_order/DB설계.md) — 포트폴리오 데이터 스키마
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
