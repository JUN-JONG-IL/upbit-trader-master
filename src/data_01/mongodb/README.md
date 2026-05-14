# mongodb ??MongoDB 紐⑤뱢

## 紐⑹쟻

Upbit ?몃젅?대뵫 ?쒖뒪?쒖쓽 二쇰Ц, ?ъ??? ?ъ슜???ㅼ젙, ?щ낵 硫뷀??곗씠?곕? 臾몄꽌 ??μ냼濡?愿由ы빀?덈떎.

## 援ъ“

```
mongodb/
?쒋?? core/               # ?곌껐 ? 諛??ㅼ젙
??  ?쒋?? config.py       # MongoDB ?곌껐 ?ㅼ젙 (?섍꼍蹂??湲곕컲)
??  ?쒋?? connection.py   # motor 鍮꾨룞湲??곌껐 愿由?
??  ?쒋?? handler.py      # DBHandler ???덇굅???듯빀 IO ?몃뱾??
??  ?붴?? lite_storage.py # SQLite 湲곕컲 LiteStorage (MongoDB ?녿뒗 ?섍꼍 ?泥?
?쒋?? models/             # ?곗씠??紐⑤뜽
??  ?쒋?? metadata.py     # ?щ낵 硫뷀??곗씠??紐⑤뜽
??  ?쒋?? priority_settings.py  # ?곗꽑?쒖쐞 ?ㅼ젙 紐⑤뜽
??  ?붴?? user_favorites.py     # 利먭꺼李얘린 紐⑤뜽
?쒋?? operations/         # 而щ젆?섎퀎 CRUD
??  ?쒋?? symbol_manager.py   # ?щ낵 CRUD 諛??앸챸二쇨린 愿由?
??  ?붴?? settings_manager.py # ???ㅼ젙 CRUD
?쒋?? health_check.py     # ?곌껐 ?곹깭 ?뺤씤
?쒋?? init_mongodb.py     # DB 珥덇린??(而щ젆?샕룹씤?깆뒪 ?앹꽦)
?붴?? ui/                 # PyQt5 愿由??ㅼ씠?쇰줈洹?
    ?붴?? mongo_dialog.py
```

## ?ъ슜踰?

```python
from mongodb.core import get_db, MongoConfig
from mongodb.operations.symbol_manager import SymbolManager
from mongodb.operations.settings_manager import SettingsManager

# MongoDB ?곗씠?곕쿋?댁뒪 ?몃뱾
db = await get_db()

# ?щ낵 愿由?
sym_mgr = SymbolManager(db)
symbols = await sym_mgr.get_all_symbols()

# ?ㅼ젙 愿由?
settings = SettingsManager(db)
await settings.save({"interval": "1m", "symbols": ["KRW-BTC"]})
```

### init_mongodb.py ?ъ슜踰?

```bash
# 而щ젆??諛??몃뜳??珥덇린??(理쒖큹 ?ㅽ뻾 ??
python src/data_01/mongodb/init_mongodb.py
```

### health_check.py ?숈옉

`check_mongo_connection()` ?⑥닔:
1. `motor`濡?MongoDB???곌껐
2. `admin.command("ping")` ?ㅽ뻾
3. ?깃났 ??`"green"`, ?ㅽ뙣 ??`"red"`, ?ㅼ젙 ?놁쓬 ??`"gray"` 諛섑솚

```python
from mongodb.health_check import check_mongo_connection

status = await check_mongo_connection()  # "green" | "red" | "gray"
```

## ?섍꼍蹂??

| 蹂??| 湲곕낯媛?| ?ㅻ챸 |
|------|--------|------|
| `MONGO_HOST` | `localhost` | MongoDB ?몄뒪??|
| `MONGO_PORT` | `27017` | MongoDB ?ы듃 |
| `MONGO_INITDB_ROOT_USERNAME` | (?놁쓬) | MongoDB 愿由ъ옄 ?ъ슜?먮챸 |
| `MONGO_INITDB_ROOT_PASSWORD` | (?놁쓬) | MongoDB 愿由ъ옄 鍮꾨?踰덊샇 |

## ?몃윭釉붿뒋??

### ?좑툘 Windows MongoDB ?쒕퉬??異⑸룎

**利앹긽**: `upbit-mongodb` 而⑦뀒?대꼫媛 ?ы듃 27017???좎젏?뱁빐 ?쒖옉 ?ㅽ뙣

```
Error: Address already in use: 0.0.0.0:27017
```

**?먯씤**: Windows??MongoDB媛 ?쒕퉬?ㅻ줈 ?ㅼ튂?섏뼱 ?덉뼱 ?ы듃瑜??좎젏

**?닿껐**:
```powershell
# MongoDB Windows ?쒕퉬??以묒? 諛??먮룞 ?쒖옉 鍮꾪솢?깊솕
Stop-Service -Name MongoDB
Set-Service -Name MongoDB -StartupType Disabled
```

### Docker 而⑦뀒?대꼫 ?곌껐 遺덇?

**?먯씤**: 而⑦뀒?대꼫媛 `127.0.0.1`留?諛붿씤?⑺븳 寃쎌슦

**?닿껐**: `docker-compose.yml`?먯꽌 `--bind_ip 0.0.0.0` ?뺤씤

```yaml
command: >
  mongod
  --bind_ip 0.0.0.0   # ???몄뒪?몄뿉???묎렐 ?덉슜
  --noauth
```

### ?곌껐 ?ㅽ뙣 ?붾쾭源?

```bash
# Docker 而⑦뀒?대꼫 ?곹깭 ?뺤씤
docker compose ps
docker compose logs upbit-mongodb

# ?ы듃 ?먯쑀 ?뺤씤 (Windows PowerShell)
netstat -ano | findstr :27017
```

## 李멸퀬 臾몄꽌

- `work_order/DB?ㅺ퀎.md` 짠5 MongoDB
- `src/data_01/README.md` ???곗씠??怨꾩링 媛쒖슂

