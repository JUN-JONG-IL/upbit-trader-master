# CHANGELOG

## [Unreleased] - 2026-04-04

### 수정 (Critical Fixes) — 데이터 파이프라인 완전 재구축

- **문제 1 — staging_candles 스키마 불일치 수정**: `DO $$` 블록으로 `quote_volume`, `trade_count`, `is_complete` 컬럼을 idempotent하게 추가. `RAISE NOTICE`로 실행 결과 확인 가능.
- **문제 2 — 연결 풀 고갈 해결**: 신규 `connector.py` (`psycopg2.pool.SimpleConnectionPool`, maxconn=10), `MongoConnector.connect()` maxPoolSize=10 및 연결 재사용, `RedisClient` max_connections=10 추가.
- **문제 3 — Event Loop 충돌 해결**: `MetadataManager.update_snapshot_if_new()`에 Event Loop 오류 감지 시 동기 pymongo fallback(`_sync_update_snapshot_if_new`) 자동 전환 추가.
- **문제 4 — TimescaleDB 쿼리 버전 호환**: `fetch_compression_policies()`와 `fetch_continuous_aggs()` 함수 추가 — v2.25+ primary 쿼리 실패 시 구 버전 카탈로그 fallback으로 자동 전환.
- **문제 5 — 모니터링 UI 추가**: `status_widget.ui`에 전체 흐름 모니터링 그룹박스 추가 (Step 1~3 + 최종 현황), `status_widget.py`에 1초 갱신 타이머 및 실시간 집계 로직 추가.

### 영향 범위
- `src/02_data/timescale/sql/00_schema.sql`: DO $$ 블록 idempotent 컬럼 추가
- `src/02_data/timescale/connector.py` (신규): psycopg2 풀 기반 싱글톤 연결 관리자
- `src/02_data/mongodb/mongo_db.py`: maxPoolSize=10, 연결 재사용
- `src/02_data/redis/redis_client.py`: max_connections=10
- `src/02_data/mongodb/metadata_manager.py`: 동기 fallback 메서드 추가
- `src/02_data/timescale/timescale_db.py`: fetch_compression_policies/fetch_continuous_aggs 추가
- `src/02_data/ui/status_widget.ui`: 파이프라인 모니터링 그룹박스 추가
- `src/02_data/ui/status_widget.py`: 1초 갱신 타이머 및 파이프라인 로직 추가
- `docs/fixes/DATABASE_FIXES.md`: 5가지 문제 상세 문서 업데이트

---

## [v4.4] - 2026-03-19

### Changed — 파일 구조 리팩터링: 도메인 경계 정비

#### 파일 이동

| 이전 위치 | 새 위치 | 이유 |
|---|---|---|
| `src/06_ai/priority/services/ml_service.py` | `src/06_ai/ai_engine/ml_service.py` | ML 서비스는 AI 엔진 레이어에 속함 |
| `src/06_ai/priority/ui/ml_model_selector.ui` | `src/06_ai/ui/ai_engine/ml_model_selector.ui` | AI UI는 `06_ai/ui/` 하위에 위치해야 함 |
| `src/06_ai/priority/services/upbit_data_provider.py` | `src/02_data/clients/upbit_data_provider.py` | 업비트 데이터 공급자는 데이터 레이어에 속함 |

#### 임포트 경로 업데이트
- `src/06_ai/priority/services/__init__.py`: 변경 내역 문서화, shim 경유
- `src/06_ai/priority/services/ml_service.py`: [SHIM] `ai_engine/ml_service.py` 로드
- `src/06_ai/priority/services/upbit_data_provider.py`: [SHIM] `02_data/clients/upbit_data_provider.py` 로드
- `src/06_ai/priority/controllers/ml_controller.py`: `_UI_FILE` 경로를 `ui/ai_engine/ml_model_selector.ui` 로 업데이트
- `src/06_ai/priority/__init__.py`: 이동 내역 반영
- `src/06_ai/ai_engine/__init__.py`: `MLService` 공개 API 추가
- `src/02_data/clients/__init__.py`: `UpbitDataProvider` 공개 API 추가

#### backend/ 정리
- `backend/services/ml_service.py`: [SHIM] `src/06_ai/ai_engine/ml_service.py` 로드
- `backend/services/upbit_data_provider.py`: [SHIM] `src/02_data/clients/upbit_data_provider.py` 로드
- `backend/services/priority_service.py`: [SHIM] `src/06_ai/priority/services/priority_service.py` 로드
- `backend/services/priority_db_service.py`: [SHIM] `src/06_ai/priority/services/priority_db_service.py` 로드
- `backend/models/db_models.py`: [SHIM] `src/06_ai/priority/models/db_models.py` 로드
- `backend/__init__.py`: deprecated 안내 추가

#### README/CHANGELOG 업데이트
- `src/06_ai/README.md`: `priority/` 서브패키지 구조 및 ML/AI 서비스 위치 반영
- `src/02_data/README.md`: `upbit_data_provider` 이동 반영



### Changed — src/ v4.0 최종 검증 완료: 중복 파일 제거 및 README 버전 통일

#### 06_ai UI 중복 파일 제거
- `src/06_ai/ai_engine/ui/widget_ai_engine.py` 삭제 (실제 구현 `src/06_ai/ui/ai_engine/` 에 존재)
- `src/06_ai/ai_engine/ui/ai_engine.ui` 삭제 (실제 구현 `src/06_ai/ui/ai_engine/` 에 존재)
- `src/06_ai/ai_engine/ui/dialogs/` 삭제 (실제 구현 `src/06_ai/ui/ai_engine/dialogs/` 에 존재)
- `src/06_ai/prediction/ui/widget_prediction.py` 삭제 (실제 구현 `src/06_ai/ui/prediction/` 에 존재)
- `src/06_ai/prediction/ui/prediction.ui` 삭제 (실제 구현 `src/06_ai/ui/prediction/` 에 존재)
- `src/06_ai/ai_engine/ui/__init__.py` 하위 호환 shim 유지 (삭제 안 함)
- `src/06_ai/prediction/ui/__init__.py` 하위 호환 shim 유지 (삭제 안 함)

#### README 버전 v4.0 최종 통일
- `src/03_market/README.md`: v3.0 → v4.0
- `src/08_portfolio/README.md`: v2.0 → v4.0
- `src/09_sentiment/README.md`: v2.0 → v4.0
- `src/05_strategy/README.md`: v2.0 → v4.0
- `src/04_chart/README.md`: 버전 헤더 추가 (v4.0)
- `src/07_scanner/README.md`: 버전 헤더 추가 (v4.0)



### Changed — src/ v4.0 최종 정리: 중복 구조 제거 및 docs 이동

#### 09_sentiment 중복 구조 제거
- `src/09_sentiment/analysis/analysis/` → `src/09_sentiment/analysis/analytics/` (중복 명명 해소)
- `src/09_sentiment/analysis/correlation_analysis.py` 하위 호환 shim 경로 수정 (`.analytics.*`)
- `src/09_sentiment/analysis/influence_score.py` 하위 호환 shim 경로 수정 (`.analytics.*`)
- `src/09_sentiment/analysis/topic_modeling.py` 하위 호환 shim 경로 수정 (`.analytics.*`)
- `src/09_sentiment/README.md` 구조 다이어그램 업데이트

#### 모듈 내 docs 폴더 루트 docs/로 이동
- `src/04_chart/docs/` → `docs/04_chart/` (ADVANCED_CHART_GUIDE, CHART_ENGINE_COMPARISON, CHART_README)
- `src/05_strategy/docs/` → `docs/05_strategy/` (BACKTEST_GUIDE, STRATEGY_DEVELOPMENT_GUIDE)
- `src/07_scanner/engine/docs/` → `docs/07_scanner/` (API, ARCHITECTURE, EXAMPLES)

#### README 최신화
- `src/README.md` v4.0 구조 다이어그램 완전화 (analytics/ 반영, engine/ 확인)



### Changed — 11_server/ 및 13_compute/ 중복 명명 구조 정리
- `src/11_server/server/` → `src/11_server/app/` (Flask/FastAPI 표준 명명)
- `src/13_compute/compute/` → `src/13_compute/engine/` (계산 엔진 의미 명확화)
- `src/11_server/__init__.py` import 경로 수정 (`app.server`)
- `src/app/main.py` import 경로 수정 (`11_server.app.server`, `11_server.app.static`)
- `src/app/ui/managers/symbol_loader.py` import 경로 수정 (`11_server.app.static.static`)
- `src/13_compute/__init__.py` import 경로 수정 (`engine`)
- `src/11_server/README.md` 구조 다이어그램 업데이트
- `src/13_compute/README.md` 구조 다이어그램 업데이트
- `src/13_compute/engine/README.md` 경로 참조 업데이트

## [v4.1] - 2026-03-15

### Changed — src/ v4.0 최종 정리 (PR #97)
- `src/10_trade/README.md` 중복 섹션 제거 (lines 182–311) 및 날짜 `2025-01-01` → `2026-03-15` 수정
- `src/04_chart/README.md` 폴더 다이어그램 업데이트 (`docs/` → `docs/04_chart/` 참조)
- `src/06_ai/ai_engine/ui/` → `src/06_ai/ui/ai_engine/` 이동 (UI 통합 완료)
- `src/06_ai/prediction/ui/` → `src/06_ai/ui/prediction/` 이동 (UI 통합 완료)
- `src/06_ai/ui/__init__.py` import 경로 수정 (`.ai_engine.` / `.prediction.` 상대경로)
- `src/06_ai/ai_engine/ui/__init__.py` 하위 호환 shim으로 전환
- `src/06_ai/prediction/ui/__init__.py` 하위 호환 shim으로 전환
- `src/README.md` v4.0 구조 다이어그램 업데이트 (`ui/ai_engine/`, `ui/prediction/` 반영)
- 하위 모듈 README 버전 v4.0 통일:
  - `src/01_core/auth/README.md`: v1.0 → v4.0, 날짜 2026-03-15
  - `src/06_ai/prompt/README.md`: v1.0 → v4.0, 날짜 2026-03-15
  - `src/app/README.md`: v1.0 → v4.0, 날짜 2026-03-15



### Changed — src/ 전체 재구조화 v4.0 (명확한 명명 및 용도별 분류)
- `src/03_market/coin_list/` → `src/03_market/coinlist/` (명확한 명명)
- `src/03_market/trade/` → `src/03_market/trades/` (복수형으로 명확화)
- `src/08_portfolio/portfolio/` → `src/08_portfolio/holdings/` (용도 명확화: 보유자산)
- `src/10_trade/trade/` → `src/10_trade/orders/` (용도 명확화: 주문)
- `src/05_strategy/strategy/` 삭제 — deprecated shim 제거, `strategies/`로 통합 완료
- `src/07_scanner/scanner/` → `src/07_scanner/engine/` (중복 명명 해소)
- `src/09_sentiment/sentiment/` → `src/09_sentiment/analysis/` (중복 명명 해소)
- `src/09_sentiment/analysis/logic/` → `src/09_sentiment/analysis/core/` (역할 명확화)
- `src/06_ai/ui/` 통합 진입점 신규 추가 (`ai_engine/ui/` + `prediction/ui/` 통합)
- `src/app/ui/managers/widget_loader.py` 경로 수정 (새 폴더명 반영)
- `src/07_scanner/__init__.py` import 경로 수정 (`engine/`)
- `src/09_sentiment/__init__.py` import 경로 수정 (`analysis/`)
- `src/app/services/scanner_service.py` import 경로 수정 (`engine/`)
- `src/app/services/sentiment_service.py` import 경로 수정 (`analysis/core/`)
- `src/03_market/__init__.py` import 경로 수정 (`coinlist/`, `trades/`)
- `src/08_portfolio/__init__.py` import 경로 수정 (`holdings/`)
- `src/06_ai/__init__.py` import 경로 수정 (`ui/` 통합)
- `src/README.md` v4.0 갱신 (폴더 구조 다이어그램 업데이트)



### Added
- AI/ML 모듈 통합 (`06_ai/`) — sentiment 복구 파일 추가
  - `src/06_ai/sentiment/sentiment_logic.py` — 감성 분석 비즈니스 로직
  - `src/06_ai/sentiment/widget_sentiment.py` — 감성 분석 Qt 위젯
  - `src/06_ai/sentiment/sentiment.ui` — Qt Designer UI
  - `src/06_ai/sentiment/correlation_analysis.py` — Granger 인과관계 분석
  - `src/06_ai/sentiment/influence_score.py` — 소셜 미디어 영향력 점수
  - `src/06_ai/sentiment/multilingual_sentiment.py` — 다국어 감성 분석 (KoBERT, FinBERT)
  - `src/06_ai/sentiment/topic_modeling.py` — BERTopic 주제 모델링
  - `src/06_ai/sentiment/README.md` — 모듈 설명서
  - `src/06_ai/ai_engine/realtime_data.py` — WebSocket 실시간 데이터 피드
  - `src/06_ai/core/README.md`, `detection/README.md`, `strategy/README.md`,
    `training/README.md`, `utils/README.md` — 모듈 설명서

### Changed
- `src/06_ai/sentiment/__init__.py` — SentimentLogic, SentimentWidget 포함하도록 업데이트
- `src/05_ai/__init__.py` — 레거시 shim을 `06_ai`로 리다이렉트 (하위 호환)
- `src/05_ai/ml/__init__.py` — 레거시 shim을 `06_ai`로 리다이렉트 (하위 호환)
- `src/08_ml_ai/__init__.py` — 레거시 shim에 `06_ai.models` 재노출 추가

### Fixed
- 레거시 shim (`05_ai`, `08_ml_ai`)이 폐기된 `10_ai_ml` 대신 `06_ai`를 참조하도록 수정

## [3.2.0] - 2026-02-08

### Added - Advanced Multi-Chart System
- **고급 차트 시스템 구현** (2025-2026 최신 트레이딩 기능)
  - ✅ 100+ 기술 지표 (MA, RSI, MACD, Bollinger Bands, Ichimoku, Fibonacci 등)
  - ✅ 드로잉 툴 15종 (트렌드 라인, 피보나치, 엘리엇 웨이브, Gann 도구 등)
  - ✅ 다양한 차트 타입 (캔들스틱, 라인, 바, 에어리어, 히트맵, Heikin-Ashi, Renko)
  - ✅ 무한 줌/팬/스크롤, 크로스헤어, 툴팁 기능

- **멀티차트 레이아웃 시스템** (`src/chart/multi/`)
  - ✅ 4~16개 차트 동시 표시, 12x6 그리드 레이아웃
  - ✅ 시간축/줌/크로스헤어 동기화
  - ✅ 레이아웃 저장/불러오기 (JSON 스키마)
  - ✅ 5가지 프리셋 레이아웃 (Single, Dual, Quad, Comparison, Workspace)
  - ✅ 다크/라이트 테마 지원
  - ✅ 스플릿 뷰 (상/하 분할)

- **실시간 차트 시스템** (`src/chart/realtime/`)
  - ✅ WebSocket 실시간 스트리밍 (QThread 비동기 처리)
  - ✅ WebGL 가속 렌더링 (lightweight-charts)
  - ✅ 깊이 차트 (호가창) 기능
  - ✅ 성능 메트릭 모니터링 (msg/s, 지연시간)
  - ✅ 자동 재연결 기능

- **AI/ML 차트 통합** (`src/chart/ai/`)
  - ✅ AI 기반 가격 예측 (LSTM/ML 오버레이)
  - ✅ 자동 패턴 인식 (헤드앤숄더, 플래그 등)
  - ✅ 감성 분석 오버레이 (뉴스/소셜 미디어)
  - ✅ 이상 탐지 알림
  - ✅ 자동 업데이트 (5분 간격)

- **차트 컴포넌트** (`src/chart/`)
  - `advanced_chart_dialog.py/.ui`: 고급 차트 메인 다이얼로그
  - `indicators.py`: 100+ 기술 지표 선택 시스템
  - `drawing_tools.py`: 15종 드로잉 툴
  - `chart_types.py`: 7가지 차트 타입 (Heikin-Ashi, Renko 포함)

### Documentation
- ✅ `src/chart/multi/README.md`: 멀티차트 레이아웃 가이드
- ✅ `src/chart/ai/README.md`: AI/ML 통합 가이드
- ✅ 모든 다이얼로그에 도움말 버튼 (❓) 구현
- ✅ Phase 11-13 규칙 준수 (실제 데이터, QThread, 도움말 필수)

### Technical Implementation
- ✅ **work_order/규칙.md 준수**
  - UI 파일(.ui)과 로직 파일(.py) 같은 폴더에 배치
  - QPainter.Antialiasing 올바른 사용
  - QThread 비동기 처리 (렉 방지)
  - Dialog suffix 사용
  - 차트 최소 크기 800x600px

- ✅ **렉 방지 규칙**
  - 네트워크/DB/ML 작업은 QThread 사용
  - UI 응답 시간 < 100ms
  - GUI 메인 스레드에서 time.sleep() 금지

- ✅ **Phase 11-13 AI/ML 규칙**
  - UI 생성 시 백엔드 로직 동시 구현
  - 도움말 버튼 필수 구현
  - 실제 데이터로 테스트 (Mock/Stub 금지)
  - QThread 비동기 처리

### Files Changed
- **새 파일** (13개):
  - `src/chart/advanced_chart_dialog.py/.ui`
  - `src/chart/indicators.py`
  - `src/chart/drawing_tools.py`
  - `src/chart/chart_types.py`
  - `src/chart/multi/multi_chart_dialog.py/.ui`
  - `src/chart/multi/README.md`
  - `src/chart/multi/__init__.py`
  - `src/chart/realtime/realtime_chart_dialog.py/.ui`
  - `src/chart/realtime/__init__.py`
  - `src/chart/ai/ai_chart_dialog.py/.ui`
  - `src/chart/ai/README.md`
  - `src/chart/ai/__init__.py`

---

## [3.1.1] - 2026-02-06

### Fixed
- **QChartView Antialiasing 오류 수정**
  - `src/ai/ai_engine_dialog.py`: QPainter.Antialiasing 사용으로 수정
  - `src/models/prediction_dialog.py`: QPainter.Antialiasing 사용으로 수정 (3곳)
  - `src/nlp/sentiment_dialog.py`: QPainter.Antialiasing 사용으로 수정
  - 모든 AI/ML 다이얼로그 차트가 정상 표시되도록 수정
  - AttributeError: 'QChartView' object has no attribute 'Antialiasing' 완전 해결

### Added
- **work_order/규칙.md**: PyQt5 Chart 사용 규칙 추가
  - QChartView Antialiasing 올바른 사용법 문서화
  - QPainter.Antialiasing 사용 규칙 정의
  - 자동 검증 명령어 추가
- **tests/test_chart_rendering.py**: Chart 렌더링 테스트 추가
  - QChartView Antialiasing 설정 테스트
  - AI/ML 다이얼로그 import 테스트
- **docs/PYQT5_CHART_GUIDE.md**: PyQt5 Chart 사용 가이드 생성
  - 올바른 Antialiasing 설정 방법
  - 자주 발생하는 오류 및 해결 방법
  - 완전한 예제 코드 (라인 차트, 파이 차트)
  - 검증 방법 및 참고 자료

### Documentation
- PyQt5 QChartView Antialiasing 올바른 사용법 문서화
- 자동 검증 스크립트 가이드 추가
- 재발 방지를 위한 규칙 문서화 완료

---

## [3.1.0] - 2026-02-06

### Fixed
- ✅ AI/ML 다이얼로그 임포트 경로 수정 (src. 접두사 제거)
  - `src/ai/ai_engine_dialog.py` - 6개 임포트 수정
  - `src/models/prediction_dialog.py` - 10개 임포트 수정
  - `src/nlp/sentiment_dialog.py` - 10개 임포트 수정
  - 모든 `from src.` → `from` 패턴으로 변경
  - 프로젝트 Python path 구조에 맞게 수정

### Added
- 📝 임포트 규칙 문서 (`docs/development/IMPORT_GUIDELINES.md`)
  - 올바른/잘못된 임포트 예제
  - Python path 구조 설명
  - 자동/수동 검증 방법
- 🔧 Pre-commit hook (`scripts/check_imports.py`)
  - 모든 Python 파일에서 `from src.` 패턴 자동 검출
  - 잘못된 임포트 위치 및 라인 번호 표시
  - 종료 코드 반환 (CI/CD 통합 가능)
- 🔧 `.pre-commit-config.yaml` 설정
  - check-imports hook 자동 실행
  - Python 파일 수정 시 자동 검증

### Changed
- 📝 `work_order/11_단계_AI_엔진_통합.md` - 임포트 규칙 섹션 추가
- 📝 `work_order/12_단계_예측_모델.md` - 임포트 규칙 섹션 추가
- 📝 `work_order/13_단계_뉴스_소셜_감성_분석_시스템.md` - 임포트 규칙 섹션 추가
- 📝 `README.md` - 개발 가이드에 임포트 규칙 강조 추가
- 📝 임포트 규칙 가이드 링크 추가

---

## [3.0.0] - 2026-02-06

### 🎉 Major Release: 획기적인 AI/ML 기능 추가

#### Fixed
- **임포트 경로 수정 완료**
  - `src/app/window_main.py`의 AI/ML 다이얼로그 임포트 수정
  - `src.` 접두사 제거 (프로젝트 구조에 맞게 수정)
  - `from ai.ai_engine_dialog import AIEngineDialog` (수정 후)
  - `from models.prediction_dialog import PredictionDialog` (수정 후)
  - `from nlp.sentiment_dialog import SentimentDialog` (수정 후)
  - `__init__.py` 파일에 다이얼로그 클래스 추가

- **APScheduler Graceful Shutdown 완전 구현**
  - DataManager에 graceful shutdown 구현 완료
  - SIGINT, SIGTERM 시그널 핸들러 추가
  - atexit 핸들러로 안전한 종료 보장
  - shutdown flag로 종료 중 스케줄링 방지
  - `_one_minute_sync_loop`에서 종료 플래그 체크
  - 모든 종료 오류 완전 해결 ✅

- **11~13단계 다이얼로그 파일 완전 복구**
  - 모든 버튼 및 팝업창 정상 동작
  - Qt Designer 원칙 준수 (.ui와 .py 분리)
  - Signal/Slot 패턴 완전 구현

#### Added - 획기적인 AI/ML 기능

##### 멀티 모달 AI 통합 (`src/ai/multimodal_engine.py`)
- 텍스트(뉴스), 이미지(차트), 시계열(가격) 데이터 통합 분석
- CLIP 기반 차트 패턴 인식 (head_and_shoulders, double_top, flags 등)
- 멀티 시그널 통합 (가중 평균 방식)
- 트렌드 자동 감지 (uptrend, downtrend, sideways)

##### Ollama 로컬 LLM 어시스턴트 (`src/ai/ollama_assistant.py`)
- Llama 3.1, Mistral, Gemma 로컬 실행
- 자연어 명령 해석 ("비트코인 차트 보여줘", "이더리움 매수해" 등)
- 트레이딩 전략 자연어 파싱
- 실시간 AI 조언 생성
- 심볼 자동 추출 (비트코인→KRW-BTC 변환)

##### DQN 강화학습 트레이더 (`src/rl/dqn_trader.py`)
- Deep Q-Network 기반 자동 매매 에이전트
- Gym-like 트레이딩 환경 구현
- 상태: OHLCV + 기술 지표 + 감성 점수
- 행동: BUY, SELL, HOLD
- Q-learning 알고리즘 구현
- Epsilon-greedy 탐험 전략
- 모델 저장/로드 (.npz 형식)
- Stable-Baselines3 호환 인터페이스

##### 이상 거래 탐지 (`src/detection/anomaly_detector.py`)
- Autoencoder 기반 비정상 패턴 감지
- **펌프앤덤프** (Pump & Dump) 탐지
- **워시 트레이딩** (Wash Trading) 감지
- **스푸핑** (Spoofing) 탐지
- 심각도 분류 (normal, low, medium, high, critical)
- 재구성 오류 기반 이상 점수 계산
- 배치 탐지 지원
- 임계값 자동 설정 (contamination 기반)

##### 포트폴리오 최적화 (`src/portfolio/optimizer.py`)
- **마코위츠 평균-분산 모델** (Markowitz Portfolio Theory)
- **효율적 프론티어** (Efficient Frontier) 계산
- 샤프 비율 최대화
- 최소 분산 포트폴리오
- 리스크 패리티 (Risk Parity)
- 최대 분산 (Maximum Diversification)
- scipy 선택적 사용 (없어도 작동)

#### Documentation Updates
- `work_order/11_단계_AI_엔진_통합.md` - 획기적 기능 추가 항목 반영
- `work_order/12_단계_예측_모델.md` - DQN, 포트폴리오 최적화 추가
- `work_order/13_단계_뉴스_소셜_감성_분석_시스템.md` - 이상 탐지, 멀티 모달 추가

#### File Structure
```
src/
├── ai/
│   ├── multimodal_engine.py      # 멀티 모달 AI 엔진 ✨ NEW
│   └── ollama_assistant.py       # Ollama LLM 어시스턴트 ✨ NEW
├── rl/
│   ├── __init__.py                # ✨ NEW
│   └── dqn_trader.py              # DQN 강화학습 트레이더 ✨ NEW
├── detection/
│   ├── __init__.py                # ✨ NEW
│   └── anomaly_detector.py       # 이상 거래 탐지 ✨ NEW
└── portfolio/
    ├── __init__.py                # ✨ NEW
    └── optimizer.py               # 포트폴리오 최적화 ✨ NEW
```

---

## [2.3.0] - 2026-02-06

### Fixed
- **APScheduler RuntimeError 완전 해결**
  - DataManager에 graceful shutdown 구현
  - SIGINT, SIGTERM 시그널 핸들러 추가
  - atexit 핸들러로 안전한 종료 보장
  - shutdown flag로 종료 중 스케줄링 방지
  - `_one_minute_sync_loop`에서 종료 플래그 체크
  
- **11~13단계 UI 기능 완전 구현**
  - 모든 버튼 및 팝업창 정상 동작
  - Qt Designer 원칙 준수 (.ui와 .py 분리)
  - Signal/Slot 패턴 완전 구현

### Added

#### 11단계: AI 엔진 통합 (src/ai_engine/)
- **GPT-4o, Gemini API 연동**
  - OpenAI GPT-4o, GPT-4o-mini 지원
  - Google Gemini 1.5 Pro, 2.0 Flash 지원
  - API 키 설정 다이얼로그 (`dialog_api_settings.py`)
  
- **실시간 AI 분석 기능**
  - AI 분석 시작/중지 버튼
  - 긴급 중단 버튼 (🚨)
  - 신뢰도 임계값 슬라이더 (0.0 ~ 1.0)
  - 모델 선택 드롭다운
  
- **분석 결과 표시**
  - 실시간 로그 스트리밍
  - 분석 결과 테이블 (시각, 신호, 신뢰도, 근거)
  - 성능 메트릭 (정확도, 승률, 평균 수익률)
  
- **파일 구조**
  - `widget_ai_engine.py` - Qt UI 위젯
  - `ai_engine.ui` - Qt Designer UI 정의
  - `ai_engine_logic.py` - AI 엔진 비즈니스 로직
  - `dialog_api_settings.py` - API 설정 다이얼로그
  - `README.md` - 모듈 문서

#### 12단계: 예측 모델 (src/prediction/)
- **5가지 ML 모델 지원**
  - LSTM (Long Short-Term Memory)
  - GRU (Gated Recurrent Unit)
  - Transformer
  - XGBoost
  - LightGBM
  
- **학습 및 예측 기능**
  - 모델 학습 시작 버튼
  - 예측 실행 버튼
  - 학습 진행률 바
  - 데이터 소스 선택 (실시간/과거)
  - 예측 기간 선택 (5분/15분/1시간/4시간/1일)
  
- **성능 평가**
  - 정확도 메트릭 테이블 (MAE, RMSE, R², Sharpe Ratio)
  - 백테스팅 기능
  - 예측 vs 실제 그래프 (matplotlib)
  
- **모델 관리**
  - 모델 저장/불러오기 (.pth 파일)
  - 학습 로그 출력
  
- **파일 구조**
  - `widget_prediction.py` - Qt UI 위젯
  - `prediction.ui` - Qt Designer UI 정의
  - `prediction_logic.py` - ML 모델 구현
  - `test_prediction.py` - 테스트 코드
  - `demo.py` - 사용 예제
  - `README.md` - 모듈 문서

#### 13단계: 감성 분석 (src/sentiment/)
- **다중 소스 스크래핑**
  - 뉴스 스크래핑 시작 버튼
  - 트위터 스크래핑 시작 버튼
  - 레딧 스크래핑 시작 버튼
  - 모두 중지 버튼
  
- **감성 점수 시각화**
  - 감성 점수 게이지 (-1.0 ~ +1.0)
  - 실시간 업데이트 간격 설정 슬라이더 (10~300초)
  - 소스 필터링 체크박스 (뉴스/트위터/레딧)
  
- **데이터 시각화**
  - 키워드 클라우드 (wordcloud)
  - 감성 히스토리 차트 (시계열)
  - 긍정/부정/중립 비율 파이 차트
  - 감성 점수 테이블 (시각, 소스, 점수, 키워드, 헤드라인)
  
- **파일 구조**
  - `widget_sentiment.py` - Qt UI 위젯
  - `sentiment.ui` - Qt Designer UI 정의
  - `sentiment_logic.py` - 스크래핑 및 감성 분석 로직
  - `README.md` - 모듈 문서

#### 테스트 코드 추가
- `tests/test_apscheduler_shutdown.py` - APScheduler 종료 테스트
- `tests/test_ai_engine_ui.py` - AI 엔진 UI 테스트
- `tests/test_prediction_ui.py` - 예측 모델 UI 테스트
- `tests/test_sentiment_ui.py` - 감성 분석 UI 테스트

### Changed
- **자동화 문서 업데이트**
  - 11~13단계 완료 상태 반영
  - Qt Designer 원칙 명시
  - 테스트 가이드 업데이트

### Technical Details

#### Qt Designer 원칙 준수
- UI 정의 (.ui)와 로직 (.py) 완전 분리
- uic.loadUi()로 동적 UI 로딩
- Signal/Slot 패턴 일관성 유지
- pathlib.Path 사용

#### 보안 강화
- API 키 .env 파일 관리
- 비밀번호 필드 마스킹
- 긴급 중단 기능

#### 성능 최적화
- 백그라운드 스레드 사용 (학습/스크래핑)
- 논블로킹 UI 업데이트
- 효율적인 데이터 처리

### Dependencies
```
PyQt5>=5.15.0
openai>=1.0.0
google-generativeai>=0.3.0
python-dotenv>=1.0.0
torch>=2.0.0
transformers>=4.30.0
xgboost>=2.0.0
lightgbm>=4.0.0
matplotlib>=3.5.0
wordcloud>=1.9.0
```

---

## [Documentation v2.1] 문서 정리 및 완성 - 2026-02-03

### ✅ 추가됨 (Added)

#### 문서 개선
- `docs/automation_full_features.md` - 검증 기준 추가
  - 단계 지시서 검증 기준 명시
  - 환경 검증 기준 명시
  - 문서 표준 검증 기준 명시
  - 트러블슈팅 섹션 추가
  - 중요 원칙 추가

### 🔧 변경됨 (Changed)

#### 통합 개발 가이드 업데이트
- `work_order/통합_개발_가이드.md` - 지시서 검증 섹션 추가
  - 1.5️⃣ 작업 지시서 검토 및 개선 섹션 강화
  - 검증 도구 사용법 추가 (`verify_work_order.py`)
  - 검증 방법 상세화
  - 개선 원칙 명확화

#### 문서 업데이트 프로세스 개선
- `work_order/문서_업데이트_프로세스.md` - 검증 단계 추가
  - 0️⃣ 작업 전 검증 섹션 신규 추가
  - 지시서 완전성 검증 단계 추가
  - 환경 검증 단계 추가
  - 문서 표준 검증 단계 추가

### 📝 검증 완료 (Verified)

#### 기존 파일 완성도 확인
- ✅ `automation/env_check.py` - 373줄, 완성됨
- ✅ `automation/auto_workflow.py` - 428줄, 완성됨
- ✅ `automation/test_runner.py` - 401줄, 완성됨
- ✅ `automation/doc_updater.py` - 404줄, 완성됨
- ✅ `automation/TEST_GUIDE.md` - 657줄, 완성됨
- ✅ `scripts/doc_check.py` - 428줄, 완성됨
- ✅ `scripts/backup_manager.py` - 429줄, 완성됨
- ✅ `scripts/changelog_helper.py` - 319줄, 완성됨
- ✅ `scripts/verify_work_order.py` - 319줄, 완성됨
- ✅ `scripts/recovery_tool.py` - 351줄, 완성됨

### 🎯 작업 목적

**문제 해결**: work_order 폴더의 단계 지시서가 100% 완벽하지 않을 수 있음  
**해결 방법**: 모든 자동화 작업 시작 전 검증 시스템 구축

---

## [Automation v2.0] 자동화 시스템 완전 업그레이드 - 2026-02-03

### ✅ 추가됨 (Added)

#### 신규 자동화 도구
- `automation/error_predictor.py` - AI 기반 에러 예측 및 예방 시스템
  - 과거 로그 분석으로 잠재적 오류 예측
  - ML 모델 (scikit-learn) 사용
  - 에러 발생 시 자동 롤백 (Git)
  - 패턴 기반 오류 탐지 및 예방 조치 제안

- `automation/monitoring_dashboard.py` - 실시간 모니터링 대시보드
  - 시스템 상태 실시간 모니터링 (CPU, 메모리, 디스크)
  - 웹 대시보드 (Flask)
  - 성능 메트릭 시각화
  - 알림 시스템 및 오류 즉시 보고

- `automation/test_framework.py` - 테스트 프레임워크 업그레이드
  - pytest 통합 (단위/통합 테스트)
  - 커버리지 리포트 자동 생성 (80% 미만 시 중단)
  - 백테스팅 자동화 (Backtrader)
  - 성능 벤치마크 자동화

- `automation/security_checker.py` - 보안 및 컴플라이언스 자동 체크
  - API 키/비밀 관리 자동화
  - 하드코딩된 비밀 스캔
  - 보안 취약점 스캔 (bandit)
  - 암호화폐 거래 규제 준수 체크리스트

- `automation/docker_automation.py` - Docker 컨테이너화 자동화
  - Dockerfile 자동 생성 (프로젝트 구조 기반)
  - docker-compose.yml 검증 및 최적화
  - 이미지 빌드 및 배포 자동화
  - Kubernetes 매니페스트 생성

- `automation/feedback_collector.py` - 사용자 피드백 루프
  - 작업 후 자동 설문/로그 수집
  - GitHub Issues 템플릿 생성
  - 피드백 분석 및 개선 사항 자동 제안

#### 신규 스크립트
- `scripts/verify_work_order.py` - 작업 지시서 자동 검증
  - 모든 work_order/*.md 파일 검증
  - 지시서 완전성 검사
  - 표준 헤더 및 링크 유효성 확인
  - 개선 사항 제안

- `scripts/auto_doc_generator.py` - 자동 문서 생성기 업그레이드
  - Python 코드 주석 자동 추출 → Markdown 변환
  - API 문서 자동 생성 (docstring → OpenAPI spec)
  - Git hooks 통합 (커밋 시 자동 업데이트)
  - 버전 관리 통합

#### 문서
- `docs/automation_full_features.md` - 전체 자동화 기능 목록
  - 모든 자동화 도구 상세 설명
  - 7개 카테고리별 분류 및 사용법
  - 워크플로우 예시
  - 모범 사례 및 주의사항

### 🔄 업데이트됨 (Updated)

#### 설정 파일
- `requirements.txt` - 자동화 관련 패키지 추가
  - scikit-learn>=1.3.0 (에러 예측)
  - flask>=2.3.0 (모니터링 대시보드)
  - streamlit>=1.28.0 (모니터링 대시보드, 선택)
  - bandit>=1.7.5 (보안 스캔)
  - psutil>=5.9.0 (시스템 모니터링)

- `.gitignore` - 자동화 관련 항목 추가
  - automation/backups/
  - automation/*.log
  - automation/error_model.pkl
  - bandit_report.json
  - test_reports/
  - feedback/

#### 문서
- `automation/README.md` - v2.0 업데이트
  - 6개 신규 자동화 도구 설명 추가
  - 전체 워크플로우 업데이트
  - docs/automation_full_features.md 링크 추가

### 🎯 주요 개선사항

#### 에러 관리 강화
- AI 기반 에러 예측으로 사전 방지
- 자동 롤백 기능으로 빠른 복구
- 패턴 인식을 통한 반복 오류 방지

#### 모니터링 및 보안
- 실시간 시스템 상태 모니터링
- 웹 대시보드로 직관적인 시각화
- 포괄적인 보안 체크 자동화
- 컴플라이언스 준수 확인

#### 테스트 자동화
- 커버리지 기반 품질 보장
- 백테스팅 자동화
- 성능 벤치마크 자동 실행

#### 개발자 경험 개선
- 피드백 수집 및 분석 자동화
- 문서 자동 생성으로 문서화 부담 감소
- Docker/K8s 지원으로 배포 간소화

---

## [5단계 / Phase 5] Scanner/Search 엔진 완전 구현 - 2026-02-03

### ✅ 추가됨 (Added)

#### 문서
- `work_order/5_단계_Scanner_Search_엔진_v2.md` - 이미지 기반 Phase 5 작업 지시서 (v2.0)
  - 4개 이미지 기반 완전한 UI/UX 명세
  - 상세 설정창 UI 컴포넌트 정의 (14개 체크박스, 5개 콤보박스, 12개 스핀박스)
  - Scanner 엔진 아키텍처 및 데이터 흐름
  - 룰 정의 및 스코어링 시스템
  - 테스트 계획 및 완료 기준
  - 기존 내용 부록으로 보존

- `docs/phases/phase5_completion.md` - Phase 5 완료 보고서
  - 구현 통계 (신규 파일 7개, 수정 파일 3개)
  - 컴포넌트 아키텍처 다이어그램
  - UI/UX 기능 체크리스트
  - 사용 예시 및 확장 포인트
  - 향후 개선사항 (Elasticsearch, Kafka, REST API 등)

- `work_order/5_단계_Scanner_Search_엔진_OLD.md` - 기존 Phase 5 문서 백업

#### 코드
- `src/search/popup_search_settings_advanced.ui` - 고급 설정창 UI (Qt Designer XML)
  - 기본 설정 그룹 (자동테교, 기준코인, 코인, 분봉)
  - OHLC 임계값 그룹 (Open/Close/High/Low)
  - 최근 기준 제외 설정
  - RSI 설정 (분봉, 임계값, 다이버전스 7개 체크박스)
  - 평균거래량 설정 (6개 체크박스, 증가율 임계값)
  - 골든크로스/데드크로스 설정
  - 이동평균 설정 (단기/장기)
  - 자동갱신 주기 설정
  - 저장/취소 버튼

- `src/search/popup_search_settings_advanced.py` - 고급 설정 다이얼로그 (169 lines)
  - UI 로드 및 초기화
  - 콤보박스 자동 채우기 (코인 목록, 분봉 옵션)
  - 스핀박스 기본값 설정
  - get_settings() 메서드로 모든 설정 dict 반환
  - 저장/취소 버튼 처리

- `src/search/scanner_engine.py` - Scanner 백엔드 엔진 (181 lines)
  - 비동기 스캔 실행 (async scan)
  - aiopyupbit API 통합 (OHLCV 데이터 조회)
  - 4가지 룰 체크 (RSI, 골든크로스, 거래량, OHLC)
  - 스코어 계산 및 정렬
  - TA-Lib 옵션 지원 (fallback to simple calculations)
  - 에러 처리 및 로깅

- `src/search/scanner_rules.py` - Scanner 룰 정의 (130 lines)
  - RuleBase 추상 클래스
  - RSIRule 구현 (RSI < threshold)
  - GoldenCrossRule 구현 (단기 MA vs 장기 MA)
  - VolumeRule 구현 (거래량 증가율)
  - OHLCRule 구현 (가격 변화율)
  - RULES 레지스트리 (플러그인 시스템)

#### 테스트
- `tests/search/` - Search 모듈 테스트 디렉토리 생성

- `tests/search/test_scanner_engine.py` - Scanner 엔진 단위 테스트 (8 tests)
  - 엔진 초기화 테스트
  - RSI 룰 체크 테스트
  - 골든크로스 룰 체크 테스트
  - 거래량 룰 체크 테스트
  - OHLC 룰 체크 테스트
  - 전체 룰 체크 테스트
  - 빈 데이터 스캔 테스트
  - Mock 데이터 스캔 테스트

- `tests/search/test_popup_search_settings_advanced.py` - 설정 다이얼로그 테스트 (7 tests)
  - 팝업 초기화 테스트
  - 콤보박스 초기화 테스트
  - 스핀박스 초기화 테스트
  - get_settings() 메서드 테스트
  - 체크박스 상태 테스트
  - 설정 값 타입 테스트

- `tests/search/__init__.py` - 테스트 문서 및 실행 가이드

### 🔧 변경됨 (Changed)

- `work_order/통합_개발_가이드.md` - 지시서 개선 프로세스 추가
  - **새 섹션**: 1.5️⃣ 작업 지시서 검토 및 개선 (자동 업그레이드)
  - Copilot 자동 수행 프로세스 정의
  - 개선 원칙 명시 (지시서는 완벽하지 않을 수 있음)
  - 예시 포함 (이미지 기반 UI/UX 명세 추출)

- `src/search/__init__.py` - Export 추가
  - SearchSettingsAdvancedPopup 추가
  - ScannerEngine 추가
  - RULES 추가
  - Docstring 업데이트

- `src/search/widget_search_frame.py` - 주석 추가 (최소 수정)
  - 고급 설정창 import 주석 추가
  - open_settings() 메서드에 문서화 주석 추가
  - 고급 설정창 사용 방법 안내

### 📊 통계

#### 파일 통계
- **신규 생성**: 7개 (UI 1, Python 3, 테스트 2, 문서 1)
- **수정**: 3개 (최소 변경, 주석 추가만)
- **백업**: 1개 (기존 작업 지시서)

#### 코드 통계
- **Python 코드**: ~500 lines
- **테스트 코드**: ~200 lines
- **UI XML**: ~400 lines
- **문서**: ~650 lines (work order v2)

#### 컴포넌트
- **UI 위젯**: 33개 (14 체크박스, 5 콤보박스, 12 스핀박스, 2 버튼)
- **Scanner 룰**: 4개 (RSI, Golden Cross, Volume, OHLC)
- **테스트**: 15개 (8 engine + 7 UI)

### 🎯 주요 기능

#### Scanner/Search 엔진
- ✅ 이미지 4개 기반 완전한 UI/UX 구현
- ✅ 고급 설정창 (33개 UI 컴포넌트)
- ✅ 비동기 스캔 엔진 (aiopyupbit 통합)
- ✅ 4가지 기본 룰 (확장 가능한 플러그인 시스템)
- ✅ 스코어링 및 랭킹 시스템
- ✅ 포괄적인 단위 테스트

#### 아키텍처
- **UI Layer**: SearchFrameWidget + Advanced Settings Dialog
- **Logic Layer**: ScannerEngine (async)
- **Rule Layer**: Pluggable rule system (RULES registry)
- **Data Layer**: aiopyupbit API

### 🔐 규칙 준수

- ✅ 기존 `.ui` 파일 수정 없음
- ✅ 기존 Python 로직 수정 없음 (주석만 추가)
- ✅ 모든 UI 텍스트 한글
- ✅ ERROR 레벨만 콘솔 출력
- ✅ 포괄적인 Docstring
- ✅ Type hints 사용

### 🚀 다음 단계

- Phase 6: PAPER 모드 구현
- Scanner 결과 MongoDB 저장
- Elasticsearch/Kafka 통합 (고급 기능)
- REST API 제공
- 웹 대시보드 (Streamlit)

---

## [문서화] 2~4단계 작업 지시서 업그레이드 및 자동화 - 2026-02-02

### ✅ 추가됨 (Added)
- `docs/phases/phase4_completion.md` - 4단계 완료 보고서
  - Compute 프로세스 완료 내용 상세 문서화
  - CandleAggregator, IndicatorEngine, ScannerExecutor 상세 설명
  - 검증 결과 및 성능 지표
  - 다음 단계 준비사항
  
- `work_order/문서_업데이트_프로세스.md` - 문서화 프로세스 가이드
  - 작업 전/중/후 문서화 표준 프로세스
  - 문서 불일치 방지 체크리스트
  - 단계별 진행 절차 (Phase 1~3)
  - 문서 작성 모범 사례 및 예시
  
- `scripts/verify_documentation.py` - 문서 검증 자동화 스크립트
  - 단계 지시서 메타데이터 검증
  - 완료 보고서 필수 섹션 확인
  - CHANGELOG 업데이트 여부 확인
  - 참조된 파일 실제 존재 여부 확인
  
- `docs/templates/completion_report_template.md` - 완료 보고서 템플릿
  - 단계별 완료 보고서 작성용 표준 템플릿
  - 필수 섹션 및 체크리스트 포함
  
- `.github/workflows/docs-validation.yml` - CI/CD 문서 검증 워크플로우
  - PR 생성 시 자동 문서 검증
  - 인코딩, 링크, 메타데이터 검증
  - 문서 불일치 발견 시 PR 차단

### 🔧 변경됨 (Changed)
- `work_order/2_단계_환경_구축_및_사전_준비.md` - v2.0으로 업그레이드 (4단계 수준 상세화)
  - **데이터 흐름 다이어그램 추가**:
    - 전체 시스템 아키텍처 (MongoDB, Redis, Kafka, Zookeeper, FastAPI)
    - 데이터 파이프라인 (Upbit WebSocket → Redis → MongoDB → GUI)
    - 서비스 간 의존성 및 시작 순서
    - 포트 매핑 테이블
  - **실제 파일 경로 명시**:
    - docker-compose.yml 실제 구성
    - .env.template 전체 환경변수
    - requirements.txt 의존성 목록
    - 초기화 스크립트 (init_kafka_topics.sh, init_mongodb.py)
  - **트러블슈팅 섹션 강화**:
    - 8가지 구체적 시나리오 (Docker 충돌, Python 의존성, .env 누락 등)
    - 각 시나리오별 증상, 원인, 진단, 해결 방법
    - 실행 가능한 명령어 예시 포함
    - 일반적인 디버깅 체크리스트
  - **검증 절차 상세화**:
    - 단계별 검증 명령어
    - 예상 출력 결과
    - 실패 시 대응 방법
    
- `work_order/3_단계_MONITOR_모드_안정화.md` - v2.0으로 업그레이드 (실제 구현 반영)
  - **데이터 흐름 명확화**:
    - MONITOR 모드 상세 데이터 파이프라인
    - GUI 컴포넌트별 데이터 흐름 다이어그램
    - WebSocket → Redis Pub/Sub → GUI Widgets 경로
  - **실제 구현 파일 경로 명시**:
    - src/gui/ui_state_manager.py - 모드 관리
    - src/gui/widgets/coin_list_widget.py - 실시간 코인 목록
    - src/gui/widgets/chart_widget.py - 실시간 차트
    - src/gui/widgets/orderbook_widget.py - 호가창
    - src/gui/widgets/trade_widget.py - 주문 UI (비활성화)
  - **검증 스크립트 사용법 추가**:
    - verify_monitor_mode.py 상세 사용법
    - 6가지 검증 항목 및 명령어
    - GUI 동작 확인 체크리스트
  - **실제 코드 예시 포함**:
    - UIStateManager 클래스 구현
    - TradeWidget 모드별 UI 제어
    - 주문 기능 비활성화 메커니즘
    
- `docs/DOCUMENTATION_STANDARDS.md` - v2.0으로 업그레이드
  - **자동화 도구 사용 가이드** 추가:
    - verify_documentation.py 사용법
    - CI/CD 워크플로우 설명
    - 완료 보고서 템플릿 사용법
  - **모범 사례 및 예시** 추가:
    - 좋은 문서 vs 나쁜 문서 비교
    - 실제 파일 경로 명시 예시
    - 실행 가능한 명령어 예시
    - 검증 방법 포함 예시
  - **재발 방지 체크리스트** 강화:
    - 단계 완료 시 필수 확인 사항
    - 검증 스크립트 실행 의무화

### 📝 문서화 (Documentation)
- **표준화된 문서 구조**:
  - docs/phases/ - 단계별 완료 보고서
  - docs/templates/ - 문서 템플릿
  - work_order/ - 작업 지시서 및 프로세스 가이드
  
- **문서 불일치 방지 시스템**:
  - 작업 전/중/후 체크리스트
  - 자동 검증 스크립트
  - CI/CD 파이프라인 통합
  
- **재사용 가능한 템플릿**:
  - 완료 보고서 템플릿
  - 메타데이터 표준 형식
  - 섹션 구조 가이드

### 🔍 검증 (Verification)
- ✅ `verify_documentation.py --all` 실행 통과 (2,3,4단계)
- ✅ 2단계 문서 검증 통과
- ✅ 3단계 문서 검증 통과
- ✅ 4단계 문서 검증 통과
- ✅ 메타데이터 검증 통과
- ✅ 참조 파일 경로 검증 통과 (일부 경고)

### 🎯 개선 효과
- **2~3단계 지시서 품질**: 추상적 설명 → 4단계 수준 구체성
- **문서 일관성**: 수동 관리 → 자동 검증 시스템
- **실수 방지**: 사후 대응 → 사전 예방 (CI/CD)
- **유지보수성**: 개별 노력 → 표준화된 프로세스

---

## [4단계] Compute 프로세스 데이터 집계 - 2026-02-02

### ✅ 추가됨 (Added)
- `scripts/verify_compute_process.py` - Compute 프로세스 검증 스크립트
- `docs/guides/compute_process_guide.md` - Compute 프로세스 사용자 가이드
- `docs/operations/compute_runbook.md` - Compute 프로세스 운영 가이드

### 🔧 변경됨 (Changed)
- `work_order/2_단계_환경_구축_및_사전_준비.md` - 실제 구현에 맞게 업데이트 (v1.2)
  - Docker Compose 실제 구성 반영 (MongoDB 7.0, Redis 7-alpine, Kafka 7.5.0)
  - .env.template 실제 내용 반영 (모든 환경변수 포함)
  - requirements.txt 실제 의존성 반영
  - 실제 검증 스크립트 추가 (init_kafka_topics.sh, init_mongodb.py)
  
- `work_order/4_단계_Compute_프로세스_데이터_집계.md` - Redis Pub/Sub 기반 실제 구현 반영 (v2.0)
  - Kafka 중심 이론 → Redis Pub/Sub 기반 실제 구현으로 완전 리팩토링
  - CandleAggregator 상세 설명 (O(1) 복잡도, 16+ 타임프레임, KST 시간대)
  - IndicatorEngine 상세 설명 (Welford's 알고리즘, 7개 지표)
  - ScannerExecutor 상세 설명 (AST 기반 안전한 표현식 평가, 200ms 마이크로배치)
  - ComputeProcess 통합 가이드 (멀티프로세싱, Redis Pub/Sub, MongoDB 저장)
  - 실제 성능 측정 결과 (<1ms per trade, <100MB for 1000 symbols)
  - 배포, 모니터링, 장애 대응 가이드 추가

### 📝 문서화 (Documentation)
- **CandleAggregator 상세 문서:**
  - O(1) 복잡도 달성 원리 (증분 업데이트, 재계산 없음)
  - 16+ 타임프레임 지원 (tick, sec, min, hour, day, week, month, year)
  - KST 시간대 처리 (pytz 라이브러리 사용)
  - 사용 예시 및 메트릭스 조회
  
- **IndicatorEngine 상세 문서:**
  - Welford's 온라인 알고리즘 설명 (분산, 표준편차 O(1) 계산)
  - EMA/SMA 증분 계산 방식
  - 7개 주요 지표 (RSI, MACD, Bollinger Bands, EMA, SMA, ATR, Stochastic)
  - 사용 예시 및 지표 해석 가이드
  
- **ScannerExecutor 상세 문서:**
  - AST 기반 안전한 표현식 파싱
  - 200ms 마이크로배치 실행
  - 델타 전송 (add/remove)
  - 조건식 예시 및 보안 정책
  
- **ComputeProcess 통합 가이드:**
  - 멀티프로세싱 구조 및 생명주기
  - Redis Pub/Sub 채널 (구독: md.events, 발행: candle.events, indicator.events)
  - MongoDB 저장 스키마 및 인덱스
  - 배포 및 검증 방법
  
- **성능 및 모니터링:**
  - 실제 벤치마크 결과 (tests/test_compute.py)
  - Prometheus 메트릭스 엔드포인트
  - 헬스체크 엔드포인트
  - 로그 구조 (JSON structured logging)
  - 주요 모니터링 지표 및 알림 규칙
  
- **장애 대응:**
  - 재시작 시 복구 전략
  - 중복 방지 (MongoDB unique 인덱스)
  - 누락 방지 (Redis Pub/Sub 재연결)
  - 데이터 정합성 검증

### ✅ 검증됨 (Verified)
- CandleAggregator 정확성 검증 (틱봉, 초봉, 분봉, 시간봉, 일봉)
- IndicatorEngine 정확성 검증 (RSI, MACD, EMA, SMA, Bollinger Bands)
- 성능 벤치마크 (< 1ms per trade)
- 메모리 사용량 (< 100MB for 1000 symbols)
- O(1) 복잡도 유지 확인

### 🎯 개선 사항
- 이론적 Kafka 중심 내용 → 실제 Redis Pub/Sub 기반 구현 반영
- 추상적 설명 → 구체적인 코드 예시 및 사용법
- 누락된 상세 설명 → 완전한 기술 문서 (CandleAggregator, IndicatorEngine, ScannerExecutor)
- 간략한 운영 가이드 → 포괄적인 운영 런북 (시작/종료, 모니터링, 장애 대응, 백업/복구)

---

## [2-3단계 통합] 환경 구축 및 MONITOR 모드 안정화 - 2026-02-02

### ✅ 추가됨 (Added)

#### 2단계: 환경 구축
- `scripts/init_kafka_topics.sh` - Kafka 토픽 자동 초기화 스크립트
- `scripts/init_mongodb.py` - MongoDB 컬렉션 및 인덱스 자동 생성 스크립트
- `.github/workflows/ci.yml` - CI/CD 파이프라인

#### 3단계: MONITOR 모드 안정화
- `scripts/verify_monitor_mode.py` - MONITOR 모드 검증 스크립트
- `docs/guides/monitor_mode_guide.md` - MONITOR 모드 사용자 가이드
- `docs/operations/runbook.md` - 운영 런북

#### 문서 표준화
- `docs/DOCUMENTATION_STANDARDS.md` - 문서화 표준 가이드
- `docs/PHASES_INDEX.md` - 전체 단계 인덱스
- `docs/phases/README.md` - phases 폴더 안내
- `docs/phases/phase2_completion.md` - 2단계 완료 보고서 (통합본)
- `docs/phases/phase3_completion.md` - 3단계 완료 보고서

### 🔧 개선됨 (Improved)
- 문서 구조 표준화 (`docs/phases/`, `docs/guides/`, `docs/operations/`)
- 단계별 문서 통합 관리 체계 수립
- 파일명 규칙 통일

### 📝 문서화 (Documentation)
- 2단계 작업 내용 상세 문서화
- 3단계 작업 내용 상세 문서화
- MONITOR 모드 사용자 가이드
- 운영 절차 표준화
- 장애 대응 시나리오 문서화
- 백업/복구 절차 문서화

### ✅ 검증됨 (Verified)
- Docker Compose 환경 구성 확인
- Kafka/MongoDB 초기화 스크립트 동작 확인
- MONITOR 모드 기본 동작 확인
- 주문 기능 비활성화 확인
- 데이터 수집 정상 동작 확인

### 🔒 재발 방지 (Prevention)
- 문서화 표준 가이드 생성
- 폴더 구조 규칙 명시
- 파일명 규칙 정의
- Git 작업 체크리스트 제공

---

## [이전 2단계] 환경 구축 및 사전 준비 - 2026-02-02

### ✅ 추가됨 (Added)
- `scripts/init_kafka_topics.sh` - Kafka 토픽 자동 초기화 스크립트
- `scripts/init_mongodb.py` - MongoDB 컬렉션 및 인덱스 자동 생성 스크립트
- `.github/workflows/ci.yml` - CI/CD 파이프라인 (환경 검증, 문서 검증, 코드 품질, 테스트 자동화)
- `docs/phase2_completion_summary.md` - 2단계 완료 요약 문서

### 🔧 변경됨 (Changed)
- `work_order/2_단계_환경_구축_및_사전_준비.md` - 완료 표시 추가

### 📝 문서화 (Documentation)
- 2단계 작업 완료 상태 문서화
- 스크립트 사용법 및 주의사항 문서화
- CI/CD 파이프라인 설정 문서화

### ✅ 검증됨 (Verified)
- Docker Compose 환경 구성 확인
- 필수 스크립트 동작 확인
- Phase 2 검증 스크립트 통과

---

## [이전 버전]
- 2026-01-31 | 루트 README.md 재작성
- 2026-01-31 | 문서 표준화 작업
