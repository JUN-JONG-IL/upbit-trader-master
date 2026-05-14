# src/11_server — FastAPI REST/WebSocket 서버

## 서버 개요

`src/11_server`는 Upbit Trader 플랫폼의 **REST API·WebSocket 서버 계층**을 담당합니다.

- **프레임워크**: FastAPI (ASGI)
- **실시간 통신**: WebSocket (주문·캔들 스트리밍)
- **인증**: JWT Bearer 토큰
- **Rate Limit**: Redis 기반 슬라이딩 윈도우
- **CORS**: 환경 변수 설정 허용 Origin
- **모니터링**: Prometheus metrics (`/metrics`)

> ⚠️ **중요: 데이터베이스 설정 위치**
>
> 데이터베이스 연결 설정 UI는 **`src/data_01/` 폴더**에 있습니다.
> - TimescaleDB: `src/data_01/timescale/ui/`
> - Redis: `src/data_01/redis/ui/`
> - MongoDB: `src/data_01/mongodb/ui/`
> - Kafka: `src/data_01/kafka/ui/`
> - ClickHouse: `src/data_01/clickhouse/ui/`
> - PostgreSQL: `src/data_01/postgres/ui/`
>
> `11_server`는 **서버 자체 설정**(포트, CORS, 인증 등)만 관리합니다.
> DB 연결은 메인 앱의 **"데이터베이스" 메뉴**에서 관리하세요.

---

## 폴더 구조

```
src/11_server/
├── README.md                    # 이 파일
├── __init__.py                  # 주요 컴포넌트 re-export
│
├── core/                        # 핵심 서버 로직
│   ├── fastapi_app.py           # FastAPI 앱 생성, 미들웨어 등록, 라우터 연결
│   ├── websocket_manager.py     # WebSocket 연결 풀 관리
│   └── session_manager.py       # JWT 세션 관리
│
├── api/                         # REST API 엔드포인트
│   ├── candles.py               # GET /api/v1/candles  — 캔들 데이터 조회
│   ├── symbols.py               # GET /api/v1/symbols  — 심볼 목록 조회
│   ├── orders.py                # POST /api/v1/orders  — 주문 관리
│   └── health.py                # GET /health          — 서버 상태 확인
│
├── workers/                     # 백그라운드 워커
│   ├── data_sync.py             # TimescaleDB → Redis 실시간 동기화
│   ├── gap_detector.py          # 데이터 Gap 탐지
│   └── aggregator.py            # OHLCV CAGG Refresh
│
├── middleware/                  # 미들웨어
│   ├── rate_limiter.py          # Redis 기반 Rate Limit
│   ├── auth_middleware.py       # JWT 인증 미들웨어
│   └── cors_middleware.py       # CORS 설정
│
├── config/                      # 서버 설정
│   ├── server_config.py         # 호스트·포트·디버그 설정
│   └── redis_config.py          # Redis 연결 설정
│
├── utils/                       # 유틸리티
│   ├── response_formatter.py    # 공통 응답 포맷
│   └── error_handlers.py        # 전역 예외 핸들러
│
├── ui/                          # PyQt5 서버 관리 UI (서버 전용)
│   ├── settings/                # 서버 설정 UI
│   │   ├── server_settings.ui
│   │   └── widget_server_settings.py
│   └── monitoring/              # 서버 모니터링 UI
│       ├── server_status.ui
│       └── widget_server_status.py
│
└── websocket/                   # WebSocket 핸들러
    └── handlers.py              # WS 이벤트 라우팅
```

---

## 설치 방법

### 1. Python 의존성 설치

```bash
pip install -r requirements.txt
```

주요 패키지: `fastapi`, `uvicorn[standard]`, `python-jose[cryptography]`, `redis`, `asyncpg`.

### 2. 환경 변수 설정

`.env` 파일 또는 OS 환경 변수로 설정합니다:

```env
# 서버
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
DEBUG=false

# 인증
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# TimescaleDB
TIMESCALE_DSN=postgresql+asyncpg://user:password@localhost:5432/upbit_trader

# CORS (쉼표 구분)
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

> ⚠️ **보안 주의**: `JWT_SECRET_KEY`와 DB 비밀번호는 절대 코드에 하드코딩하지 마세요.

---

## 실행 방법

### 개발 모드 (핫 리로드)

```bash
uvicorn src.11_server.core.fastapi_app:create_app --factory \
    --host 0.0.0.0 --port 8000 --reload
```

### 프로덕션 모드

```bash
uvicorn src.11_server.core.fastapi_app:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --workers 4 \
    --log-level info
```

### Docker로 실행

```bash
docker-compose up server
```

---

## API 엔드포인트 문서

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)  
ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Health Check

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 서버 및 DB 연결 상태 |
| GET | `/metrics` | Prometheus metrics |

**응답 예시 (`/health`)**:
```json
{
  "status": "ok",
  "timestamp": "2026-03-19T12:00:00Z",
  "services": {
    "timescale": "connected",
    "redis": "connected",
    "mongodb": "connected"
  }
}
```

### 캔들 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/candles` | 캔들 데이터 조회 |

**쿼리 파라미터**:
- `symbol` (필수): 심볼명 (예: `KRW-BTC`)
- `interval` (필수): 캔들 간격 (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- `limit` (선택, 기본 200): 반환할 캔들 수 (최대 1000)
- `start` (선택): ISO8601 시작 시각
- `end` (선택): ISO8601 종료 시각

**응답 예시**:
```json
{
  "symbol": "KRW-BTC",
  "interval": "1m",
  "data": [
    {
      "timestamp": "2026-03-19T12:00:00Z",
      "open": 135000000,
      "high": 136000000,
      "low": 134500000,
      "close": 135500000,
      "volume": 12.5
    }
  ]
}
```

### 심볼 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/symbols` | 전체 심볼 목록 조회 |
| GET | `/api/v1/symbols/{symbol}` | 단일 심볼 정보 조회 |

### 주문 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/orders` | 주문 생성 |
| GET | `/api/v1/orders/{order_id}` | 주문 상태 조회 |
| DELETE | `/api/v1/orders/{order_id}` | 주문 취소 |

> ⚠️ **주문 API는 유효한 JWT 토큰이 필요합니다** (`Authorization: Bearer <token>` 헤더).

### WebSocket 엔드포인트

| 경로 | 설명 |
|------|------|
| `ws://localhost:8000/ws/candles/{symbol}` | 실시간 캔들 스트리밍 |
| `ws://localhost:8000/ws/orderbook/{symbol}` | 실시간 호가창 스트리밍 |

---

## 설정 방법

### 서버 설정 (`src/11_server/config/server_config.py`)

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `SERVER_HOST` | `0.0.0.0` | 바인딩 호스트 |
| `SERVER_PORT` | `8000` | 서버 포트 |
| `DEBUG` | `false` | 디버그 모드 |
| `WORKERS` | `1` | 워커 프로세스 수 |

### Rate Limit 설정

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `RATE_LIMIT_PER_MINUTE` | `100` | 분당 최대 요청 수 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate Limit 윈도우 |

### JWT 설정

| 설정 키 | 기본값 | 설명 |
|---------|--------|------|
| `JWT_SECRET_KEY` | (필수) | 토큰 서명 키 |
| `JWT_ALGORITHM` | `HS256` | 서명 알고리즘 |
| `JWT_EXPIRE_MINUTES` | `60` | 토큰 만료 시간 |

---

## 서버 제어 UI

PyQt5 메인 앱의 **"서버" 메뉴**에서 서버를 제어할 수 있습니다:

- **서버 상태** (`actionServerStatus`): 현재 서버 상태 모니터링
- **서버 설정** (`actionServerSettings`): 호스트·포트·인증 설정
- **FastAPI Swagger** (`actionFastAPI`): 브라우저에서 Swagger UI 열기
- **WebSocket 연결** (`actionWebSocket`): WebSocket 클라이언트 테스트

---

## 트러블슈팅 가이드

### 서버가 시작되지 않는 경우

1. **포트 충돌 확인**:
   ```bash
   lsof -i :8000
   ```
2. **Redis 연결 확인**:
   ```bash
   redis-cli ping   # PONG 응답이 있어야 정상
   ```
3. **환경 변수 확인**:
   ```bash
   echo $JWT_SECRET_KEY
   echo $TIMESCALE_DSN
   ```

### 인증 오류 (401 Unauthorized)

- `Authorization: Bearer <token>` 헤더가 포함되어 있는지 확인
- 토큰 만료 여부 확인 (`JWT_EXPIRE_MINUTES` 설정)
- `JWT_SECRET_KEY`가 서버와 클라이언트 동일한지 확인

### Rate Limit 오류 (429 Too Many Requests)

- `RATE_LIMIT_PER_MINUTE` 값 증가
- Redis가 정상 동작 중인지 확인
- 요청 빈도를 줄이거나 캐싱 적용

### WebSocket 연결 실패

- 방화벽에서 WebSocket 포트 허용 여부 확인
- CORS `CORS_ORIGINS` 설정에 클라이언트 Origin 포함 여부 확인
- 로그에서 `WebSocketManager` 관련 오류 확인:
  ```bash
  grep "WebSocket" logs/server.log
  ```

### TimescaleDB 연결 오류

- `TIMESCALE_DSN` 환경 변수 정확성 확인
- PostgreSQL 서비스 실행 여부 확인:
  ```bash
  pg_isready -h localhost -p 5432
  ```
- Docker 사용 시: `docker-compose ps timescale`

---

## 로그 확인

```bash
# 실시간 로그 스트리밍
tail -f logs/server.log

# 오류만 필터링
grep "ERROR\|CRITICAL" logs/server.log

# API 요청 로그
grep "api/v1" logs/server.log
```

---

*최종 수정: 2026-03-19 | Copilot*
