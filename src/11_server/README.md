# src/11_server ??FastAPI REST/WebSocket ?쒕쾭

## ?쒕쾭 媛쒖슂

`src/11_server`??Upbit Trader ?뚮옯?쇱쓽 **REST API쨌WebSocket ?쒕쾭 怨꾩링**???대떦?⑸땲??

- **?꾨젅?꾩썙??*: FastAPI (ASGI)
- **?ㅼ떆媛??듭떊**: WebSocket (二쇰Ц쨌罹붾뱾 ?ㅽ듃由щ컢)
- **?몄쬆**: JWT Bearer ?좏겙
- **Rate Limit**: Redis 湲곕컲 ?щ씪?대뵫 ?덈룄??
- **CORS**: ?섍꼍 蹂???ㅼ젙 ?덉슜 Origin
- **紐⑤땲?곕쭅**: Prometheus metrics (`/metrics`)

> ?좑툘 **以묒슂: ?곗씠?곕쿋?댁뒪 ?ㅼ젙 ?꾩튂**
>
> ?곗씠?곕쿋?댁뒪 ?곌껐 ?ㅼ젙 UI??**`src/data_01/` ?대뜑**???덉뒿?덈떎.
> - TimescaleDB: `src/data_01/timescale/ui/`
> - Redis: `src/data_01/redis/ui/`
> - MongoDB: `src/data_01/mongodb/ui/`
> - Kafka: `src/data_01/kafka/ui/`
> - ClickHouse: `src/data_01/clickhouse/ui/`
> - PostgreSQL: `src/data_01/postgres/ui/`
>
> `11_server`??**?쒕쾭 ?먯껜 ?ㅼ젙**(?ы듃, CORS, ?몄쬆 ??留?愿由ы빀?덈떎.
> DB ?곌껐? 硫붿씤 ?깆쓽 **"?곗씠?곕쿋?댁뒪" 硫붾돱**?먯꽌 愿由ы븯?몄슂.

---

## ?대뜑 援ъ“

```
src/11_server/
?쒋?? README.md                    # ???뚯씪
?쒋?? __init__.py                  # 二쇱슂 而댄룷?뚰듃 re-export
??
?쒋?? core/                        # ?듭떖 ?쒕쾭 濡쒖쭅
??  ?쒋?? fastapi_app.py           # FastAPI ???앹꽦, 誘몃뱾?⑥뼱 ?깅줉, ?쇱슦???곌껐
??  ?쒋?? websocket_manager.py     # WebSocket ?곌껐 ? 愿由?
??  ?붴?? session_manager.py       # JWT ?몄뀡 愿由?
??
?쒋?? api/                         # REST API ?붾뱶?ъ씤??
??  ?쒋?? candles.py               # GET /api/v1/candles  ??罹붾뱾 ?곗씠??議고쉶
??  ?쒋?? symbols.py               # GET /api/v1/symbols  ???щ낵 紐⑸줉 議고쉶
??  ?쒋?? orders.py                # POST /api/v1/orders  ??二쇰Ц 愿由?
??  ?붴?? health.py                # GET /health          ???쒕쾭 ?곹깭 ?뺤씤
??
?쒋?? workers/                     # 諛깃렇?쇱슫???뚯빱
??  ?쒋?? data_sync.py             # TimescaleDB ??Redis ?ㅼ떆媛??숆린??
??  ?쒋?? gap_detector.py          # ?곗씠??Gap ?먯?
??  ?붴?? aggregator.py            # OHLCV CAGG Refresh
??
?쒋?? middleware/                  # 誘몃뱾?⑥뼱
??  ?쒋?? rate_limiter.py          # Redis 湲곕컲 Rate Limit
??  ?쒋?? auth_middleware.py       # JWT ?몄쬆 誘몃뱾?⑥뼱
??  ?붴?? cors_middleware.py       # CORS ?ㅼ젙
??
?쒋?? config/                      # ?쒕쾭 ?ㅼ젙
??  ?쒋?? server_config.py         # ?몄뒪?맞룻룷?맞룸뵒踰꾧렇 ?ㅼ젙
??  ?붴?? redis_config.py          # Redis ?곌껐 ?ㅼ젙
??
?쒋?? utils/                       # ?좏떥由ы떚
??  ?쒋?? response_formatter.py    # 怨듯넻 ?묐떟 ?щ㎎
??  ?붴?? error_handlers.py        # ?꾩뿭 ?덉쇅 ?몃뱾??
??
?쒋?? ui/                          # PyQt5 ?쒕쾭 愿由?UI (?쒕쾭 ?꾩슜)
??  ?쒋?? settings/                # ?쒕쾭 ?ㅼ젙 UI
??  ??  ?쒋?? server_settings.ui
??  ??  ?붴?? widget_server_settings.py
??  ?붴?? monitoring/              # ?쒕쾭 紐⑤땲?곕쭅 UI
??      ?쒋?? server_status.ui
??      ?붴?? widget_server_status.py
??
?붴?? websocket/                   # WebSocket ?몃뱾??
    ?붴?? handlers.py              # WS ?대깽???쇱슦??
```

---

## ?ㅼ튂 諛⑸쾿

### 1. Python ?섏〈???ㅼ튂

```bash
pip install -r requirements.txt
```

二쇱슂 ?⑦궎吏: `fastapi`, `uvicorn[standard]`, `python-jose[cryptography]`, `redis`, `asyncpg`.

### 2. ?섍꼍 蹂???ㅼ젙

`.env` ?뚯씪 ?먮뒗 OS ?섍꼍 蹂?섎줈 ?ㅼ젙?⑸땲??

```env
# ?쒕쾭
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
DEBUG=false

# ?몄쬆
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# TimescaleDB
TIMESCALE_DSN=postgresql+asyncpg://user:password@localhost:5432/upbit_trader

# CORS (?쇳몴 援щ텇)
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

> ?좑툘 **蹂댁븞 二쇱쓽**: `JWT_SECRET_KEY`? DB 鍮꾨?踰덊샇???덈? 肄붾뱶???섎뱶肄붾뵫?섏? 留덉꽭??

---

## ?ㅽ뻾 諛⑸쾿

### 媛쒕컻 紐⑤뱶 (??由щ줈??

```bash
uvicorn src.11_server.core.fastapi_app:create_app --factory \
    --host 0.0.0.0 --port 8000 --reload
```

### ?꾨줈?뺤뀡 紐⑤뱶

```bash
uvicorn src.11_server.core.fastapi_app:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --workers 4 \
    --log-level info
```

### Docker濡??ㅽ뻾

```bash
docker-compose up server
```

---

## API ?붾뱶?ъ씤??臾몄꽌

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)  
ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Health Check

| 硫붿꽌??| 寃쎈줈 | ?ㅻ챸 |
|--------|------|------|
| GET | `/health` | ?쒕쾭 諛?DB ?곌껐 ?곹깭 |
| GET | `/metrics` | Prometheus metrics |

**?묐떟 ?덉떆 (`/health`)**:
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

### 罹붾뱾 API

| 硫붿꽌??| 寃쎈줈 | ?ㅻ챸 |
|--------|------|------|
| GET | `/api/v1/candles` | 罹붾뱾 ?곗씠??議고쉶 |

**荑쇰━ ?뚮씪誘명꽣**:
- `symbol` (?꾩닔): ?щ낵紐?(?? `KRW-BTC`)
- `interval` (?꾩닔): 罹붾뱾 媛꾧꺽 (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- `limit` (?좏깮, 湲곕낯 200): 諛섑솚??罹붾뱾 ??(理쒕? 1000)
- `start` (?좏깮): ISO8601 ?쒖옉 ?쒓컖
- `end` (?좏깮): ISO8601 醫낅즺 ?쒓컖

**?묐떟 ?덉떆**:
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

### ?щ낵 API

| 硫붿꽌??| 寃쎈줈 | ?ㅻ챸 |
|--------|------|------|
| GET | `/api/v1/symbols` | ?꾩껜 ?щ낵 紐⑸줉 議고쉶 |
| GET | `/api/v1/symbols/{symbol}` | ?⑥씪 ?щ낵 ?뺣낫 議고쉶 |

### 二쇰Ц API

| 硫붿꽌??| 寃쎈줈 | ?ㅻ챸 |
|--------|------|------|
| POST | `/api/v1/orders` | 二쇰Ц ?앹꽦 |
| GET | `/api/v1/orders/{order_id}` | 二쇰Ц ?곹깭 議고쉶 |
| DELETE | `/api/v1/orders/{order_id}` | 二쇰Ц 痍⑥냼 |

> ?좑툘 **二쇰Ц API???좏슚??JWT ?좏겙???꾩슂?⑸땲??* (`Authorization: Bearer <token>` ?ㅻ뜑).

### WebSocket ?붾뱶?ъ씤??

| 寃쎈줈 | ?ㅻ챸 |
|------|------|
| `ws://localhost:8000/ws/candles/{symbol}` | ?ㅼ떆媛?罹붾뱾 ?ㅽ듃由щ컢 |
| `ws://localhost:8000/ws/orderbook/{symbol}` | ?ㅼ떆媛??멸?李??ㅽ듃由щ컢 |

---

## ?ㅼ젙 諛⑸쾿

### ?쒕쾭 ?ㅼ젙 (`src/11_server/config/server_config.py`)

| ?ㅼ젙 ??| 湲곕낯媛?| ?ㅻ챸 |
|---------|--------|------|
| `SERVER_HOST` | `0.0.0.0` | 諛붿씤???몄뒪??|
| `SERVER_PORT` | `8000` | ?쒕쾭 ?ы듃 |
| `DEBUG` | `false` | ?붾쾭洹?紐⑤뱶 |
| `WORKERS` | `1` | ?뚯빱 ?꾨줈?몄뒪 ??|

### Rate Limit ?ㅼ젙

| ?ㅼ젙 ??| 湲곕낯媛?| ?ㅻ챸 |
|---------|--------|------|
| `RATE_LIMIT_PER_MINUTE` | `100` | 遺꾨떦 理쒕? ?붿껌 ??|
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate Limit ?덈룄??|

### JWT ?ㅼ젙

| ?ㅼ젙 ??| 湲곕낯媛?| ?ㅻ챸 |
|---------|--------|------|
| `JWT_SECRET_KEY` | (?꾩닔) | ?좏겙 ?쒕챸 ??|
| `JWT_ALGORITHM` | `HS256` | ?쒕챸 ?뚭퀬由ъ쬁 |
| `JWT_EXPIRE_MINUTES` | `60` | ?좏겙 留뚮즺 ?쒓컙 |

---

## ?쒕쾭 ?쒖뼱 UI

PyQt5 硫붿씤 ?깆쓽 **"?쒕쾭" 硫붾돱**?먯꽌 ?쒕쾭瑜??쒖뼱?????덉뒿?덈떎:

- **?쒕쾭 ?곹깭** (`actionServerStatus`): ?꾩옱 ?쒕쾭 ?곹깭 紐⑤땲?곕쭅
- **?쒕쾭 ?ㅼ젙** (`actionServerSettings`): ?몄뒪?맞룻룷?맞룹씤利??ㅼ젙
- **FastAPI Swagger** (`actionFastAPI`): 釉뚮씪?곗??먯꽌 Swagger UI ?닿린
- **WebSocket ?곌껐** (`actionWebSocket`): WebSocket ?대씪?댁뼵???뚯뒪??

---

## ?몃윭釉붿뒋??媛?대뱶

### ?쒕쾭媛 ?쒖옉?섏? ?딅뒗 寃쎌슦

1. **?ы듃 異⑸룎 ?뺤씤**:
   ```bash
   lsof -i :8000
   ```
2. **Redis ?곌껐 ?뺤씤**:
   ```bash
   redis-cli ping   # PONG ?묐떟???덉뼱???뺤긽
   ```
3. **?섍꼍 蹂???뺤씤**:
   ```bash
   echo $JWT_SECRET_KEY
   echo $TIMESCALE_DSN
   ```

### ?몄쬆 ?ㅻ쪟 (401 Unauthorized)

- `Authorization: Bearer <token>` ?ㅻ뜑媛 ?ы븿?섏뼱 ?덈뒗吏 ?뺤씤
- ?좏겙 留뚮즺 ?щ? ?뺤씤 (`JWT_EXPIRE_MINUTES` ?ㅼ젙)
- `JWT_SECRET_KEY`媛 ?쒕쾭? ?대씪?댁뼵???숈씪?쒖? ?뺤씤

### Rate Limit ?ㅻ쪟 (429 Too Many Requests)

- `RATE_LIMIT_PER_MINUTE` 媛?利앷?
- Redis媛 ?뺤긽 ?숈옉 以묒씤吏 ?뺤씤
- ?붿껌 鍮덈룄瑜?以꾩씠嫄곕굹 罹먯떛 ?곸슜

### WebSocket ?곌껐 ?ㅽ뙣

- 諛⑺솕踰쎌뿉??WebSocket ?ы듃 ?덉슜 ?щ? ?뺤씤
- CORS `CORS_ORIGINS` ?ㅼ젙???대씪?댁뼵??Origin ?ы븿 ?щ? ?뺤씤
- 濡쒓렇?먯꽌 `WebSocketManager` 愿???ㅻ쪟 ?뺤씤:
  ```bash
  grep "WebSocket" logs/server.log
  ```

### TimescaleDB ?곌껐 ?ㅻ쪟

- `TIMESCALE_DSN` ?섍꼍 蹂???뺥솗???뺤씤
- PostgreSQL ?쒕퉬???ㅽ뻾 ?щ? ?뺤씤:
  ```bash
  pg_isready -h localhost -p 5432
  ```
- Docker ?ъ슜 ?? `docker-compose ps timescale`

---

## 濡쒓렇 ?뺤씤

```bash
# ?ㅼ떆媛?濡쒓렇 ?ㅽ듃由щ컢
tail -f logs/server.log

# ?ㅻ쪟留??꾪꽣留?
grep "ERROR\|CRITICAL" logs/server.log

# API ?붿껌 濡쒓렇
grep "api/v1" logs/server.log
```

---

*理쒖쥌 ?섏젙: 2026-03-19 | Copilot*

