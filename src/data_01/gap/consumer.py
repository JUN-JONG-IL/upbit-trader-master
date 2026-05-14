# -*- coding: utf-8 -*-
"""
Gap job ?Œë¹„??consumer) ?Œì»¤ - ?¨ì¼ ?Œì¼ PoC

ê¸°ëŠ¥ ?”ì•½:
- Redis ZSET (gap_fill_queue)?ì„œ ?°ì„ ?œìœ„ê°€ ê°€???’ì? job???ˆì „?˜ê²Œ ì¶”ì¶œ(ZPOPMAX ?œë„, ?¤íŒ¨ ??fallback)
- job JSON ?Œì‹± ë°?ë©±ë“±??claim ì²˜ë¦¬:
    - claim ?? gap:claim:{job_id} (SET NX PX ?¼ë¡œ ?¨ì¼ ?Œì»¤ ?Œìœ )
    - processed ?? gap:processed:{job_id} (ì¤‘ë³µ ì²˜ë¦¬ ë°©ì?)
- ì²˜ë¦¬ ë¡œì§(ë°±í•„)?€ PoC ?˜ì????¤í…?¼ë¡œ êµ¬í˜„?˜ì–´ ?ˆìœ¼ë©?
  ?¤ì œ ?˜ê²½?ï¿½ï¿½ëŠ” Kafka replay / ê±°ë˜??REST / S3 ?¬ìƒ ì¤??˜ë‚˜ë¡??€ì²´í•´????
- ì²˜ë¦¬ ?±ê³µ ??processed ?¤ë? ?¤ì •?˜ê³  ë¡œê·¸ ê¸°ë¡.
- ì²˜ë¦¬ ?¤íŒ¨ ??attemptsë¥?ì¦ê??œì¼œ ?¬í(ì§€?˜ì  ë°±ì˜¤???ìˆ˜)?˜ê±°??DLQ???´ë™.
- ?ˆì „ ì¢…ë£Œ, ë¦¬ì†Œ???•ë¦¬ ì§€?? ?¤ì–‘??redis ?´ë¼?´ì–¸???¸í™˜(redis.asyncio / aioredis)

?¬ìš©ë²?
- ?¨ë°œ???¤í–‰(??ë²ˆë§Œ ì²˜ë¦¬):
    python -m src.data_01.gap.consumer --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"
- ?°ëª¬ ëª¨ë“œ:
    python -m src.data_01.gap.consumer --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"

ì£¼ì˜:
- ?¤ì œ ë°±í•„ ë¡œì§?€ stub?…ë‹ˆ?? production ?µí•© ?„ì— ?¬ìƒ(restore) ?ŒìŠ¤ë¥?êµ¬í˜„?˜ì„¸??
- ëª¨ë“  ì£¼ì„?€ ?œê??…ë‹ˆ??
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import hashlib
from typing import Any, Dict, Optional

import orjson  # type: ignore

logger = logging.getLogger("gap.consumer")


def _get_default_redis_url() -> str:
    """config.yaml ê¸°ë°˜ Redis URL ë°˜í™˜ (fallback: ?¬íŠ¸ 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_gc", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


# Redis ???¤ì •
ZSET_KEY = "gap_fill_queue"
CLAIM_KEY_PREFIX = "gap:claim:"       # claim key: gap:claim:{job_id}
PROCESSED_KEY_PREFIX = "gap:processed:"  # processed key: gap:processed:{job_id}
DLQ_LIST = "gap_fill_dlq"             # ?¤íŒ¨/?êµ¬?¤íŒ¨ job ë³´ê? ë¦¬ìŠ¤??

# Claim ë§Œë£Œ(ms)
CLAIM_TTL_MS = 60_000  # 60ì´?ê¸°ë³¸

# ?¬ì‹œ???œí•œ
MAX_ATTEMPTS = 5

# ?¬í ê¸°ë³¸ ê°€ì¤‘ì¹˜(?°ì„ ?œìœ„ ?¤ì???ë³´ì •)
REQUEUE_BASE_DELAY = 30  # ì´?


class RedisCompat:
    """
    ê°„ë‹¨??Redis ?¸í™˜ ?ˆì´???½ê¸°/?°ê¸°/claim/zpop ì§€??
    - redis.asyncio ?ëŠ” aioredis ????ì§€??ê¶Œì¥: redis.asyncio)
    """
    def __init__(self, client: Any):
        self._client = client

    # ZPOPMAX wrapper: ë°˜í™˜ ?•ì‹ ?µì¼
    async def zpopmax(self, name: str, count: int = 1):
        """
        ?œë„ ?œì„œ:
        - redis-py(>=4) / redis.asyncio: await client.zpopmax(name, count)
        - aioredis: await client.zpopmax(name, count)
        - fallback: zrevrange + zrem
        ë°˜í™˜: list of tuples [(member_str, score_float), ...]
        """
        try:
            # ?œì?: redis.asyncio
            res = await self._client.zpopmax(name, count)
            # redis-py returns list of (member, score) where member is bytes or str
            return res
        except Exception:
            # fallback: zrevrange + zrem
            try:
                members = await self._client.zrevrange(name, 0, count - 1, withscores=True)
                if not members:
                    return []
                # ë©¤ë²„ ?œê±°
                # aioredis/redis-py ì°¨ì´???€?? zrem accepts *members or single
                keys = [m for (m, s) in members]
                try:
                    await self._client.zrem(name, *keys)
                except TypeError:
                    # some clients expect different signature
                    for k in keys:
                        await self._client.zrem(name, k)
                return members
            except Exception:
                logger.exception("[RedisCompat] zpopmax/fallback ?¤íŒ¨")
                return []

    async def set_claim(self, key: str, value: str, px: int) -> bool:
        """
        claim ?¤ì •: SET key value NX PX px
        ë°˜í™˜ True?´ë©´ claim ?±ê³µ
        """
        try:
            # redis.asyncio / redis-py interface
            res = await self._client.set(key, value, nx=True, px=px)
            return bool(res)
        except TypeError:
            # fallback: older signature may not support keywords
            try:
                res = await self._client.execute_command("SET", key, value, "NX", "PX", str(px))
                return res == b"OK" or res == "OK"
            except Exception:
                logger.exception("[RedisCompat] set_claim ?´ë°± ?¤íŒ¨")
                return False
        except Exception:
            logger.exception("[RedisCompat] set_claim ?¤íŒ¨")
            return False

    async def get(self, key: str) -> Optional[bytes]:
        try:
            return await self._client.get(key)
        except Exception:
            logger.debug("[RedisCompat] get ?¤íŒ¨", exc_info=True)
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        try:
            await self._client.set(key, value, ex=ex)
        except Exception:
            logger.debug("[RedisCompat] set ?¤íŒ¨", exc_info=True)

    async def rpush(self, key: str, value: str):
        try:
            await self._client.rpush(key, value)
        except Exception:
            logger.exception("[RedisCompat] rpush ?¤íŒ¨")

    async def zadd(self, name: str, mapping: dict):
        try:
            await self._client.zadd(name, mapping)
        except Exception:
            # ?¬ëŸ¬ ?œê·¸?ˆì²˜ ?€ì²??¼ì´ë¸ŒëŸ¬ë¦¬ë³„ ì°¨ì´)
            try:
                for member, score in mapping.items():
                    await self._client.zadd(name, score, member)  # type: ignore
            except Exception:
                logger.exception("[RedisCompat] zadd ?´ë°± ?¤íŒ¨")
                raise

    async def delete(self, key: str):
        try:
            await self._client.delete(key)
        except Exception:
            logger.debug("[RedisCompat] delete ?¤íŒ¨", exc_info=True)


# ---------------------------
# ë°±í•„(ì²˜ë¦¬) ê´€??? í‹¸/?¤í…
# ---------------------------
async def perform_backfill(job: Dict[str, Any], timescale_pool: Any) -> bool:
    """
    ?¤ì œ ë°±í•„ ?‘ì—…???˜í–‰?˜ëŠ” ?ë¦¬(?„ì¬??PoC stub).
    - job: job_dict (?Œì‹±??JSON)
    - timescale_pool: asyncpg pool ê°™ì? DB ì»¤ë„¥???€
    ë°˜í™˜: ?±ê³µ True/False

    ?¤ì œ ?˜ê²½?ì„œ???¤ìŒ ?‘ì—… ì¤??˜ë‚˜ ?´ìƒ??êµ¬í˜„:
    1) Kafka replay (symbol/time range)
    2) ê±°ë˜??REST historical fetch
    3) S3/Parquet ?„ì¹´?´ë¸Œ ë³µêµ¬
    ê·¸ë¦¬ê³?Timescale??idempotent insert ?˜í–‰.
    """
    try:
        symbol = job.get("symbol")
        start = job.get("start")
        end = job.get("end")
        job_id = job.get("job_id")
        logger.info("[Backfill] ?œì‘: symbol=%s start=%s end=%s job_id=%s", symbol, start, end, job_id)

        # PoC: ?¤ì œ ?¬ìƒ ?€??short sleepë¡??‘ì—…???œë??ˆì´??
        await asyncio.sleep(0.5)

        # PoC?ì„œ??Timescale??ê°„ë‹¨??ë¡œê·¸ ?¸ì„œ??? íƒ ?¬í•­) ?ëŠ” ?•ì¸ ì¿¼ë¦¬ë§??˜í–‰
        # ?¤ì œ?˜ê²½: idempotent insert êµ¬í˜„ ?„ìš” (INSERT ... ON CONFLICT)
        try:
            if timescale_pool is not None:
                # ?? ë¡œê·¸ ?Œì´ë¸”ì— ?½ì…(?ŒìŠ¤?¸ìš©)
                async with timescale_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO IF NOT EXISTS gap_backfill_log (job_id, symbol, start_ts, end_ts, created_at) VALUES ($1, $2, $3, $4, NOW())",
                        job_id, symbol, start, end
                    )
        except Exception:
            # ??DDL???†ì„ ???ˆìœ¼ë¯€ë¡?ë¬´ì‹œ(? íƒ)
            pass

        logger.info("[Backfill] ?±ê³µ: job_id=%s", job_id)
        return True
    except Exception:
        logger.exception("[Backfill] ?ˆì™¸ ë°œìƒ")
        return False


# ---------------------------
# ?Œë¹„??ë©”ì¸ ?´ë˜??
# ---------------------------
class GapConsumer:
    """
    Gap job ?Œë¹„??
    - redis_client: raw redis client (redis.asyncio ?ëŠ” aioredis)
    - timescale_pool: asyncpg pool (? íƒ)
    """

    def __init__(self, redis_client: Any, timescale_pool: Any = None, claim_ttl_ms: int = CLAIM_TTL_MS):
        self.redis = RedisCompat(redis_client)
        self._raw_redis = redis_client
        self.timescale_pool = timescale_pool
        self._claim_ttl_ms = claim_ttl_ms
        self._running = False

    async def _pop_job(self) -> Optional[Dict[str, Any]]:
        """
        ZSET?ì„œ ìµœê³  ?°ì„  job??êº¼ëƒ„(zpopmax). ë°˜í™˜: parsed job dict ?ëŠ” None
        """
        try:
            items = await self.redis.zpopmax(ZSET_KEY, 1)
            if not items:
                return None
            # items: [(member, score)] - member may be bytes or str
            member, score = items[0]
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            try:
                job = orjson.loads(member)
            except Exception:
                # fallback to str -> eval/json
                import json
                job = json.loads(member)
            # attach raw_member for DLQ/redis requeue if needed
            job["_raw_member"] = member
            job["_score"] = float(score)
            return job
        except Exception:
            logger.exception("[GapConsumer] pop_job ?¤íŒ¨")
            return None

    async def _claim_job(self, job_id: str, owner_id: str) -> bool:
        key = CLAIM_KEY_PREFIX + job_id
        return await self.redis.set_claim(key, owner_id, px=self._claim_ttl_ms)

    async def _mark_processed(self, job_id: str, ttl_seconds: int = 86400):
        key = PROCESSED_KEY_PREFIX + job_id
        await self.redis.set(key, "1", ex=ttl_seconds)

    async def _is_processed(self, job_id: str) -> bool:
        key = PROCESSED_KEY_PREFIX + job_id
        res = await self.redis.get(key)
        return bool(res)

    async def _requeue_job(self, job: Dict[str, Any], attempts: int):
        """
        ?¬í: attempts ì¦ê?, score ?¬ê³„??ì§€?˜ì  backoff ê¸°ë°˜)
        - attemptsê°€ MAX_ATTEMPTS ì´ˆê³¼?˜ë©´ DLQë¡??´ë™
        """
        job["attempts"] = attempts
        raw = orjson.dumps(job).decode("utf-8")
        if attempts > MAX_ATTEMPTS:
            logger.warning("[GapConsumer] ìµœë? ?¬ì‹œ??ì´ˆê³¼, DLQë¡??´ë™ job_id=%s attempts=%d", job.get("job_id"), attempts)
            await self.redis.rpush(DLQ_LIST, raw)
            return
        # ì§€?˜ì  ì§€??ê¸°ë°˜ ?°ì„ ?œìœ„(ê°„ë‹¨): ê¸°ì¡´ scoreë¥?ì¤„ì—¬???œìœ„ë¥???¶¤
        base_score = job.get("_score", 1.0)
        delay_seconds = REQUEUE_BASE_DELAY * (2 ** (attempts - 1))
        new_score = base_score / (1 + attempts)  # ê°„ë‹¨ ?¤ì½”??ê°ì†Œ
        # ?¤ì œ ?´ì˜?ì„œ???¬ì‹œ???ˆì•½ ?œìŠ¤?œì„ ?¬ìš©?˜ëŠ” ê²ƒì´ ??ì¢‹ìŒ
        await self.redis.zadd(ZSET_KEY, {raw: new_score})
        logger.info("[GapConsumer] ?¬í: job_id=%s attempts=%d new_score=%.4f delay=%ds", job.get("job_id"), attempts, new_score, delay_seconds)

    async def _process_job(self, job: Dict[str, Any], owner_id: str):
        """
        ?¨ê±´ job ì²˜ë¦¬ ?Œë¡œ??
        - ë©±ë“±??ê²€??
        - claim ?œë„
        - perform_backfill ?¸ì¶œ
        - ?±ê³µ: mark_processed
        - ?¤íŒ¨: ?¬í(?ëŠ” DLQ)
        """
        job_id = job.get("job_id") or hashlib.sha256(orjson.dumps(job)).hexdigest()
        # ?´ë? ì²˜ë¦¬?˜ì—ˆ?”ì? ?•ì¸
        if await self._is_processed(job_id):
            logger.info("[GapConsumer] ?´ë? ì²˜ë¦¬??job ê±´ë„ˆ?€: %s", job_id)
            return

        # claim ?œë„
        claimed = await self._claim_job(job_id, owner_id)
        if not claimed:
            logger.debug("[GapConsumer] claim ?¤íŒ¨ (?¤ë¥¸ ?Œì»¤ ì²˜ë¦¬ ì¤?: %s", job_id)
            return

        # attempts ì¹´ìš´??ê´€ë¦?
        attempts = int(job.get("attempts", 0))
        try:
            ok = await perform_backfill(job, self.timescale_pool)
            if ok:
                await self._mark_processed(job_id)
                logger.info("[GapConsumer] ì²˜ë¦¬ ?±ê³µ: %s", job_id)
            else:
                attempts += 1
                await self._requeue_job(job, attempts)
                logger.warning("[GapConsumer] ì²˜ë¦¬ ?¤íŒ¨ - ?¬í: %s attempts=%d", job_id, attempts)
        except Exception:
            attempts += 1
            await self._requeue_job(job, attempts)
            logger.exception("[GapConsumer] ì²˜ë¦¬ ?ˆì™¸ - ?¬í: %s attempts=%d", job_id, attempts)

    async def run_once(self, owner_id: Optional[str] = None) -> int:
        """
        ?¨ë°œ??ì²˜ë¦¬: ?˜ë‚˜??job??ì²˜ë¦¬(?ëŠ” ?œë„)?˜ê³  ì¢…ë£Œ.
        ë°˜í™˜: ì²˜ë¦¬(?œë„)??job ??0/1)
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        job = await self._pop_job()
        if not job:
            logger.debug("[GapConsumer] ì²˜ë¦¬??job ?†ìŒ")
            return 0
        await self._process_job(job, owner)
        return 1

    async def run(self, poll_interval: float = 1.0, owner_id: Optional[str] = None):
        """
        ?°ëª¬ ëª¨ë“œ: ê³„ì†?´ì„œ ZSET?ì„œ job??êº¼ë‚´ ì²˜ë¦¬.
        ?ˆì „ ì¢…ë£Œ???¸ë??ì„œ loop??SIGINT/SIGTERM???„ë‹¬?´ì•¼ ??
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        self._running = True
        logger.info("[GapConsumer] ?°ëª¬ ?œì‘ owner=%s", owner)
        try:
            while self._running:
                try:
                    job = await self._pop_job()
                    if job:
                        await self._process_job(job, owner)
                        # ì¦‰ì‹œ ?¤ìŒ job ì²˜ë¦¬ (ï¿½ï¿½?€ ?¬ì‹œ???€ê¸??†ìŒ)
                        await asyncio.sleep(0.01)
                    else:
                        # ?´ë§ ë°±ì˜¤??
                        await asyncio.sleep(poll_interval)
                except Exception:
                    logger.exception("[GapConsumer] ë£¨í”„ ì¤??ˆì™¸ ë°œìƒ")
                    await asyncio.sleep(1.0)
        finally:
            self._running = False
            logger.info("[GapConsumer] ?°ëª¬ ì¢…ë£Œ")

    def stop(self):
        self._running = False


# ---------------------------
# CLI / ?°ì²˜
# ---------------------------
async def create_redis_client(url: str):
    """
    redis-clients ì´ˆê¸°?? redis.asyncio ë¥??°ì„  ?œë„, ?†ìœ¼ë©?aioredisë¥??œë„.
    """
    try:
        import importlib
        mod = importlib.import_module("redis.asyncio")
        Redis = getattr(mod, "Redis")
        client = Redis.from_url(url, decode_responses=False)
        await client.ping()
        return client
    except Exception:
        # aioredis fallback
        try:
            import importlib
            mod = importlib.import_module("aioredis")
            client = getattr(mod, "from_url")(url)
            await client.ping()
            return client
        except Exception:
            logger.exception("[GapConsumer] Redis ?´ë¼?´ì–¸???ì„± ?¤íŒ¨")
            raise


async def create_timescale_pool(dsn: Optional[str]):
    """
    asyncpg pool ?ì„±(? íƒ). dsn ?†ìœ¼ë©?None ë°˜í™˜.
    """
    if not dsn:
        return None
    try:
        import asyncpg  # type: ignore
        pool = await asyncpg.create_pool(dsn)
        return pool
    except Exception:
        logger.exception("[GapConsumer] timescale pool ?ì„± ?¤íŒ¨")
        return None


def _setup_logging():
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(handler)
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


async def _main_async(args):
    _setup_logging()
    redis_client = await create_redis_client(args.redis_url)
    timescale_pool = await create_timescale_pool(args.timescale_dsn)
    consumer = GapConsumer(redis_client, timescale_pool)

    if args.once:
        await consumer.run_once()
        # ?ˆì „ ì¢…ë£Œ
        try:
            await _safe_close(redis_client)
        except Exception:
            pass
        if timescale_pool:
            await timescale_pool.close()
    else:
        # ?°ëª¬ ëª¨ë“œ: ?œê·¸??ì²˜ë¦¬
        loop = asyncio.get_running_loop()
        stop_evt = asyncio.Event()

        def _on_stop():
            logger.info("[GapConsumer] ì¢…ë£Œ ? í˜¸ ?˜ì‹ ")
            consumer.stop()
            stop_evt.set()

        try:
            loop.add_signal_handler(signal.SIGINT, _on_stop)   # type: ignore[name-defined]
            loop.add_signal_handler(signal.SIGTERM, _on_stop)  # type: ignore[name-defined]
        except Exception:
            logger.debug("[GapConsumer] ?œê·¸???¸ë“¤???±ë¡ ë¶ˆê?(?˜ê²½?œí•œ)")

        # ë°±ê·¸?¼ìš´???¤í–‰
        task = asyncio.create_task(consumer.run(poll_interval=args.interval))
        await stop_evt.wait()
        # ?•ë¦¬
        try:
            await _safe_close(redis_client)
        except Exception:
            pass
        if timescale_pool:
            await timescale_pool.close()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except Exception:
            task.cancel()
            try:
                await task
            except Exception:
                pass


async def _safe_close(obj: Any):
    """
    Redis/DB client ?ˆì „ ì¢…ë£Œ: aclose -> close ?œìœ¼ë¡??œë„
    """
    try:
        if hasattr(obj, "aclose"):
            res = obj.aclose()
            if asyncio.iscoroutine(res):
                await res
            return
        if hasattr(obj, "close"):
            res = obj.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        logger.debug("[GapConsumer] ?ˆì „ ì¢…ë£Œ ì¤??ˆì™¸", exc_info=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gap consumer worker")
    parser.add_argument("--once", action="store_true", help="??ë²ˆë§Œ ì²˜ë¦¬?˜ê³  ì¢…ë£Œ")
    parser.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    parser.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("GAP_CONSUMER_INTERVAL", "1.0")))
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        logger.info("[GapConsumer] ?¬ìš©???¸í„°?½íŠ¸ë¡?ì¢…ë£Œ")
    except Exception:
        logger.exception("[GapConsumer] ?ˆì™¸ë¡?ì¢…ë£Œ")
        sys.exit(1)


if __name__ == "__main__":
    main()
