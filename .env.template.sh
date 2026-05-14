# Copy to .env and fill real secrets. DO NOT commit .env
#
# ⚠️ Windows 환경변수 충돌 주의사항:
#   Windows 시스템/사용자 환경변수에 REDIS_PORT, PGPORT 등이 설정된 경우
#   이 파일의 값보다 시스템 환경변수가 우선 적용되어 DB 연결 실패가 발생합니다.
#   아래 PowerShell 명령으로 충돌하는 환경변수를 삭제하세요:
#
#   [System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
#   [System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
#   [System.Environment]::SetEnvironmentVariable("PGHOST", $null, "User")

# ── Python 앱에서 MongoDB 접속 시 사용하는 인증 정보 ──────────────────────────
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=__CHANGE_ME__

# ── Docker Compose가 MongoDB 컨테이너를 초기화할 때 사용하는 값 ──────────────
# docker-compose.yml은 MONGO_INITDB_ROOT_USERNAME_CONTAINER 를 컨테이너의
# MONGO_INITDB_ROOT_USERNAME 환경변수로 매핑합니다.
# 이 _CONTAINER 변수로 MongoDB가 초기화되므로, 위의 MONGO_INITDB_ROOT_USERNAME /
# _PASSWORD 와 반드시 같은 값을 설정해야 Python 앱이 MongoDB에 인증 성공합니다.
MONGO_INITDB_ROOT_USERNAME_CONTAINER=admin
MONGO_INITDB_ROOT_PASSWORD_CONTAINER=__CHANGE_ME__
MONGO_INITDB_DATABASE_CONTAINER=upbit_trader
MONGO_DATA_DIR=mongo-data

# ── Redis ────────────────────────────────────────────────────────────────────
# 외부 매핑 포트: 58530 (Docker 컨테이너 내부 포트 6379 → 호스트 포트 58530)
# ⚠️ Windows 사용자: REDIS_PORT 환경변수가 시스템에 설정된 경우 삭제 필요
REDIS_PASSWORD=__CHANGE_ME__
REDIS_PASSWORD_CONTAINER=__CHANGE_ME__
REDIS_PORT_CONTAINER=58530
REDIS_DATA_DIR=redis-data

# ── TimescaleDB (PostgreSQL) ──────────────────────────────────────────────────
# 외부 매핑 포트: 58529 (Docker 컨테이너 내부 포트 5432 → 호스트 포트 58529)
# ⚠️ Windows 사용자: PGPORT 환경변수가 시스템에 설정된 경우 삭제 필요
POSTGRES_USER=postgres
POSTGRES_PASSWORD=__CHANGE_ME__
POSTGRES_DB=postgres
POSTGRES_USER_CONTAINER=postgres
POSTGRES_PASSWORD_CONTAINER=__CHANGE_ME__
POSTGRES_DB_CONTAINER=postgres
POSTGRES_PORT_CONTAINER=58529
TIMESCALE_DATA_DIR=timescale-data

# ── App / misc ────────────────────────────────────────────────────────────────
REDIS_URL=redis://:__CHANGE_ME__@upbit-redis:6379/0
PYTHONPATH=src