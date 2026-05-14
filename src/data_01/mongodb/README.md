# mongodb — MongoDB 모듈

## 목적

Upbit 트레이딩 시스템의 주문, 포지션, 사용자 설정, 심볼 메타데이터를 문서 저장소로 관리합니다.

## 구조

```
mongodb/
├── core/               # 연결 풀 및 설정
│   ├── config.py       # MongoDB 연결 설정 (환경변수 기반)
│   ├── connection.py   # motor 비동기 연결 관리
│   ├── handler.py      # DBHandler — 레거시 통합 IO 핸들러
│   └── lite_storage.py # SQLite 기반 LiteStorage (MongoDB 없는 환경 대체)
├── models/             # 데이터 모델
│   ├── metadata.py     # 심볼 메타데이터 모델
│   ├── priority_settings.py  # 우선순위 설정 모델
│   └── user_favorites.py     # 즐겨찾기 모델
├── operations/         # 컬렉션별 CRUD
│   ├── symbol_manager.py   # 심볼 CRUD 및 생명주기 관리
│   └── settings_manager.py # 앱 설정 CRUD
├── health_check.py     # 연결 상태 확인
├── init_mongodb.py     # DB 초기화 (컬렉션·인덱스 생성)
└── ui/                 # PyQt5 관리 다이얼로그
    └── mongo_dialog.py
```

## 사용법

```python
from mongodb.core import get_db, MongoConfig
from mongodb.operations.symbol_manager import SymbolManager
from mongodb.operations.settings_manager import SettingsManager

# MongoDB 데이터베이스 핸들
db = await get_db()

# 심볼 관리
sym_mgr = SymbolManager(db)
symbols = await sym_mgr.get_all_symbols()

# 설정 관리
settings = SettingsManager(db)
await settings.save({"interval": "1m", "symbols": ["KRW-BTC"]})
```

### init_mongodb.py 사용법

```bash
# 컬렉션 및 인덱스 초기화 (최초 실행 시)
python src/data_01/mongodb/init_mongodb.py
```

### health_check.py 동작

`check_mongo_connection()` 함수:
1. `motor`로 MongoDB에 연결
2. `admin.command("ping")` 실행
3. 성공 시 `"green"`, 실패 시 `"red"`, 설정 없음 시 `"gray"` 반환

```python
from mongodb.health_check import check_mongo_connection

status = await check_mongo_connection()  # "green" | "red" | "gray"
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MONGO_HOST` | `localhost` | MongoDB 호스트 |
| `MONGO_PORT` | `27017` | MongoDB 포트 |
| `MONGO_INITDB_ROOT_USERNAME` | (없음) | MongoDB 관리자 사용자명 |
| `MONGO_INITDB_ROOT_PASSWORD` | (없음) | MongoDB 관리자 비밀번호 |

## 트러블슈팅

### ⚠️ Windows MongoDB 서비스 충돌

**증상**: `upbit-mongodb` 컨테이너가 포트 27017을 선점당해 시작 실패

```
Error: Address already in use: 0.0.0.0:27017
```

**원인**: Windows에 MongoDB가 서비스로 설치되어 있어 포트를 선점

**해결**:
```powershell
# MongoDB Windows 서비스 중지 및 자동 시작 비활성화
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### Docker 컨테이너 연결 불가

**원인**: 컨테이너가 `127.0.0.1`만 바인딩한 경우

**해결**: `docker-compose.yml`에서 `--bind_ip 0.0.0.0` 확인

```yaml
command: >
  mongod
  --bind_ip 0.0.0.0   # ← 호스트에서 접근 허용
  --noauth
```

### 연결 실패 디버깅

```bash
# Docker 컨테이너 상태 확인
docker compose ps
docker compose logs upbit-mongodb

# 포트 점유 확인 (Windows PowerShell)
netstat -ano | findstr :27017
```

## 참고 문서

- `work_order/DB설계.md` §5 MongoDB
- `src/data_01/README.md` — 데이터 계층 개요
