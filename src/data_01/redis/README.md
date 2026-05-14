# redis ??Redis 紐⑤뱢

## 紐⑹쟻

Upbit ?몃젅?대뵫 ?쒖뒪?쒖쓽 怨좎꽦??罹먯떛, pub/sub 硫붿떆吏? gap-fill ?먮? ?대떦?⑸땲??

## 援ъ“

```
redis/
?쒋?? core/               # ?곌껐 ? 諛??ㅼ젙
??  ?쒋?? config.py       # Redis ?곌껐 ?ㅼ젙 (?섍꼍蹂??湲곕컲)
??  ?쒋?? connection.py   # redis.asyncio ?곌껐 愿由?
??  ?쒋?? client.py       # ?숆린 RedisClient ?섑띁
??  ?붴?? lite_cache.py   # ?몃찓紐⑤━ LiteCache (Redis ?녿뒗 ?섍꼍 ?泥?
?쒋?? cache/              # L1 罹먯떆 ?곗궛
??  ?쒋?? l1_cache.py     # 理쒓렐 罹붾뱾 LRANGE 罹먯떆
??  ?붴?? hydrator.py     # TimescaleDB ??Redis 罹먯떆 梨꾩슦湲?
?쒋?? pubsub/             # Pub/Sub 硫붿떆吏?
??  ?쒋?? publisher.py    # 硫붿떆吏 諛쒗뻾
??  ?붴?? subscriber.py   # 硫붿떆吏 援щ룆
?쒋?? queue/              # Gap-fill ??
??  ?붴?? gap_queue.py    # Redis 湲곕컲 gap ?묒뾽 ??
?쒋?? health_check.py     # ?곌껐 ?곹깭 ?뺤씤 (RESP ?꾨줈?좎퐳)
?붴?? ui/                 # PyQt5 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹?
    ?붴?? redis_dialog.py
```

## ?ъ슜踰?

```python
from redis.core import get_client, RedisConfig
from redis.cache.l1_cache import L1Cache
from redis.pubsub.publisher import Publisher
from redis.queue.gap_queue import GapQueue

# 鍮꾨룞湲?Redis ?대씪?댁뼵??
client = await get_client()

# L1 罹먯떆 ?곗궛
cache = L1Cache(client)
await cache.push("KRW-BTC", "1m", candle_data)

# 硫붿떆吏 諛쒗뻾
pub = Publisher(client)
await pub.publish("candle_update", {"symbol": "KRW-BTC"})

# Gap-fill ??
queue = GapQueue(client)
await queue.enqueue(gap_task)
```

### health_check.py ?숈옉 (RESP ?꾨줈?좎퐳)

`check_redis_connection()` ?⑥닔??`socket`?쇰줈 吏곸젒 RESP ?꾨줈?좎퐳???ъ슜?⑸땲??

1. ?뚯폆 ?곌껐 (timeout: 5珥?
2. 鍮꾨?踰덊샇媛 ?덉쑝硫?`AUTH` 紐낅졊 ?꾩넚 ??50ms ?湲????묐떟 ?뺤씤
3. `PING` 紐낅졊 ?꾩넚 ??50ms ?湲????묐떟 ?뺤씤
4. `+PONG` ?먮뒗 `NOAUTH` ?ы븿 ??`"green"` 諛섑솚

```python
from redis.health_check import check_redis_connection

status = check_redis_connection()  # "green" | "red" | "gray"
```

## ?섍꼍蹂??

| 蹂??| 湲곕낯媛?| ?ㅻ챸 |
|------|--------|------|
| `REDIS_HOST` | `localhost` | Redis ?쒕쾭 ?몄뒪??|
| `REDIS_PORT` | `6379` | Redis ?쒕쾭 ?ы듃 |
| `REDIS_PASSWORD` | (?놁쓬) | Redis ?몄쬆 鍮꾨?踰덊샇 |

## ?몃윭釉붿뒋??

### Windows ?섍꼍蹂??異⑸룎

**利앹긽**: health check媛 "red" 諛섑솚, ?곌껐 嫄곕?

**?먯씤**: Windows ?ъ슜???섍꼍蹂?섏뿉 ephemeral ?ы듃媛 ?ㅼ젙??寃쎌슦

```powershell
# ?섎せ????
# REDIS_PORT=58530  ??ephemeral ?ы듃 踰붿＜ (?ㅻ쪟)

# ?뺤씤
[System.Environment]::GetEnvironmentVariable("REDIS_PORT", "User")

# ??젣 (湲곕낯媛?6379濡?蹂듭썝)
[System.Environment]::SetEnvironmentVariable("REDIS_PORT", $null, "User")
```

### recv() ?묐떟 ?湲?遺議?

**利앹긽**: PING ??鍮??묐떟, "red" 諛섑솚

**?닿껐**: `health_check.py`??`time.sleep(0.05)` 異붽? (?대? ?곸슜??

```python
sock.sendall(b"*1\r\n$4\r\nPING\r\n")
time.sleep(0.05)  # ???묐떟 ?湲?
ping_resp = sock.recv(64).decode(errors="replace").strip()
```

### Docker 而⑦뀒?대꼫 ?곌껐 遺덇?

**?먯씤**: Redis 而⑦뀒?대꼫媛 `127.0.0.1`留?諛붿씤?⑺븳 寃쎌슦

**?닿껐**: `docker-compose.yml`?먯꽌 `--bind 0.0.0.0` ?뺤씤

```yaml
command: >
  sh -c "redis-server
  --bind 0.0.0.0   # ???몄뒪?몄뿉???묎렐 ?덉슜
  --protected-mode no
  ..."
```

## 李멸퀬 臾몄꽌

- `work_order/DB?ㅺ퀎.md` 짠4 Redis
- `src/data_01/README.md` ???곗씠??怨꾩링 媛쒖슂

