# timescale — TimescaleDB 모듈

## 목적

Upbit 트레이딩 시스템의 캔들·거래 시계열 데이터 저장을 담당합니다.  
10단계 데이터 파이프라인으로 데이터 검증, 격리, 집계를 수행합니다.

## 구조

```
timescale/
├── core/               # DB 연결, 설정, 스키마
│   ├── config.py       # TimescaleDB 연결 설정 (환경변수 기반)
│   ├── connection.py   # asyncpg 연결 풀 관리
│   ├── schema.py       # 테이블 정의 (CREATE TABLE / hypertable)
│   └── kafka_client.py # Kafka 이벤트 스트리밍 클라이언트
├── models/             # 데이터 모델
│   ├── candles.py      # 캔들 OHLCV 모델
│   ├── staging.py      # 스테이징 테이블 모델
│   └── isolated.py     # 격리 캔들 모델
├── operations/         # 10단계 데이터 파이프라인
│   ├── stage_01_checker.py       # 1단계: 존재 여부 확인 (L0–L3 캐시)
│   ├── stage_02_receiver.py      # 2단계: 데이터 수집
│   ├── stage_03_stager.py        # 3단계: 임시 스테이징
│   ├── stage_04_validator.py     # 4단계: 유효성 검증
│   ├── stage_05_isolator.py      # 5단계: 격리
│   ├── stage_06_finalizer.py     # 6단계: 최종 저장
│   ├── stage_07_notifier.py      # 7단계: 알림
│   ├── stage_08_aggregator.py    # 8단계: 집계
│   ├── stage_09_hydrator.py      # 9단계: Redis 채우기
│   ├── stage_10_monitor.py       # 10단계: 모니터링
│   └── pipeline_orchestrator.py  # 파이프라인 조율
├── workers/            # 백그라운드 워커
│   ├── gap_fill_worker.py  # Gap 감지 및 보충
│   └── backfill_worker.py  # 히스토리 백필
├── aggregation/        # CAGG 및 지표
│   ├── cagg_manager.py     # 연속 집계 관리
│   └── indicator_computer.py # 기술 지표 계산
├── ml/                 # ML 기반 최적화
│   ├── gap_predictor.py    # Gap 타이밍 예측
│   ├── adaptive_tf.py      # 적응형 타임프레임 선택
│   └── drift_monitor.py    # 데이터 드리프트 모니터
├── health_check.py     # 연결 상태 확인 (asyncpg)
└── ui/                 # PyQt5 관리 다이얼로그
    └── timescale_dialog.py
```

## 사용법

```python
from timescale.core import get_pool, TimescaleConfig
from timescale.operations.checker import DataChecker
from timescale.operations.stager import DataStager
from timescale.workers import GapFillWorker

# 연결 풀 초기화
pool = await get_pool()

# 1단계: Gap 확인
checker = DataChecker(redis_client=redis_client, timescale_client=timescale_client)
missing = await checker.get_missing_ranges("KRW-BTC", "1m", start, end)

# 3단계: 데이터 스테이징
stager = DataStager()
await stager.stage_candles(candles)
```

### health_check.py 동작 (asyncpg)

`check_timescale_connection()` 함수:
1. `asyncpg`로 TimescaleDB에 연결 (timeout: 5초)
2. `SELECT 1` 쿼리 실행
3. 성공 시 `"green"`, 실패 시 `"red"`, asyncpg 미설치 시 `"gray"` 반환

```python
from timescale.health_check import check_timescale_connection

status = await check_timescale_connection()  # "green" | "red" | "gray"
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PGHOST` | `localhost` | TimescaleDB 호스트 |
| `PGPORT` | `5432` | TimescaleDB 포트 |
| `PGUSER` | `postgres` | 연결 사용자 |
| `PGPASSWORD` | `postgres` | 연결 비밀번호 |
| `PGDATABASE` | `upbit_trader` | 데이터베이스 이름 |

⚠️ **포트 주의**: `PGPORT`는 **인바운드 리스닝 포트** 설정입니다.  
outbound 연결 포트(ephemeral port)는 OS가 자동 할당하므로 별도 설정이 필요 없습니다.  
Windows 시스템 환경변수에 `PGPORT=58529` 같은 값이 있으면 반드시 삭제하세요.

## 트러블슈팅

### ⚠️ Windows 환경변수 충돌

**증상**: `asyncpg` 연결 실패, "connection refused on port 58529"

**원인**: Windows 사용자 환경변수 `PGPORT`에 ephemeral 포트가 설정됨

```powershell
# 확인
[System.Environment]::GetEnvironmentVariable("PGPORT", "User")

# 삭제 (기본값 5432로 복원)
[System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
[System.Environment]::SetEnvironmentVariable("PGHOST", $null, "User")
```

### Docker 컨테이너 연결 불가

**원인**: 컨테이너가 `127.0.0.1`만 바인딩한 경우

**해결**: `docker-compose.yml`에서 `listen_addresses='*'` 확인

```yaml
command: >
  postgres
  -c listen_addresses='*'   # ← 모든 인터페이스에서 연결 허용
  -c max_connections=100
  -c shared_buffers=256MB
```

### pg_isready healthcheck 실패

**증상**: 컨테이너 상태가 `unhealthy`

**해결**: `docker-compose.yml` healthcheck에서 `-h 127.0.0.1` 제거

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres -d upbit_trader"]
  # 주의: -h 127.0.0.1 옵션은 외부 연결 차단 시 실패할 수 있음
```

### 연결 실패 디버깅

```bash
# Docker 컨테이너 상태 확인
docker compose ps
docker compose logs upbit-timescaledb

# 포트 점유 확인 (Windows PowerShell)
netstat -ano | findstr :5432
```

## 참고 문서

- `work_order/DB설계.md` §3 TimescaleDB
- `src/02_data/README.md` — 데이터 계층 개요
