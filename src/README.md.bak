# CHANGELOG
# 2026-03-15 | Copilot | 업그레이드: src/README.md v4.0. 폴더명 명확화 및 구조 최적화.
# 2026-03-13 | Copilot | 업그레이드: src/README.md v3.0. 프로젝트 개요, 15가지 설계 원칙, 시작 가이드, 기여 가이드, 전체 디렉토리 구조 추가.
# 2026-03-13 | Copilot | 업데이트: src/README.md 갱신. 01~13번 모듈 구조로 변경. backup UI/위젯 파일 통합 반영.
# 2026-01-31 | Copilot | 생성: src/README.md 작성. 영향: src 폴더 문서화.
Current Stage: N/A
Version: v4.0
Last Modified: 2026-03-15
References:
  - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md
  - work_order/DB설계.md

# Upbit Trader — 기관 에이전트급 트레이딩 시스템

## 프로젝트 개요

Upbit Trader는 **기관·에이전트급 수준의 암호화폐 자동 트레이딩 플랫폼**입니다.
틱/초/분/일/주/월/년 단위 시계열 데이터를 실시간으로 수집·저장하고, 멀티차트·호가창·스캐너·AI/ML 예측·자동매매까지 통합한 풀스택 데스크톱 + 서버 솔루션입니다.

### 주요 기능

| 영역 | 기능 |
|------|------|
| **AI/ML** | LSTM·XGBoost·Transformer 예측, PPO 강화학습, VAE 이상탐지, 앙상블 |
| **스캐너** | 237개+ 종목 실시간 스캔, 기술 지표·패턴·볼륨 조건 검색, 프리셋 관리 |
| **차트** | 5개 엔진(matplotlib/mplfinance/plotly/lightweight/bokeh), 100+ 지표, 멀티차트 |
| **포트폴리오** | 보유자산 현황, 파이차트, 수익률 분석, 포트폴리오 최적화 |
| **트레이드** | 지정가·시장가·조건부 주문, 리스크 관리, 자동매매(PAPER/LIVE) |
| **데이터** | TimescaleDB(시계열), Redis(캐시), MongoDB(메타), Kafka(스트리밍), ClickHouse(분석) |
| **서버** | FastAPI REST + WebSocket, 실시간 데이터 스트리밍, 설정 UI |
| **감성분석** | 뉴스·소셜(트위터/Reddit) 감성, FinBERT/KoBERT 기반 신호 생성 |

> **참고**: `work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md` 및 `work_order/DB설계.md` v8/v9 기준으로 설계되었습니다.

## 디렉토리 구조 (v4.0 — 번호 모듈 기반)

```
src/
├── __init__.py
├── README.md                   # 이 파일
│
├── 01_core/                    # 핵심 인프라 (인증, DI, 설정, 이벤트)
│   ├── __init__.py
│   ├── README.md
│   ├── auth/                   # 인증 및 로그인
│   │   ├── ui/                 # login.ui, widget_login.py
│   │   └── services/
│   ├── base/                   # 기본 인프라 (이벤트 루프)
│   ├── config/                 # 설정 관리
│   ├── di/                     # 의존성 주입
│   ├── events/                 # 이벤트 버스
│   ├── lib/                    # 핵심 라이브러리
│   └── utils/                  # 공통 유틸리티
│
├── 02_data/                    # 데이터 레이어 (DB, 파이프라인)
│   ├── __init__.py
│   ├── README.md
│   ├── timescale/              # TimescaleDB (시계열 OHLCV)
│   ├── redis/                  # Redis (실시간 캐시, PubSub)
│   ├── mongodb/                # MongoDB (메타데이터)
│   ├── kafka/                  # Kafka (스트리밍 파이프라인)
│   ├── clickhouse/             # ClickHouse (분석 쿼리)
│   ├── pipeline/               # 데이터 파이프라인
│   ├── gap/                    # 갭 탐지 및 보정
│   ├── features/               # AI/ML 피처 스토어
│   ├── core/                   # DataManager
│   └── workers/                # 백그라운드 워커
│
├── 03_market/                  # 마켓 데이터 (종목, 호가, 체결)
│   ├── __init__.py
│   ├── README.md
│   ├── coinlist/
│   │   ├── ui/                 # coin_list.ui, favorite.ui, widget_*.py
│   │   ├── logic/
│   │   └── services/
│   ├── orderbook/              # 호가창
│   ├── trades/                 # 체결 데이터
│   ├── websocket/              # WebSocket 클라이언트
│   └── rest/                   # REST API 클라이언트
│
├── 04_chart/                   # 차트 엔진 (5개 엔진, 100+ 지표)
│   ├── __init__.py
│   ├── README.md
│   ├── ui/                     # chart.ui, chart_settings_dialog.ui, widget_chart.py
│   ├── manager/                # ui_manager, period_manager, engine_manager, data_manager, settings_manager
│   ├── ai/                     # AI 기반 차트 분석 (패턴, LSTM 예측, 감성 오버레이)
│   ├── multi/
│   │   └── ui/                 # multi_chart_dialog.ui
│   ├── realtime/
│   │   └── ui/                 # realtime_chart_dialog.ui
│   ├── engines/                # matplotlib/mplfinance/plotly/lightweight/bokeh
│   │   └── matplotlib/        # ✅ Matplotlib 유틸리티 통합 완료
│   ├── indicators/             # trend/momentum/volatility/volume
│   └── utils/
│
├── 05_strategy/                # 트레이딩 전략 (백테스팅, 최적화)
│   ├── __init__.py
│   ├── README.md
│   ├── core/                   # SignalManager, BaseStrategy, StrategyRegistry
│   ├── strategies/             # 전략 구현체 (strategy/ shim 제거됨)
│   ├── widgets/                # 전략 관리 UI
│   └── risk/                   # 리스크 관리
│
├── 06_ai/                      # AI/ML 엔진 (예측, 강화학습, 이상탐지)
│   ├── __init__.py
│   ├── README.md
│   ├── ui/                     # AI UI 통합 진입점 (v4.0)
│   │   ├── __init__.py
│   │   ├── ai_engine/          # ai_engine.ui, widget_ai_engine.py (통합 완료)
│   │   └── prediction/         # prediction.ui, widget_prediction.py (통합 완료)
│   ├── ai_engine/
│   │   ├── ui/                 # compat shim → ui/ai_engine/ 참조
│   │   └── logic/
│   ├── prediction/
│   │   ├── ui/                 # compat shim → ui/prediction/ 참조
│   │   └── logic/
│   ├── models/                 # LSTM, XGBoost, Transformer
│   ├── rl/                     # 강화학습 (PPO)
│   ├── detection/              # 이상탐지 (VAE)
│   ├── sentiment/              # 감성 분석 엔진
│   └── prompt/                 # 프롬프트 관리
│
├── 07_scanner/                 # 마켓 스캐너 (조건 스캔, 알림)
│   ├── __init__.py
│   ├── README.md
│   └── engine/
│       ├── ui/                 # widget_scanner_frame.ui/.py
│       │                       # popup_scanner_settings.ui/.py
│       │                       # scanner_settings_advanced_popup.ui/.py
│       │                       # tab_basic_indicators.ui, tab_advanced_indicators.ui
│       │                       # tab_patterns_volume.ui, tab_filters.ui, tab_alerts_presets.ui
│       ├── logic/
│       ├── workers/
│       ├── models/
│       ├── indicators/
│       └── patterns/
│
├── 08_portfolio/               # 포트폴리오 관리 (자산 현황, 최적화)
│   ├── __init__.py
│   ├── README.md
│   ├── holdings/
│   │   └── ui/                 # detailholdinglist.ui, widget_portfolio.py
│   ├── userinfo/
│   │   └── ui/                 # userinfo.ui, widget_piechart.py
│   └── optimizer/
│
├── 09_sentiment/               # 감성 분석 (뉴스/소셜)
│   ├── __init__.py
│   ├── README.md
│   └── analysis/
│       ├── ui/                 # widget_sentiment.py
│       ├── core/               # sentiment_engine.py, scrapers, signal_generator
│       ├── models/
│       ├── preprocessing/
│       ├── analytics/          # correlation, topic_modeling ✅ (analysis/ → analytics/ 변경)
│       └── workers/
│
├── 10_trade/                   # 트레이드 실행 (주문, 리스크 관리)
│   ├── __init__.py
│   ├── README.md
│   ├── orders/                 # ✅ order/ → orders/ 완전 통합
│   │   ├── market_order.py     # 시장가 주문 빌더
│   │   ├── limit_order.py      # 지정가 주문 빌더
│   │   ├── stop_order.py       # 스탑 주문 빌더
│   │   ├── trailing_stop.py    # 트레일링 스탑 빌더
│   │   └── ui/                 # trade.ui, widget_trade.py
│   ├── signals/
│   ├── risk/
│   └── core/
│
├── 11_server/                  # FastAPI 서버 (REST, WebSocket)
│   ├── __init__.py
│   ├── README.md
│   ├── api/                    # REST API 라우터
│   ├── core/                   # 앱 코어, WebSocket
│   ├── middleware/             # 인증, CORS, 속도제한
│   ├── settings/
│   │   └── ui/                 # settings.ui, widget_settings.py
│   └── utils/
│
├── 12_realtime/                # 실시간 데이터 스트리밍
│   ├── __init__.py
│   ├── README.md
│   ├── component/
│   ├── workers/
│   └── ui/
│
├── 13_compute/                 # 계산 엔진 (지표 계산, 집계)
│   ├── __init__.py
│   ├── README.md
│   ├── engine/                 # ✅ compute/ → engine/ 변경
│   ├── aggregation/
│   └── workers/
│
├── app/                        # 메인 애플리케이션
│   ├── __init__.py
│   ├── README.md
│   ├── config/
│   ├── core/
│   ├── services/
│   └── ui/
│
├── resources/                  # 공통 리소스
│   ├── __init__.py
│   ├── icons/
│   └── images/
│
└── styles/                     # UI 스타일
    ├── __init__.py
    ├── dark_theme.qss
    └── light_theme.qss
```

---

## 15가지 설계 원칙

| # | 원칙 | 설명 |
|---|------|------|
| 1 | **일관성** | 모든 모듈이 `ui/` + `logic/` + `workers/` 패턴 준수 |
| 2 | **논리성** | 기능별 명확한 그룹화 (번호 01~13으로 도메인 구분) |
| 3 | **통합성** | 중복 영역 통합 — backup UI 파일을 src로 일원화 |
| 4 | **모듈성** | 파일당 500~700줄 목표, 파일 분리 원칙 준수 |
| 5 | **확장성** | 플러그인 기반 구조 — 전략/엔진/스캐너 레지스트리 |
| 6 | **유연성** | 다양한 DB·차트 엔진 교체 가능 (추상화 계층) |
| 7 | **상호보완성** | UI와 로직의 명확한 연결 (MVC/MVP 패턴) |
| 8 | **균형성** | 폴더 깊이 3~5단계 유지 |
| 9 | **점진성** | 모니터 → 스캐너 → AI → 자동매매 단계적 구현 |
| 10 | **완결성** | 모든 기능(차트/스캐너/AI/트레이드/서버) 완전 구현 |
| 11 | **재사용성** | `01_core/utils/`·`resources/`·`styles/` 공통 모듈 |
| 12 | **계층성** | Core → Data → Market → Chart → Strategy → AI → Trade |
| 13 | **전환성** | 하위 호환성 유지 — DeprecationWarning 기반 shim 지원 |
| 14 | **강조성** | 핵심 기능(AI/스캐너) 별도 번호 모듈로 강조 |
| 15 | **반복성** | `ui/`, `logic/`, `workers/`, `models/` 패턴 반복 적용 |

> **절대 원칙**: ✅ 중복 금지 ✅ 분산 금지 ✅ `.ui` 파일 순수 PyQt5 유지 ✅ 민감정보 커밋 금지

---

## 시작 가이드

### 1. 사전 요구사항

- **OS**: Windows 10/11 (권장), Linux/macOS 지원
- **Python**: 3.11.11 (Anaconda 환경 권장)
- **Docker**: TimescaleDB, Redis, MongoDB, Kafka, ClickHouse 컨테이너

### 2. 의존성 설치

```bash
# 가상환경 생성 및 활성화
conda create -n py311 python=3.11.11
conda activate py311

# 의존성 설치
pip install -r requirements.txt
```

### 3. 환경 설정

```bash
# .env 파일 생성 (루트 디렉토리)
cp .env.example .env
# .env 파일에서 API 키 및 DB 설정 입력
# UPBIT_ACCESS_KEY=your_access_key
# UPBIT_SECRET_KEY=your_secret_key
# TIMESCALE_HOST=localhost
# REDIS_HOST=localhost
# MONGODB_HOST=localhost
```

### 4. Docker 서비스 시작

```bash
docker-compose up -d
```

### 5. 애플리케이션 실행

```bash
# GUI 애플리케이션
python -m src.app.main

# FastAPI 서버
python -m src._11_server.core.app

# 테스트 실행
python -m pytest tools/tests/ -q
```

---

## 모듈 개요

| 모듈 | 설명 | 핵심 기술 |
|------|------|-----------|
| `01_core/` | 핵심 인프라 (인증, DI, 설정) | PyQt5, asyncio |
| `02_data/` | 데이터 레이어 (DB, 파이프라인) | TimescaleDB, Redis, MongoDB, Kafka, ClickHouse |
| `03_market/` | 마켓 데이터 (종목, 호가, 체결) | Upbit WebSocket/REST API |
| `04_chart/` | 차트 엔진 (5개 엔진, 100+ 지표) | matplotlib, mplfinance, plotly, lightweight-charts, bokeh |
| `05_strategy/` | 트레이딩 전략 (백테스팅, 최적화) | 변동성돌파, 추세추종, DCA, 그리드 |
| `06_ai/` | AI/ML 엔진 (예측, 강화학습, 이상탐지) | LSTM, XGBoost, Transformer, PPO, VAE |
| `07_scanner/` | 마켓 스캐너 (조건 스캔, 알림) | 기술지표, 패턴, 볼륨 조건 |
| `08_portfolio/` | 포트폴리오 관리 (자산 현황, 최적화) | 파이차트, 수익률 분석 |
| `09_sentiment/` | 감성 분석 (뉴스/소셜) | FinBERT, KoBERT |
| `10_trade/` | 트레이드 실행 (주문, 리스크 관리) | Upbit 주문 API, PAPER/LIVE 모드 |
| `11_server/` | FastAPI 서버 (REST, WebSocket) | FastAPI, uvicorn, WebSocket |
| `12_realtime/` | 실시간 데이터 스트리밍 | Upbit WebSocket, 틱 수신 |
| `13_compute/` | 계산 엔진 (지표 계산, 집계) | 캔들 집계, O(1) 증분 계산 |

---

## 기여 가이드

### 코드 스타일

- **Python**: PEP 8 준수, 타입 힌트 사용
- **파일 크기**: 파일당 500~700줄 목표 (최대 800줄)
- **명명 규칙**: `snake_case` (파일/변수), `PascalCase` (클래스)
- **UI 파일**: `.ui` 파일은 순수 PyQt5 Qt Designer 형식 유지

### 새 모듈 추가 시

1. 해당 번호 폴더 하위에 `logic/`, `ui/`, `workers/` 구조 생성
2. `__init__.py` 및 `README.md` 생성 필수
3. 15가지 설계 원칙 준수 여부 확인

### PR 작성 방법

1. feature 브랜치 생성: `git checkout -b feature/모듈명-기능명`
2. 변경사항 커밋 (한 PR에 한 기능 집중)
3. 테스트 실행: `python -m pytest tools/tests/ -q`
4. PR 설명에 변경 모듈, 영향 범위, 테스트 결과 포함

### 테스트 가이드

```bash
# 전체 테스트 (app/ 제외 — headless 환경)
python -m pytest tools/tests/ -q --ignore=tools/tests/app

# 특정 모듈 테스트
python -m pytest tools/tests/test_scanner.py -v

# 코드 품질 검사
flake8 src/
```

---

## ⚠️ 보안 및 실거래 주의사항

- **API 키 관리**: `.env` 파일 사용, 절대 커밋 금지
- **LIVE 모드**: `10_trade/` 모듈은 실거래 API를 호출합니다 — PAPER 모드로 충분히 검증 후 사용
- **STAGE_LOCKED**: `work_order/*.md` 파일의 STAGE_X_LOCKED 토큰 준수

---

## 참고 문서

- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md) — 시스템 전체 설계 가이드
- [`work_order/DB설계.md`](../work_order/DB설계.md) — 데이터베이스 설계 v8/v9
- [`work_order/규칙.md`](../work_order/규칙.md) — 개발 규칙 및 원칙
- [`work_order/README_작성_가이드.md`](../work_order/README_작성_가이드.md) — README 작성 가이드

Last Modified: 2026-03-13 | Copilot

끝