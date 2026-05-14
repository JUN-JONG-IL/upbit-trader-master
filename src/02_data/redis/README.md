# redis — Redis 모듈

## 목적

Upbit 트레이딩 시스템의 고성능 캐싱, pub/sub 메시징, gap-fill 큐를 담당합니다.

## 구조

```
redis/
├── core/               # 연결 풀 및 설정
│   ├── config.py       # Redis 연결 설정 (환경변수 기반)
│   ├── connection.py   # redis.asyncio 연결 관리
│   ├── client.py       # 동기 RedisClient 래퍼
│   └── lite_cache.py   # 인메모리 LiteCache (Redis 없는 환경 대체)
├── cache/              # L1 캐시 연산
│   ├── l1_cache.py     # 최근 캔들 LRANGE 캐시
│   └── hydrator.py     # TimescaleDB → Redis 캐시 채우기
├── pubsub/             # Pub/Sub 메시징
│   ├── publisher.py    # 메시지 발행
│   └── subscriber.py   # 메시지 구독
├── queue/              # Gap-fill 큐
│   └── gap_queue.py    # Redis 기반 gap 작업 큐
├── health_check.py     # 연결 상태 확인 (RESP 프로토콜)
└── ui/                 # PyQt5 모니터링 다이얼로그
    └── redis_dialog.py
```

## 사용법

```python
from redis.core import get_client, RedisConfig
from redis.cache.l1_cache import L1Cache
from redis.pubsub.publisher import Publisher
from redis.queue.gap_queue import GapQueue

# 비동기 Redis 클라이언트
client = await get_client()

# L1 캐시 연산
cache = L1Cache(client)
await cache.push("KRW-BTC", "1m", candle_data)

# 메시지 발행
pub = Publisher(client)
await pub.publish("candle_update", {"symbol": "KRW-BTC"})

# Gap-fill 큐
queue = GapQueue(client)
await queue.enqueue(gap_task)
```

### health_check.py 동작 (RESP 프로토콜)

`check_redis_connection()` 함수는 `socket`으로 직접 RESP 프로토콜을 사용합니다.

1. 소켓 연결 (timeout: 5초)
2. 비밀번호가 있으면 `AUTH` 명령 전송 → 50ms 대기 → 응답 확인
3. `PING` 명령 전송 → 50ms 대기 → 응답 확인
4. `+PONG` 또는 `NOAUTH` 포함 시 `"green"` 반환

```python
from redis.health_check import check_redis_connection

status = check_redis_connection()  # "green" | "red" | "gray"
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `REDIS_HOST` | `localhost` | Redis 서버 호스트 |
| `REDIS_PORT` | `6379` | Redis 서버 포트 |
| `REDIS_PASSWORD` | (없음) | Redis 인증 비밀번호 |

## 트러블슈팅

### Windows 환경변수 충돌

**증상**: health check가 "red" 반환, 연결 거부

**원인**: Windows 사용자 환경변수에 ephemeral 포트가 설정된 경우

```powershell
# 잘못된 예
# REDIS_PORT=58530  ← ephemeral 포트 범주 (오류)

# 확인
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")

# 삭제 (기본값 6379로 복원)
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
```

### recv() 응답 대기 부족

**증상**: PING 후 빈 응답, "red" 반환

**해결**: `health_check.py`에 `time.sleep(0.05)` 추가 (이미 적용됨)

```python
sock.sendall(b"*1\r\n$4\r\nPING\r\n")
time.sleep(0.05)  # ✅ 응답 대기
ping_resp = sock.recv(64).decode(errors="replace").strip()
```

### Docker 컨테이너 연결 불가

**원인**: Redis 컨테이너가 `127.0.0.1`만 바인딩한 경우

**해결**: `docker-compose.yml`에서 `--bind 0.0.0.0` 확인

```yaml
command: >
  sh -c "redis-server
  --bind 0.0.0.0   # ← 호스트에서 접근 허용
  --protected-mode no
  ..."
```

## 참고 문서

- `work_order/DB설계.md` §4 Redis
- `src/02_data/README.md` — 데이터 계층 개요
