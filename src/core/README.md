# src/core 폴더

## 목적
upbit-trader 플랫폼의 **핵심 인프라 및 공통 모듈**을 제공합니다.

## 폴더 구조

```
src/core/
├── auth/           # 인증 및 로그인
├── base/           # 기본 인프라 (이벤트 루프 등)
├── config/         # 설정 관리 (구 root config/ 포함)
├── lib/            # 핵심 라이브러리 (구 root lib/)
└── utils/          # 공통 유틸리티
```

## 각 폴더 설명

### auth/ - 인증 및 로그인
사용자 인증, 세션 관리, 2FA 등을 담당합니다.

**구조**:
- `services/`: 비즈니스 로직 (AuthService, SessionManager, TwoFactorAuth)
- `ui/`: 로그인 화면 UI (LoginWidget, login.ui)

**사용 예시**:
```python
from auth import gui_main, AuthService

# GUI 로그인 실행
gui_main()

# 서비스 직접 사용
auth_service = AuthService()
auth_service.authenticate(username, password)
```

### base/ - 기본 인프라
플랫폼 전역에서 사용하는 기본 인프라를 제공합니다.

**주요 기능**:
- `event_loop.py`: asyncio 이벤트 루프 관리 (Windows SelectorEventLoopPolicy 설정)

**사용 예시**:
```python
from base import setup_event_loop, get_event_loop

# 앱 시작 시 한 번만 호출
setup_event_loop()

# 이벤트 루프 가져오기
loop = get_event_loop()
```

### config/ - 설정 관리
YAML 기반 설정 파일 로딩 및 관리를 담당합니다.

**주요 파일**:
- `config.yaml`: 실제 설정 파일 (Git 제외)
- `config.yaml.example`: 설정 템플릿
- `loader.py`: 설정 로딩 로직

**사용 예시**:
```python
from config import load_config

config = load_config()
upbit_key = config['UPBIT']['ACCESS_KEY']
```

### lib/ - 핵심 라이브러리
MongoDB/Redis/SQLAlchemy 통합 IO 핸들러 및 핵심 라이브러리를 제공합니다.

**주요 모듈**:
- `db_handler.py`: DBHandler 클래스 (MongoDB/Redis/SQLAlchemy 통합, dask/Polars 지원)

**사용 예시**:
```python
from lib import DBHandler

db = DBHandler(ip="localhost", port=27017)
inserted_id = await db.insert_item_one(data, "candles", "KRW-BTC_minute_1")
result = await db.find_item_one({"symbol": "KRW-BTC"}, "candles", "KRW-BTC_minute_1")
```

### utils/ - 공통 유틸리티
플랫폼 전역에서 사용하는 유틸리티 함수/클래스를 제공합니다.

**주요 모듈**:
- `logger.py`: JSON 구조화 로깅
- `debounce.py`, `throttle.py`: 함수 실행 제어
- `metrics_lite.py`: 경량 메트릭스 수집
- `compute/`: 기술적 지표 계산 엔진
- `metrics/`: Prometheus 메트릭스 export

**사용 예시**:
```python
from utils import get_logger, debounce, throttle
from utils.compute import IndicatorEngine

logger = get_logger()

@debounce(300)  # 300ms debounce
def on_resize():
    logger.info("Resized")
```

## 개발 가이드

### 폴더 네이밍 규칙
- 숫자 prefix 유지: `core`, `data_01`, ...
- 명확한 단수/복수 구분: `auth` (단일 개념), `utils` (복수 유틸리티)

### import 경로
- 절대 import 사용: `from auth import ...`
- 상대 import 금지 (테스트 제외)

### 하위 호환성
- 기존 import 경로 유지 필수
- `__init__.py`에서 re-export로 보장

## 확장 계획
- `validation/`: 입력 검증 모듈
- `security/`: 보안 유틸리티 (암호화, 해시 등)

---

**작성**: Copilot Workspace Refactor
**날짜**: 2026-03-05
