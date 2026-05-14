# CHANGELOG
# 2026-01-31 | Copilot | 변경: 루트 README.md 재작성 — 파일/폴더별 목적, 사용법, 실행방법 및 주의사항을 README_작성_가이드.md 기준으로 상세 기술. 영향: 루트 문서. 테스트: 로컬 문서 검토.

Version: v2.0
Last Modified: 2026-01-31 | Copilot
References:
 - work_order/README_작성_가이드.md
 - work_order/규칙.md
 - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md

요약 (한 줄)
- 이 파일은 프로젝트 루트의 파일과 폴더를 대상으로 한 상세 README 입니다. 각 항목에 대해 목적, 즉시 사용할 수 있는 사용 예(명령어/코드), 그리고 주의사항(민감정보, STAGE_LOCKED, LIVE 모드 관련)을 빠짐없이 기술합니다. 하위 폴더 내부 파일 목록은 포함하지 않습니다.

중요 안내 (먼저 읽을 것)
1. work_order/규칙.md 및 work_order/README_작성_가이드.md를 먼저 읽으십시오. 이 문서의 형식과 변경 규칙을 따릅니다.
2. "앱 기능 변질 금지(P1)" 원칙을 준수하십시오. 기존 파일/스크립트의 입출력, 데이터 포맷, API 계약을 변경하지 마십시오.
3. 민감한 인증정보(API 키 등)는 환경변수 또는 OS별 시크릿 매니저에 보관하고 절대 리포지토리에 하드코딩하지 마십시오.

목차
- 문서 구조
- 개요
- 루트 파일/폴더 상세 설명 (각 파일별 목적, 사용법, 주의사항)
- 개발 환경 설정 및 실행방법 (로컬 / Docker)
- 테스트 및 린트 명령
- 자동화 도구(문서 검사) 사용법
- 배포/실거래(주의)
- 변경 이력 및 롤백
- 다음 작업 제안

## 📚 문서 구조

### 핵심 문서
- **[work_order/](./work_order/)** - 단계별 작업 지시서 및 핵심 규칙
  - [규칙.md](./work_order/규칙.md) - 절대 규칙 (필독) ⭐
  - [통합_개발_가이드.md](./work_order/통합_개발_가이드.md) - 통합 개발 가이드
  
### 개발자 가이드
- **[docs/development/](./docs/development/)** - 개발 표준 및 가이드
  - [코딩 표준](./docs/development/CODING_STANDARDS.md) - DRY, 네이밍, 타입힌트 등
  - [파일 구조](./docs/development/FILE_STRUCTURE.md) - 폴더 구조, 파일명 규칙
  - [프로세스 아키텍처](./docs/development/PROCESS_ARCHITECTURE.md) - GUI/WS/Compute 프로세스 구조
  - [로깅 가이드](./docs/development/LOGGING_GUIDE.md) - 로그 레벨, 에러 처리
  - [UI/UX 가이드라인](./docs/development/UI_UX_GUIDELINES.md) - Qt Designer 사용, 디자인 원칙
  - [임포트 규칙](./docs/development/IMPORT_GUIDELINES.md) - 임포트 경로 규칙 ⚠️
  
### 임포트 규칙 ⚠️
- **`src.` 접두사 사용 금지**
- 모든 `src/` 내부 모듈은 직접 임포트
- 예: `from ai.model_registry import ModelRegistry`
- 자동 검증: `python tools/scripts/check_imports.py`
- 상세: [docs/development/IMPORT_GUIDELINES.md](./docs/development/IMPORT_GUIDELINES.md)
  
### 인프라 가이드
- **[docs/infrastructure/](./docs/infrastructure/)** - 시스템 인프라 가이드
  - [데이터베이스](./docs/infrastructure/DATABASE.md) - MongoDB 사용, 스키마 규칙
  - [WebSocket](./docs/infrastructure/WEBSOCKET.md) - 실시간 통신 규칙
  - [API 통신](./docs/infrastructure/API.md) - REST API 호출 규칙
  - [캔들 집계](./docs/infrastructure/CANDLE_AGGREGATION.md) - 캔들 데이터 처리
  
### 운영 가이드
- **[docs/operations/](./docs/operations/)** - 운영 및 배포 가이드
  - [주문 처리](./docs/operations/ORDER_PROCESSING.md) - 주문 로직, 리스크 관리
  - [운영 모드](./docs/operations/OPERATING_MODES.md) - MONITOR/PAPER/LIVE 모드
  - [테스트](./docs/operations/TESTING.md) - 테스트 전략 및 커버리지
  - [배포](./docs/operations/DEPLOYMENT.md) - 배포 절차 및 체크리스트
  - [보안](./docs/operations/SECURITY.md) - 보안 규칙 및 민감정보 관리
  
### 자동화 도구
- **[automation/](./automation/)** - 자동화 스크립트 및 가이드
  - [워크플로우 완전 가이드](./automation/WORKFLOW_COMPLETE_GUIDE.md) - N단계 자동화
  - [테스트 가이드](./automation/TEST_GUIDE.md) - 자동 테스트 실행
  - [자동화 규칙](./docs/automation/AUTOMATION_RULES.md) - 자동화 워크플로우 규칙

### 자동 수정 시스템
- **[docs/AUTO_FIX_GUIDE.md](./docs/AUTO_FIX_GUIDE.md)** - 자동 오류 수정 가이드
  - Git hooks를 통한 자동 문서 수정
  - 깨진 참조 자동 수정
  - 누락된 메타데이터 자동 추가
  - Missing 모듈 자동 생성
  - GitHub Actions 자동 수정 워크플로우

## 🚀 빠른 시작

### 규칙 확인 (필수)
작업 시작 전 반드시 읽어야 할 문서:
```bash
# 핵심 규칙 (필독)
cat work_order/규칙.md
```

### 자동화 워크플로우
```bash
# N단계 작업 시작 (예: 2단계)
./start_stage.sh 2

# 또는 Python으로 직접 실행
python automation/auto_workflow.py --stage 2
```

### Git Hooks 설치 (권장)
자동 문서 오류 수정을 위한 Git hooks 설치:
```bash
# 자동 수정 hooks 설치
bash tools/scripts/install_hooks.sh

# 또는 기존 hooks 설치 (호환성)
bash tools/scripts/setup_hooks.sh
```

개요
- 본 레포지토리는 Upbit 거래용 트레이더 프레임워크(연구/검증/모니터/페이퍼/라이브 전환을 지원)를 포함합니다. 루트에는 CI/실행 스크립트, 문서(Phase2 관련 리포트), 핵심 실행 진입점(src 폴더), 자동 검증 스크립트 및 work_order(작업 지침)가 위치합니다.

루트 파일/폴더 상세 설명
- .dockerignore
  - 목적: Docker 빌드 컨텍스트에서 제외할 파일/폴더 목록. 빌드 속도 및 이미지 크기 최적화.
  - 사용법: Docker 이미지를 빌드할 때 Docker 데몬이 자동으로 참조합니다. (예: docker build -t upbit-trader:latest .)
  - 주의사항: 민감정보(예: .env)를 포함하지 않도록 구성되어 있는지 확인.

- .gitattributes
  - 목적: Git에서 파일별 속성(라이트엔딩, diff 등) 설정.
  - 사용법: 기본적으로 Git이 자동으로 사용. 수정 시 팀 합의 필요.
  - 주의사항: 라인엔딩 변경은 많은 파일에 영향을 미치므로 신중히 변경하십시오.

- .gitignore
  - 목적: 버전관리에서 제외할 파일/패턴 명시(가상환경, 빌드 아티팩트 등).
  - 사용법: git이 자동으로 적용. 새 항목 추가 시 팀 정책에 따라 커밋 전 리뷰 권장.
  - 주의사항: API 키/시크릿이 .gitignore에 포함되어 있더라도 이미 커밋된 경우 제거 절차 필요.

- .vscode/ (폴더)
  - 목적: 권장 VS Code 설정(런처, 확장, 작업 등).
  - 사용법: 개발자가 VS Code 사용 시 해당 설정을 자동으로 로드합니다.
  - 주의사항: 개인 설정과 충돌할 수 있으므로 커밋 전 검토하십시오.

- 2.0.2
  - 목적: 릴리스 태그/버전 정보를 간단히 표기한 파일(레포 관리용).
  - 사용법: 사람이 읽는 용도, 배포 스크립트에서 참조하지 않음(필요 시 스크립트에서 읽도록 변경).
  - 주의사항: 수동 변경 시 버전 정책을 준수하십시오.

- Dockerfile
  - 목적: Docker 이미지를 빌드하기 위한 정의 파일.
  - 사용법: docker build -t upbit-trader:2.0.2 .
  - 주의사항: 빌드 과정에서 민감정보를 --build-arg로 전달하지 마십시오. 실행 시 환경변수로 주입하십시오.

- LICENSE
  - 목적: 프로젝트 사용/배포에 관한 라이선스 명시.
  - 사용법: 프로젝트 사용 전 라이선스 내용을 숙지하십시오.
  - 주의사항: 라이선스 요구사항을 위반하지 않도록 외부 재배포 전 검토하십시오.

- PHASE2_COMPLETION_REPORT.md
  - 목적: Phase2 개발 완료 보고서 — 구현 범위, 주요 결정사항, 테스트 결과 요약을 포함.
  - 사용법: 프로젝트 상태 파악 및 리뷰용으로 열람.
  - 주의사항: 운영환경 전환 관련 결정사항이 포함되어 있을 수 있으니 실거래 전 반드시 확인하십시오.

- PHASE2_IMPLEMENTATION_GUIDE.md
  - 목적: Phase2의 세부 구현 가이드(설계도, 데이터 흐름, 설정 방법).
  - 사용법: 구현/배포/테스트 시 참고 매뉴얼로 사용.
  - 주의사항: 이 문서에서 제시하는 설정은 코드와 일치해야 합니다. 문서와 코드 불일치 시 우선순위를 문서화하고 수정절차를 따르십시오.

- README.md (현재 파일)
  - 목적: 레포지토리 최상단 요약 및 루트 항목 설명(이 문서).
  - 사용법: 프로젝트 진입 시 첫 참조 문서로 사용.
  - 주의사항: 이 파일은 work_order/README_작성_가이드.md 규격을 따릅니다. 구조 변경 시 가이드에 맞춰 업데이트하십시오.

- SECURITY_SUMMARY.md
  - 목적: 보안 관련 요약(리스크, 민감정보 관리, 권장 설정).
  - 사용법: 배포 전 및 보안 검토 시 참고.
  - 주의사항: 실거래 모드(LIVE)로 전환 전 보안 체크리스트를 반드시 통과하십시오.

- assets/ (폴더)
  - 목적: 문서/대시보드에 사용되는 이미지, 아이콘, 샘플 리소스 보관.
  - 사용법: 문서 또는 UI에서 사용.
  - 주의사항: 큰 파일은 CI 빌드에 부정적 영향을 줄 수 있으니 관리요망.

- base/ (폴더)
  - 목적: 베이스 템플릿, 공통 설정 또는 샘플 구성 파일 보관(프로젝트 전반 재사용).
  - 사용법: 새로운 서비스/이미지 구성 시 템플릿으로 사용.
  - 주의사항: 템플릿 수정 시 다른 구성에 영향이 있으므로 변경 로그 기록 필요.

- docker-compose.yml
  - 목적: Docker Compose로 개발/통합 테스트용 서비스를 띄우기 위한 구성.
  - 사용법:
    - docker compose up --build -d
    - 서비스별 로그: docker compose logs -f <service>
  - 주의사항: 환경변수 파일(.env)을 사용해 민감정보를 주입하십시오. 로컬 테스트용 구성과 프로덕션 구성을 분리하십시오.

- requirements.txt
  - 목적: 런타임 의존 패키지 ��록.
  - 사용법: pip install -r requirements.txt
  - 주의사항: 개발용 의존성은 requirements-dev.txt로 분리되어 있어야 합니다. 버전 고정을 권장합니다.

- tools/ (폴더)
  - 목적: 도구 스크립트(문서 검사, 자동화 지원 스크립트 등) 및 테스트 통합.
  - 사용법: 예: python tools/scripts/automation/doc_updater.py (레포 문서 검사, 드라이런)
  - 주의사항: tools 내부 스크립트는 일반적으로 로컬에서 직접 실행됩니다. 실행 전 가상환경을 활성화하고 필요 권한을 확인하십시오.

- scripts_doc_check_report_2026-01-30.json
  - 목적: scripts/doc_check.py 실행 결과 리포트(2026-01-30 시점).
  - 사용법: 결과 분석용(변경 필요/권장 사항 확인).
  - 주의사항: 오래된 리포트일 수 있으니 최신 실행을 권장합니다.

- setup.py
  - 목적: 패키지 메타데이터 및 설치 스크립트(파이썬 패키지화 지원).
  - 사용법: pip install . 또는 python setup.py sdist bdist_wheel (비권장: 현재 pip 방식 권장)
  - 주의사항: 배포 패키지의 의존성은 requirements.txt와 일치해야 합니다.

- src/ (폴더) — v3.0 번호 카테고리 구조
  - 목적: 애플리케이션 소스코드의 루트(트레이딩 엔진, 데이터 파이프라인, API 클라이언트 등).
  - v3.0 구조:
    - src/01_core/   — auth, config, utils, base
    - src/02_data/   — data, db, features
    - src/03_market/ — market, orderbook
    - src/04_chart/  — chart
    - src/05_strategy/ — strategy
    - src/06_ai/     — ai_engine, prediction, models, rl, detection, prompt
    - src/07_scanner/ — scanner
    - src/08_portfolio/ — portfolio, userinfo
    - src/09_sentiment/ — sentiment
    - src/10_trade/  — trade, signals
    - src/11_server/ — server, settings, ui, component
    - src/12_realtime/ — 실시간 데이터 스트리밍 (component, workers, ui)
    - src/13_compute/ — 계산 엔진 (compute, aggregation, workers)
    - src/app/       — 진입점 (변경 없음)
    - src/styles/    — QSS 스타일 (변경 없음)
  - 임포트: src/app/main.py가 sys.path에 번호 디렉토리를 모두 추가하므로 기존 임포트 변경 불필요.
  - 마이그레이션 안내: docs/MIGRATION_V3_FINAL.md 참조.
  - 주의사항: 비즈니스 로직/화면/UI 분리는 work_order 규칙(P2)을 준수하십시오. src 내부 파일은 변경 시 테스트와 타입체크를 반드시 수행하십시오.

## 📁 프로젝트 구조

### 핵심 모듈 (src/)
- `01_core/` - 인증, 설정, 유틸리티
- `02_data/` - TimescaleDB, Redis, MongoDB 연동
- `03_market/` - 시장 데이터 (코인리스트, 호가창, 체결)
- `04_chart/` - 차트 엔진, AI 차트
- `05_strategy/` - 전략, 백테스트
- `06_ai/` - AI 엔진, 예측 모델
- `07_scanner/` - 조건 스캐너
- `08_portfolio/` - 포트폴리오, 사용자정보
- `09_sentiment/` - 감성 분석

### 데이터베이스 설계
자세한 내용은 [work_order/DB설계.md](work_order/DB설계.md) 참조.

### 📊 포트 매핑 (4-Tier 아키텍처)

| Tier | 서비스 | 컨테이너 포트 | 호스트 포트 | 용도 |
|------|--------|:------------:|:-----------:|------|
| 🔴 Tier 1 | Redis | 6379 | **58530** | 실시간 캐시 |
| 🟡 Tier 2 | TimescaleDB | 5432 | **58529** | 시계열 DB |
| 🟠 Tier 3 | MongoDB | 27017 | 27017 | 메타데이터 |
| 🟠 Tier 3 | PostgreSQL Primary | 5432 | 5433 | CQRS 쓰기 |
| 🟠 Tier 3 | PostgreSQL Replica | 5432 | 5434 | CQRS 읽기 |
| 🔵 Tier 4 | Zookeeper | 2181 | 2181 | Kafka 코디네이터 |
| 🔵 Tier 4 | Kafka | 9092 | 9092 | 이벤트 스트림 |
| 🔵 Tier 4 | ClickHouse HTTP | 8123 | 8123 | OLAP HTTP |
| 🔵 Tier 4 | ClickHouse Native | 9000 | 9000 | OLAP TCP |

## 🖥️ 서버 (FastAPI)

Upbit Trader 플랫폼은 FastAPI 기반 REST API·WebSocket 서버를 제공합니다.

### 서버 기능 개요
- REST API: 캔들, 심볼, 주문 조회·생성 (`/api/v1/`)
- WebSocket: 실시간 캔들·호가창 스트리밍
- JWT 인증 + Redis Rate Limit
- Prometheus metrics (`/metrics`)

### 서버 실행 방법

```bash
# 개발 모드 (핫 리로드)
uvicorn src.11_server.core.fastapi_app:create_app --factory \
    --host 0.0.0.0 --port 8000 --reload

# Swagger UI
# http://localhost:8000/docs
```

### 주요 설정 (환경 변수)

```env
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
JWT_SECRET_KEY=your-secret-key
REDIS_HOST=localhost
TIMESCALE_DSN=postgresql+asyncpg://user:pass@localhost:5432/upbit_trader
```

> 📖 상세 문서: **[src/11_server/README.md](src/11_server/README.md)**

- tools/ (폴더)
  - 목적: 테스트 및 유지보수 스크립트 통합 디렉토리 (구 tests/, scripts/ 통합).
  - 사용법: 자세한 내용은 tools/README.md 참조.
  - tools/tests/    — pytest 기반의 단위/통합 테스트 (구 루트 tests/)
  - tools/scripts/  — 유지보수·배포·자동화 스크립트 (구 루트 scripts/)

- tests/ (폴더)
  - 목적: pytest 기반의 단위/통합 테스트 소스 보관.
  - 사용법: python -m pytest tools/tests/ -q
  - 주의사항: 테스트는 실제 거래소 API 호출을 하지 않도록 모킹 또는 페이퍼 모드 환경을 사용하십시오.

- verify_phase2.py
  - 목적: Phase2 구현 검증 리포트 생성 스크립트(레포 전반 검사).
  - 사용법: python verify_phase2.py
  - 주의사항: 실행 시 의존성(requirements-dev.txt)을 설치하고, 스크립트가 로컬 환경 파일을 수정하는지 확인하십시오.

- verify_phase2_implementation.py
  - 목적: Phase2 특정 구현 세부 검증 및 체크리스트 스크립트.
  - 사용법: python verify_phase2_implementation.py
  - 주의사항: 스크립트가 변경 가능한 파일을 자동으로 수정하지 않는지(드라이런 기본), 수정 시 백업이 생성되는지 확인하십시오.

- verify_phase2_report.json
  - 목적: verify_phase2.py의 결과물(검증 리포트).
  - 사용법: 사람이 읽거나 자동 파싱용.
  - 주의사항: 최신 리포트가 아닐 수 있으니 필요 시 재생성하십시오.

- work_order/ (폴더)
  - 목적: 단계별(1~23) 개발·배포 가이드와 README_작성_가이드.md 및 규칙.md 등 운영 문서 보관.
  - 사용법: 단계별 작업/검증 순서와 STAGE_LOCKED 정책을 따르며 문서를 참조해 작업을 진행하십시오.
  - 주의사항: work_order 내부 문서는 자동화 규칙과 STAGE_LOCKED 정책을 포함합니다. 전 단계 파일을 무단 변경하지 마십시오.

개발 환경 설정 (로컬 권장)
1. Python 가상환경 생성 및 활성화
   - Windows (PowerShell):
     - python -m venv .venv
     - .\.venv\Scripts\Activate.ps1
   - macOS / Linux:
     - python3 -m venv .venv
     - source .venv/bin/activate

2. 의존성 설치
   - pip install -r requirements.txt
   - (개발용) pip install -r requirements-dev.txt

3. 코드 스타일/타입/보안 검사
   - black --check .
   - flake8
   - mypy .
   - bandit -r .

4. 테스트 실행
   - python -m pytest tools/tests/ -q

Docker 사용 (개발/통합 테스트)
- 이미지 빌드
  - docker build -t jun-jong-il/upbit-trader:latest .
- Compose 기반 서비스 실행(예: 로컬 통합)
  - docker compose up --build -d
- 주의사항: Compose 파일 내 환경변수(.env)로 API 키를 주입하십시오. 이미지에 키를 직접 포함시키지 마십시오.

스크립트(문서 검사 및 자동 보완)
- 문서 검사(드라이런)
  - python tools/scripts/doc_check.py
- 문서 검사(적용)
  - python tools/scripts/doc_check.py --apply
- 권장: CI에서 scripts/doc_check.py를 dry-run으로 먼저 실행하고, 합격 시 apply 단계는 일괄 PR로 처리하십시오.

실거래(LIVE) 모드 관련 주의사항
- 실거래 전 필수 체크리스트:
  - work_order/규칙.md 확인 및 변경 로그 기록
  - SECURITY_SUMMARY.md의 권장 보안 항목 충족
  - 테스트(단위/통합) 모두 통과
  - STAGE_LOCKED 토큰이 설정된 파일이 있는지 확인(해제 필요 시 문서화 + 승인)
- 민감정보 관리:
  - API 키는 OS 시크릿 매니저 또는 CI/CD 시크릿으로 관리하세요.
  - 절대 리포지토리(심지어 테스트 브랜치)에도 커밋하지 마십시오.

변경 이력 및 롤백
- 자동 변경 시:
  - 원본과 변경본은 docs/previous_stages/ 에 저장됩니다.
  - work_order/규칙.md에 changelog 항목이 추가됩니다.
- 롤백 방법:
  - git checkout <원본 SHA> -- <파일 경로>
  - 또는 docs/previous_stages/에 저장된 원본 사용
- 권장: 변경 전 반드시 git rev-parse --short HEAD로 체크포인트 SHA를 캡처하십시오.

빠른 명령 모음
- 리포지토 클론:
  - git clone https://github.com/JUN-JONG-IL/upbit-trader-master.git
- 가상환경 및 의존성:
  - python -m venv .venv
  - source .venv/bin/activate
  - pip install -r requirements.txt
- 코드 포맷 / 타입 / 보안 / 테스트:
  - black --check .
  - flake8
  - mypy .
  - bandit -r .
  - python -m pytest tools/tests/ -q
- 문서 검사:
  - python tools/scripts/doc_check.py
  - python tools/scripts/doc_check.py --apply

추가 권장 CI (복사하여 사용)
- .github/workflows/validate-and-upgrade.yml (권장)
  - docs-validate → tests → prev-stage-upgrade 순서로 검증을 자동화하십시오.
  - GitHub Actions에서 GITHUB_TOKEN을 사용해 docs 자동 적용 단계 권한을 부여할 수 있습니다.

자주 묻는 질문 (간단)
- Q: API 키는 어디에 저장하나요?
  - A: 환경변수 또는 OS의 시크릿 매니저를 사용하세요. CI는 Secrets를 사용합니다.
- Q: scripts/doc_check.py가 파일을 변경하나요?
  - A: 기본은 드라이런입니다. --apply 플래그로 실제 변경이 적용됩니다. 변경 시 docs/previous_stages에 백업이 생성됩니다.
- Q: 실거래 전 어떤 검증을 해야 하나요?
  - A: SECURITY_SUMMARY.md, work_order/규칙.md의 체크리스트, 테스트 통과(테스트 환경이 라이브 API 호출하지 않도록 모킹 필요).

마무리 — 권장 다음 단계
- 우선 순위로 작성해야 할 README.md (다음 작업 제안):
  1) work_order/README.md — work_order 폴더의 목적, 단계별 요약, 상단 헤더 템플릿 및 STAGE_LOCKED 규칙을 포함한 상세 README
  2) src/README.md — 소스 구조 설명, 주요 모듈/진입점, 개발자 작업 흐름
  3) tools/README.md — 테스트 및 스크립트 통합 내용 설명

저장/검증 체크포인트
- 현재 커밋 SHA 확인: git rev-parse --short HEAD
- 문서 검사(드라이런): python tools/scripts/doc_check.py

끝