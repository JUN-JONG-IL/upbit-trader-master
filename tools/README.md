# tools/ — 테스트 및 스크립트 통합 디렉토리

## 개요

`tools/` 디렉토리는 프로젝트의 테스트 및 유지보수 스크립트를 통합 관리합니다.
이전에 루트에 분산되어 있던 `tests/`와 `scripts/` 폴더를 이 디렉토리로 통합하였습니다.

## 디렉토리 구조

```
tools/
├── tests/                   # 단위·통합·E2E 테스트 (이전 루트 tests/)
│   ├── 01_core/             # 핵심 모듈 테스트 (DI 컨테이너, 이벤트 버스)
│   ├── 02_data/             # 데이터 모듈 테스트 (MongoDB URI 등)
│   ├── app/                 # 앱 UI 테스트 (headless PyQt5 스텁 사용)
│   ├── unit/                # 기타 단위 테스트
│   ├── integration/         # 통합 테스트
│   ├── e2e/                 # E2E 테스트
│   └── test_pipeline.py     # 데이터 파이프라인 단위 테스트
└── scripts/                 # 유지보수·배포 스크립트 (이전 루트 scripts/)
    ├── automation/          # 자동화 워크플로우 스크립트
    ├── deployment/          # 배포 스크립트
    └── tools/               # 검증 및 진단 도구
```

## 테스트 실행

### 전체 테스트 실행
```bash
# 프로젝트 루트에서 실행
python -m pytest tools/tests/ -v

# 앱 UI 테스트 제외 (headless 환경)
python -m pytest tools/tests/ --ignore=tools/tests/app -v
```

### 모듈별 테스트 실행
```bash
# 핵심 모듈 테스트
python -m pytest tools/tests/01_core/ -v

# 데이터 모듈 테스트
python -m pytest tools/tests/02_data/ -v

# 파이프라인 테스트
python -m pytest tools/tests/test_pipeline.py -v
```

## 스크립트 실행

### 자동화 스크립트
```bash
# N단계 워크플로우 실행 (예: 2단계)
python tools/scripts/automation/auto_workflow.py --stage 2

# 환경 점검
python tools/scripts/automation/env_check.py

# Import 오류 점검
python tools/scripts/check_imports.py
```

### 배포 스크립트
```bash
# 스테이징 배포 (Linux/macOS)
bash tools/scripts/deployment/deploy_stage.sh

# 스테이징 배포 (Windows)
tools/scripts/deployment/deploy_start.bat
```

## 주의사항

1. **테스트 경로**: 루트의 `conftest.py`는 pytest rootdir에서 자동 로드됩니다.
2. **상대 경로**: 각 테스트의 conftest.py는 `tools/tests/` 기준 상대 경로를 사용합니다.
3. **PyQt5 의존성**: `tests/app/` 테스트는 headless 스텁을 사용하므로 PyQt5 미설치 환경에서도 실행 가능합니다.
4. **환경변수**: DB 연결 테스트는 `.env` 또는 환경변수 설정이 필요합니다.
