# 02_data — 데이터 계층

## 목적

Upbit 트레이딩 시스템의 통합 데이터 접근 계층입니다.  
시계열 저장, 캐싱, 문서 저장, AI/ML 피처 엔지니어링을 담당합니다.

## 구조

```
src/02_data/
├── timescale/      # TimescaleDB — 캔들/거래 시계열 데이터
├── redis/          # Redis — L1 캐시, pub/sub, gap-fill 큐
├── mongodb/        # MongoDB — 주문·설정·포지션 문서 저장
├── features/       # Feature store — AI/ML 피처 엔지니어링
├── pipeline/       # 10단계 데이터 수집 파이프라인 (구 src/data_pipeline/)
├── clients/        # 데이터베이스 클라이언트 (구 src/db/)
│   └── upbit_data_provider.py  # Upbit API 데이터 제공자 (구 src/06_ai/priority/services/)
└── gap/            # Gap Detection (구 src/gap/)
```

| 모듈 | 설명 |
|------|------|
| `timescale/` | TimescaleDB 시계열 연산, 10단계 데이터 파이프라인 |
| `redis/` | Redis 캐싱, pub/sub 메시징, gap-fill 큐 |
| `mongodb/` | MongoDB 주문·설정 문서 저장 |
| `features/` | AI/ML 피처 스토어 |
| `pipeline/` | 10단계 데이터 수집 파이프라인 (CandleChecker → PipelineMonitor) |
| `clients/` | TimescaleDB/Redis/MongoDB/Upbit 클라이언트 (TimescaleClient, RedisClient, MongoClient, UpbitDataProvider) |
| `gap/` | Gap 감지 및 백필 워커 (GapDetector, BackfillWorker) |

## 사용법

```python
from timescale import TimescaleConfig, get_pool
from redis import get_client
from mongodb import MongoConfig, get_db
from features import FeatureStore, FeatureEngineer
from pipeline import CandleValidator, CandleChecker
from clients import TimescaleClient, RedisClient
from gap import GapDetector

# TimescaleDB 연결 풀 초기화
pool = await get_pool()

# Redis 클라이언트
client = await get_client()

# MongoDB 데이터베이스 핸들
db = await get_db()
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PGHOST` | `localhost` | TimescaleDB 호스트 |
| `PGPORT` | `5432` | TimescaleDB 포트 |
| `PGUSER` | `postgres` | TimescaleDB 사용자 |
| `PGPASSWORD` | `postgres` | TimescaleDB 비밀번호 |
| `PGDATABASE` | `upbit_trader` | TimescaleDB 데이터베이스 |
| `REDIS_HOST` | `localhost` | Redis 호스트 |
| `REDIS_PORT` | `6379` | Redis 포트 |
| `REDIS_PASSWORD` | (없음) | Redis 비밀번호 |
| `MONGO_HOST` | `localhost` | MongoDB 호스트 |
| `MONGO_PORT` | `27017` | MongoDB 포트 |

⚠️ **Windows 사용자**: 시스템 환경변수에 `REDIS_PORT`, `PGPORT` 등이 잘못 설정된 경우  
Docker 컨테이너 포트와 충돌할 수 있습니다. 아래 트러블슈팅 섹션을 참고하세요.

## 트러블슈팅

### 포트 충돌 (Windows 환경변수)

**증상**: 연결 실패, health check가 "red" 반환

**원인**: Windows 사용자 환경변수에 잘못된 포트가 설정된 경우

```powershell
# 잘못된 예 (ephemeral 포트 범주)
# REDIS_PORT=58530  ← 오류
# PGPORT=58529      ← 오류

# 확인 방법
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")
[System.Environment]::GetEnvironmentVariable("PGPORT", "User")

# 삭제 방법
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
[System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
```

### MongoDB Windows 서비스 충돌

**증상**: `upbit-mongodb` 컨테이너가 포트 27017을 선점당해 시작 실패

**해결**:
```powershell
# Windows MongoDB 서비스 중지
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### 연결 확인

```python
import os
from dotenv import load_dotenv
load_dotenv()
print("REDIS_PORT:", os.getenv("REDIS_PORT"))   # 기대값: 6379
print("PGPORT:", os.getenv("PGPORT"))           # 기대값: 5432
```

## 의존성

- `asyncpg` — TimescaleDB 비동기 클라이언트
- `redis` / `aioredis` — Redis 클라이언트
- `motor` / `pymongo` — MongoDB 비동기 클라이언트
- `pandas`, `polars` — DataFrame 처리
- `orjson` — 고성능 JSON 직렬화

## 참고 문서

- `work_order/DB설계.md` — 데이터베이스 아키텍처 명세
- `work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md` — 시스템 설계 가이드
- `src/02_data/redis/README.md` — Redis 모듈 상세
- `src/02_data/mongodb/README.md` — MongoDB 모듈 상세
- `src/02_data/timescale/README.md` — TimescaleDB 모듈 상세
- `src/02_data/pipeline/` — 데이터 파이프라인 상세
- `src/02_data/clients/` — DB 클라이언트 상세
- `src/02_data/gap/` — Gap Detection 상세


## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PGHOST` | `localhost` | TimescaleDB 호스트 |
| `PGPORT` | `5432` | TimescaleDB 포트 |
| `PGUSER` | `postgres` | TimescaleDB 사용자 |
| `PGPASSWORD` | `postgres` | TimescaleDB 비밀번호 |
| `PGDATABASE` | `upbit_trader` | TimescaleDB 데이터베이스 |
| `REDIS_HOST` | `localhost` | Redis 호스트 |
| `REDIS_PORT` | `6379` | Redis 포트 |
| `REDIS_PASSWORD` | (없음) | Redis 비밀번호 |
| `MONGO_HOST` | `localhost` | MongoDB 호스트 |
| `MONGO_PORT` | `27017` | MongoDB 포트 |

⚠️ **Windows 사용자**: 시스템 환경변수에 `REDIS_PORT`, `PGPORT` 등이 잘못 설정된 경우  
Docker 컨테이너 포트와 충돌할 수 있습니다. 아래 트러블슈팅 섹션을 참고하세요.

## 트러블슈팅

### 포트 충돌 (Windows 환경변수)

**증상**: 연결 실패, health check가 "red" 반환

**원인**: Windows 사용자 환경변수에 잘못된 포트가 설정된 경우

```powershell
# 잘못된 예 (ephemeral 포트 범주)
# REDIS_PORT=58530  ← 오류
# PGPORT=58529      ← 오류

# 확인 방법
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")
[System.Environment]::GetEnvironmentVariable("PGPORT", "User")

# 삭제 방법
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
[System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
```

### MongoDB Windows 서비스 충돌

**증상**: `upbit-mongodb` 컨테이너가 포트 27017을 선점당해 시작 실패

**해결**:
```powershell
# Windows MongoDB 서비스 중지
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### 연결 확인

```python
import os
from dotenv import load_dotenv
load_dotenv()
print("REDIS_PORT:", os.getenv("REDIS_PORT"))   # 기대값: 6379
print("PGPORT:", os.getenv("PGPORT"))           # 기대값: 5432
```

## 의존성

- `asyncpg` — TimescaleDB 비동기 클라이언트
- `redis` / `aioredis` — Redis 클라이언트
- `motor` / `pymongo` — MongoDB 비동기 클라이언트
- `pandas`, `polars` — DataFrame 처리
- `orjson` — 고성능 JSON 직렬화

## 참고 문서

- `work_order/DB설계.md` — 데이터베이스 아키텍처 명세
- `work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md` — 시스템 설계 가이드
- `src/02_data/redis/README.md` — Redis 모듈 상세
- `src/02_data/mongodb/README.md` — MongoDB 모듈 상세
- `src/02_data/timescale/README.md` — TimescaleDB 모듈 상세


## CHANGELOG

- 2026-03-19 | Copilot | `upbit_data_provider.py` 추가 (`src/06_ai/priority/services/` → `src/02_data/clients/`): Upbit 데이터 공급자는 데이터 레이어에 속하므로 `clients/` 하위로 재배치
