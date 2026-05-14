# data_01 ???곗씠??怨꾩링

## 紐⑹쟻

Upbit ?몃젅?대뵫 ?쒖뒪?쒖쓽 ?듯빀 ?곗씠???묎렐 怨꾩링?낅땲??  
?쒓퀎????? 罹먯떛, 臾몄꽌 ??? AI/ML ?쇱쿂 ?붿??덉뼱留곸쓣 ?대떦?⑸땲??

## 援ъ“

```
src/data_01/
?쒋?? timescale/      # TimescaleDB ??罹붾뱾/嫄곕옒 ?쒓퀎???곗씠??
?쒋?? redis/          # Redis ??L1 罹먯떆, pub/sub, gap-fill ??
?쒋?? mongodb/        # MongoDB ??二쇰Ц쨌?ㅼ젙쨌?ъ???臾몄꽌 ???
?쒋?? features/       # Feature store ??AI/ML ?쇱쿂 ?붿??덉뼱留?
?쒋?? pipeline/       # 10?④퀎 ?곗씠???섏쭛 ?뚯씠?꾨씪??(援?src/data_pipeline/)
?쒋?? clients/        # ?곗씠?곕쿋?댁뒪 ?대씪?댁뼵??(援?src/db/)
??  ?붴?? upbit_data_provider.py  # Upbit API ?곗씠???쒓났??(援?src/06_ai/priority/services/)
?붴?? gap/            # Gap Detection (援?src/gap/)
```

| 紐⑤뱢 | ?ㅻ챸 |
|------|------|
| `timescale/` | TimescaleDB ?쒓퀎???곗궛, 10?④퀎 ?곗씠???뚯씠?꾨씪??|
| `redis/` | Redis 罹먯떛, pub/sub 硫붿떆吏? gap-fill ??|
| `mongodb/` | MongoDB 二쇰Ц쨌?ㅼ젙 臾몄꽌 ???|
| `features/` | AI/ML ?쇱쿂 ?ㅽ넗??|
| `pipeline/` | 10?④퀎 ?곗씠???섏쭛 ?뚯씠?꾨씪??(CandleChecker ??PipelineMonitor) |
| `clients/` | TimescaleDB/Redis/MongoDB/Upbit ?대씪?댁뼵??(TimescaleClient, RedisClient, MongoClient, UpbitDataProvider) |
| `gap/` | Gap 媛먯? 諛?諛깊븘 ?뚯빱 (GapDetector, BackfillWorker) |

## ?ъ슜踰?

```python
from timescale import TimescaleConfig, get_pool
from redis import get_client
from mongodb import MongoConfig, get_db
from features import FeatureStore, FeatureEngineer
from pipeline import CandleValidator, CandleChecker
from clients import TimescaleClient, RedisClient
from gap import GapDetector

# TimescaleDB ?곌껐 ? 珥덇린??
pool = await get_pool()

# Redis ?대씪?댁뼵??
client = await get_client()

# MongoDB ?곗씠?곕쿋?댁뒪 ?몃뱾
db = await get_db()
```

## ?섍꼍蹂??

| 蹂??| 湲곕낯媛?| ?ㅻ챸 |
|------|--------|------|
| `PGHOST` | `localhost` | TimescaleDB ?몄뒪??|
| `PGPORT` | `5432` | TimescaleDB ?ы듃 |
| `PGUSER` | `postgres` | TimescaleDB ?ъ슜??|
| `PGPASSWORD` | `postgres` | TimescaleDB 鍮꾨?踰덊샇 |
| `PGDATABASE` | `upbit_trader` | TimescaleDB ?곗씠?곕쿋?댁뒪 |
| `REDIS_HOST` | `localhost` | Redis ?몄뒪??|
| `REDIS_PORT` | `6379` | Redis ?ы듃 |
| `REDIS_PASSWORD` | (?놁쓬) | Redis 鍮꾨?踰덊샇 |
| `MONGO_HOST` | `localhost` | MongoDB ?몄뒪??|
| `MONGO_PORT` | `27017` | MongoDB ?ы듃 |

?좑툘 **Windows ?ъ슜??*: ?쒖뒪???섍꼍蹂?섏뿉 `REDIS_PORT`, `PGPORT` ?깆씠 ?섎せ ?ㅼ젙??寃쎌슦  
Docker 而⑦뀒?대꼫 ?ы듃? 異⑸룎?????덉뒿?덈떎. ?꾨옒 ?몃윭釉붿뒋???뱀뀡??李멸퀬?섏꽭??

## ?몃윭釉붿뒋??

### ?ы듃 異⑸룎 (Windows ?섍꼍蹂??

**利앹긽**: ?곌껐 ?ㅽ뙣, health check媛 "red" 諛섑솚

**?먯씤**: Windows ?ъ슜???섍꼍蹂?섏뿉 ?섎せ???ы듃媛 ?ㅼ젙??寃쎌슦

```powershell
# ?섎せ????(ephemeral ?ы듃 踰붿＜)
# REDIS_PORT=58530  ???ㅻ쪟
# PGPORT=58529      ???ㅻ쪟

# ?뺤씤 諛⑸쾿
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")
[System.Environment]::GetEnvironmentVariable("PGPORT", "User")

# ??젣 諛⑸쾿
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
[System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
```

### MongoDB Windows ?쒕퉬??異⑸룎

**利앹긽**: `upbit-mongodb` 而⑦뀒?대꼫媛 ?ы듃 27017???좎젏?뱁빐 ?쒖옉 ?ㅽ뙣

**?닿껐**:
```powershell
# Windows MongoDB ?쒕퉬??以묒?
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### ?곌껐 ?뺤씤

```python
import os
from dotenv import load_dotenv
load_dotenv()
print("REDIS_PORT:", os.getenv("REDIS_PORT"))   # 湲곕?媛? 6379
print("PGPORT:", os.getenv("PGPORT"))           # 湲곕?媛? 5432
```

## ?섏〈??

- `asyncpg` ??TimescaleDB 鍮꾨룞湲??대씪?댁뼵??
- `redis` / `aioredis` ??Redis ?대씪?댁뼵??
- `motor` / `pymongo` ??MongoDB 鍮꾨룞湲??대씪?댁뼵??
- `pandas`, `polars` ??DataFrame 泥섎━
- `orjson` ??怨좎꽦??JSON 吏곷젹??

## 李멸퀬 臾몄꽌

- `work_order/DB?ㅺ퀎.md` ???곗씠?곕쿋?댁뒪 ?꾪궎?띿쿂 紐낆꽭
- `work_order/1_?④퀎_湲곌??먯씠?꾪듃湲?理쒖떊_?몃젅?대뵫_?쒖뒪??媛?대뱶.md` ???쒖뒪???ㅺ퀎 媛?대뱶
- `src/data_01/redis/README.md` ??Redis 紐⑤뱢 ?곸꽭
- `src/data_01/mongodb/README.md` ??MongoDB 紐⑤뱢 ?곸꽭
- `src/data_01/timescale/README.md` ??TimescaleDB 紐⑤뱢 ?곸꽭
- `src/data_01/pipeline/` ???곗씠???뚯씠?꾨씪???곸꽭
- `src/data_01/clients/` ??DB ?대씪?댁뼵???곸꽭
- `src/data_01/gap/` ??Gap Detection ?곸꽭


## ?섍꼍蹂??

| 蹂??| 湲곕낯媛?| ?ㅻ챸 |
|------|--------|------|
| `PGHOST` | `localhost` | TimescaleDB ?몄뒪??|
| `PGPORT` | `5432` | TimescaleDB ?ы듃 |
| `PGUSER` | `postgres` | TimescaleDB ?ъ슜??|
| `PGPASSWORD` | `postgres` | TimescaleDB 鍮꾨?踰덊샇 |
| `PGDATABASE` | `upbit_trader` | TimescaleDB ?곗씠?곕쿋?댁뒪 |
| `REDIS_HOST` | `localhost` | Redis ?몄뒪??|
| `REDIS_PORT` | `6379` | Redis ?ы듃 |
| `REDIS_PASSWORD` | (?놁쓬) | Redis 鍮꾨?踰덊샇 |
| `MONGO_HOST` | `localhost` | MongoDB ?몄뒪??|
| `MONGO_PORT` | `27017` | MongoDB ?ы듃 |

?좑툘 **Windows ?ъ슜??*: ?쒖뒪???섍꼍蹂?섏뿉 `REDIS_PORT`, `PGPORT` ?깆씠 ?섎せ ?ㅼ젙??寃쎌슦  
Docker 而⑦뀒?대꼫 ?ы듃? 異⑸룎?????덉뒿?덈떎. ?꾨옒 ?몃윭釉붿뒋???뱀뀡??李멸퀬?섏꽭??

## ?몃윭釉붿뒋??

### ?ы듃 異⑸룎 (Windows ?섍꼍蹂??

**利앹긽**: ?곌껐 ?ㅽ뙣, health check媛 "red" 諛섑솚

**?먯씤**: Windows ?ъ슜???섍꼍蹂?섏뿉 ?섎せ???ы듃媛 ?ㅼ젙??寃쎌슦

```powershell
# ?섎せ????(ephemeral ?ы듃 踰붿＜)
# REDIS_PORT=58530  ???ㅻ쪟
# PGPORT=58529      ???ㅻ쪟

# ?뺤씤 諛⑸쾿
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")
[System.Environment]::GetEnvironmentVariable("PGPORT", "User")

# ??젣 諛⑸쾿
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
[System.Environment]::SetEnvironmentVariable("PGPORT", $null, "User")
```

### MongoDB Windows ?쒕퉬??異⑸룎

**利앹긽**: `upbit-mongodb` 而⑦뀒?대꼫媛 ?ы듃 27017???좎젏?뱁빐 ?쒖옉 ?ㅽ뙣

**?닿껐**:
```powershell
# Windows MongoDB ?쒕퉬??以묒?
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### ?곌껐 ?뺤씤

```python
import os
from dotenv import load_dotenv
load_dotenv()
print("REDIS_PORT:", os.getenv("REDIS_PORT"))   # 湲곕?媛? 6379
print("PGPORT:", os.getenv("PGPORT"))           # 湲곕?媛? 5432
```

## ?섏〈??

- `asyncpg` ??TimescaleDB 鍮꾨룞湲??대씪?댁뼵??
- `redis` / `aioredis` ??Redis ?대씪?댁뼵??
- `motor` / `pymongo` ??MongoDB 鍮꾨룞湲??대씪?댁뼵??
- `pandas`, `polars` ??DataFrame 泥섎━
- `orjson` ??怨좎꽦??JSON 吏곷젹??

## 李멸퀬 臾몄꽌

- `work_order/DB?ㅺ퀎.md` ???곗씠?곕쿋?댁뒪 ?꾪궎?띿쿂 紐낆꽭
- `work_order/1_?④퀎_湲곌??먯씠?꾪듃湲?理쒖떊_?몃젅?대뵫_?쒖뒪??媛?대뱶.md` ???쒖뒪???ㅺ퀎 媛?대뱶
- `src/data_01/redis/README.md` ??Redis 紐⑤뱢 ?곸꽭
- `src/data_01/mongodb/README.md` ??MongoDB 紐⑤뱢 ?곸꽭
- `src/data_01/timescale/README.md` ??TimescaleDB 紐⑤뱢 ?곸꽭


## CHANGELOG

- 2026-03-19 | Copilot | `upbit_data_provider.py` 異붽? (`src/06_ai/priority/services/` ??`src/data_01/clients/`): Upbit ?곗씠??怨듦툒?먮뒗 ?곗씠???덉씠?댁뿉 ?랁븯誘濡?`clients/` ?섏쐞濡??щ같移?

