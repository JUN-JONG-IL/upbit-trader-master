# -*- coding: utf-8 -*-
"""
Gap job ?뚮퉬??consumer) ?뚯빱 - ?⑥씪 ?뚯씪 PoC

湲곕뒫 ?붿빟:
- Redis ZSET (gap_fill_queue)?먯꽌 ?곗꽑?쒖쐞媛 媛???믪? job???덉쟾?섍쾶 異붿텧(ZPOPMAX ?쒕룄, ?ㅽ뙣 ??fallback)
- job JSON ?뚯떛 諛?硫깅벑??claim 泥섎━:
    - claim ?? gap:claim:{job_id} (SET NX PX ?쇰줈 ?⑥씪 ?뚯빱 ?뚯쑀)
    - processed ?? gap:processed:{job_id} (以묐났 泥섎━ 諛⑹?)
- 泥섎━ 濡쒖쭅(諛깊븘)? PoC ?섏????ㅽ뀅?쇰줈 援ы쁽?섏뼱 ?덉쑝硫?
  ?ㅼ젣 ?섍꼍?먲옙占쎈뒗 Kafka replay / 嫄곕옒??REST / S3 ?ъ깮 以??섎굹濡??泥댄빐????
- 泥섎━ ?깃났 ??processed ?ㅻ? ?ㅼ젙?섍퀬 濡쒓렇 湲곕줉.
- 泥섎━ ?ㅽ뙣 ??attempts瑜?利앷??쒖폒 ?ы걧(吏?섏쟻 諛깆삤???먯닔)?섍굅??DLQ???대룞.
- ?덉쟾 醫낅즺, 由ъ냼???뺣━ 吏?? ?ㅼ뼇??redis ?대씪?댁뼵???명솚(redis.asyncio / aioredis)

?ъ슜踰?
- ?⑤컻???ㅽ뻾(??踰덈쭔 泥섎━):
    python -m src.data_01.gap.consumer --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"
- ?곕が 紐⑤뱶:
    python -m src.data_01.gap.consumer --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "<DSN>"

二쇱쓽:
- ?ㅼ젣 諛깊븘 濡쒖쭅? stub?낅땲?? production ?듯빀 ?꾩뿉 ?ъ깮(restore) ?뚯뒪瑜?援ы쁽?섏꽭??
- 紐⑤뱺 二쇱꽍? ?쒓??낅땲??
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
    """config.yaml 湲곕컲 Redis URL 諛섑솚 (fallback: ?ы듃 58530, password=dummy)"""
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


# Redis ???ㅼ젙
ZSET_KEY = "gap_fill_queue"
CLAIM_KEY_PREFIX = "gap:claim:"       # claim key: gap:claim:{job_id}
PROCESSED_KEY_PREFIX = "gap:processed:"  # processed key: gap:processed:{job_id}
DLQ_LIST = "gap_fill_dlq"             # ?ㅽ뙣/?곴뎄?ㅽ뙣 job 蹂닿? 由ъ뒪??

# Claim 留뚮즺(ms)
CLAIM_TTL_MS = 60_000  # 60珥?湲곕낯

# ?ъ떆???쒗븳
MAX_ATTEMPTS = 5

# ?ы걧 湲곕낯 媛以묒튂(?곗꽑?쒖쐞 ?ㅼ???蹂댁젙)
REQUEUE_BASE_DELAY = 30  # 珥?


class RedisCompat:
    """
    媛꾨떒??Redis ?명솚 ?덉씠???쎄린/?곌린/claim/zpop 吏??
    - redis.asyncio ?먮뒗 aioredis ????吏??沅뚯옣: redis.asyncio)
    """
    def __init__(self, client: Any):
        self._client = client

    # ZPOPMAX wrapper: 諛섑솚 ?뺤떇 ?듭씪
    async def zpopmax(self, name: str, count: int = 1):
        """
        ?쒕룄 ?쒖꽌:
        - redis-py(>=4) / redis.asyncio: await client.zpopmax(name, count)
        - aioredis: await client.zpopmax(name, count)
        - fallback: zrevrange + zrem
        諛섑솚: list of tuples [(member_str, score_float), ...]
        """
        try:
            # ?쒖?: redis.asyncio
            res = await self._client.zpopmax(name, count)
            # redis-py returns list of (member, score) where member is bytes or str
            return res
        except Exception:
            # fallback: zrevrange + zrem
            try:
                members = await self._client.zrevrange(name, 0, count - 1, withscores=True)
                if not members:
                    return []
                # 硫ㅻ쾭 ?쒓굅
                # aioredis/redis-py 李⑥씠????? zrem accepts *members or single
                keys = [m for (m, s) in members]
                try:
                    await self._client.zrem(name, *keys)
                except TypeError:
                    # some clients expect different signature
                    for k in keys:
                        await self._client.zrem(name, k)
                return members
            except Exception:
                logger.exception("[RedisCompat] zpopmax/fallback ?ㅽ뙣")
                return []

    async def set_claim(self, key: str, value: str, px: int) -> bool:
        """
        claim ?ㅼ젙: SET key value NX PX px
        諛섑솚 True?대㈃ claim ?깃났
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
                logger.exception("[RedisCompat] set_claim ?대갚 ?ㅽ뙣")
                return False
        except Exception:
            logger.exception("[RedisCompat] set_claim ?ㅽ뙣")
            return False

    async def get(self, key: str) -> Optional[bytes]:
        try:
            return await self._client.get(key)
        except Exception:
            logger.debug("[RedisCompat] get ?ㅽ뙣", exc_info=True)
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        try:
            await self._client.set(key, value, ex=ex)
        except Exception:
            logger.debug("[RedisCompat] set ?ㅽ뙣", exc_info=True)

    async def rpush(self, key: str, value: str):
        try:
            await self._client.rpush(key, value)
        except Exception:
            logger.exception("[RedisCompat] rpush ?ㅽ뙣")

    async def zadd(self, name: str, mapping: dict):
        try:
            await self._client.zadd(name, mapping)
        except Exception:
            # ?щ윭 ?쒓렇?덉쿂 ?泥??쇱씠釉뚮윭由щ퀎 李⑥씠)
            try:
                for member, score in mapping.items():
                    await self._client.zadd(name, score, member)  # type: ignore
            except Exception:
                logger.exception("[RedisCompat] zadd ?대갚 ?ㅽ뙣")
                raise

    async def delete(self, key: str):
        try:
            await self._client.delete(key)
        except Exception:
            logger.debug("[RedisCompat] delete ?ㅽ뙣", exc_info=True)


# ---------------------------
# 諛깊븘(泥섎━) 愿???좏떥/?ㅽ뀅
# ---------------------------
async def perform_backfill(job: Dict[str, Any], timescale_pool: Any) -> bool:
    """
    ?ㅼ젣 諛깊븘 ?묒뾽???섑뻾?섎뒗 ?먮━(?꾩옱??PoC stub).
    - job: job_dict (?뚯떛??JSON)
    - timescale_pool: asyncpg pool 媛숈? DB 而ㅻ꽖???
    諛섑솚: ?깃났 True/False

    ?ㅼ젣 ?섍꼍?먯꽌???ㅼ쓬 ?묒뾽 以??섎굹 ?댁긽??援ы쁽:
    1) Kafka replay (symbol/time range)
    2) 嫄곕옒??REST historical fetch
    3) S3/Parquet ?꾩뭅?대툕 蹂듦뎄
    洹몃━怨?Timescale??idempotent insert ?섑뻾.
    """
    try:
        symbol = job.get("symbol")
        start = job.get("start")
        end = job.get("end")
        job_id = job.get("job_id")
        logger.info("[Backfill] ?쒖옉: symbol=%s start=%s end=%s job_id=%s", symbol, start, end, job_id)

        # PoC: ?ㅼ젣 ?ъ깮 ???short sleep濡??묒뾽???쒕??덉씠??
        await asyncio.sleep(0.5)

        # PoC?먯꽌??Timescale??媛꾨떒??濡쒓렇 ?몄꽌???좏깮 ?ы빆) ?먮뒗 ?뺤씤 荑쇰━留??섑뻾
        # ?ㅼ젣?섍꼍: idempotent insert 援ы쁽 ?꾩슂 (INSERT ... ON CONFLICT)
        try:
            if timescale_pool is not None:
                # ?? 濡쒓렇 ?뚯씠釉붿뿉 ?쎌엯(?뚯뒪?몄슜)
                async with timescale_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO IF NOT EXISTS gap_backfill_log (job_id, symbol, start_ts, end_ts, created_at) VALUES ($1, $2, $3, $4, NOW())",
                        job_id, symbol, start, end
                    )
        except Exception:
            # ??DDL???놁쓣 ???덉쑝誘濡?臾댁떆(?좏깮)
            pass

        logger.info("[Backfill] ?깃났: job_id=%s", job_id)
        return True
    except Exception:
        logger.exception("[Backfill] ?덉쇅 諛쒖깮")
        return False


# ---------------------------
# ?뚮퉬??硫붿씤 ?대옒??
# ---------------------------
class GapConsumer:
    """
    Gap job ?뚮퉬??
    - redis_client: raw redis client (redis.asyncio ?먮뒗 aioredis)
    - timescale_pool: asyncpg pool (?좏깮)
    """

    def __init__(self, redis_client: Any, timescale_pool: Any = None, claim_ttl_ms: int = CLAIM_TTL_MS):
        self.redis = RedisCompat(redis_client)
        self._raw_redis = redis_client
        self.timescale_pool = timescale_pool
        self._claim_ttl_ms = claim_ttl_ms
        self._running = False

    async def _pop_job(self) -> Optional[Dict[str, Any]]:
        """
        ZSET?먯꽌 理쒓퀬 ?곗꽑 job??爰쇰깂(zpopmax). 諛섑솚: parsed job dict ?먮뒗 None
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
            logger.exception("[GapConsumer] pop_job ?ㅽ뙣")
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
        ?ы걧: attempts 利앷?, score ?ш퀎??吏?섏쟻 backoff 湲곕컲)
        - attempts媛 MAX_ATTEMPTS 珥덇낵?섎㈃ DLQ濡??대룞
        """
        job["attempts"] = attempts
        raw = orjson.dumps(job).decode("utf-8")
        if attempts > MAX_ATTEMPTS:
            logger.warning("[GapConsumer] 理쒕? ?ъ떆??珥덇낵, DLQ濡??대룞 job_id=%s attempts=%d", job.get("job_id"), attempts)
            await self.redis.rpush(DLQ_LIST, raw)
            return
        # 吏?섏쟻 吏??湲곕컲 ?곗꽑?쒖쐞(媛꾨떒): 湲곗〈 score瑜?以꾩뿬???쒖쐞瑜???땄
        base_score = job.get("_score", 1.0)
        delay_seconds = REQUEUE_BASE_DELAY * (2 ** (attempts - 1))
        new_score = base_score / (1 + attempts)  # 媛꾨떒 ?ㅼ퐫??媛먯냼
        # ?ㅼ젣 ?댁쁺?먯꽌???ъ떆???덉빟 ?쒖뒪?쒖쓣 ?ъ슜?섎뒗 寃껋씠 ??醫뗭쓬
        await self.redis.zadd(ZSET_KEY, {raw: new_score})
        logger.info("[GapConsumer] ?ы걧: job_id=%s attempts=%d new_score=%.4f delay=%ds", job.get("job_id"), attempts, new_score, delay_seconds)

    async def _process_job(self, job: Dict[str, Any], owner_id: str):
        """
        ?④굔 job 泥섎━ ?뚮줈??
        - 硫깅벑??寃??
        - claim ?쒕룄
        - perform_backfill ?몄텧
        - ?깃났: mark_processed
        - ?ㅽ뙣: ?ы걧(?먮뒗 DLQ)
        """
        job_id = job.get("job_id") or hashlib.sha256(orjson.dumps(job)).hexdigest()
        # ?대? 泥섎━?섏뿀?붿? ?뺤씤
        if await self._is_processed(job_id):
            logger.info("[GapConsumer] ?대? 泥섎━??job 嫄대꼫?: %s", job_id)
            return

        # claim ?쒕룄
        claimed = await self._claim_job(job_id, owner_id)
        if not claimed:
            logger.debug("[GapConsumer] claim ?ㅽ뙣 (?ㅻⅨ ?뚯빱 泥섎━ 以?: %s", job_id)
            return

        # attempts 移댁슫??愿由?
        attempts = int(job.get("attempts", 0))
        try:
            ok = await perform_backfill(job, self.timescale_pool)
            if ok:
                await self._mark_processed(job_id)
                logger.info("[GapConsumer] 泥섎━ ?깃났: %s", job_id)
            else:
                attempts += 1
                await self._requeue_job(job, attempts)
                logger.warning("[GapConsumer] 泥섎━ ?ㅽ뙣 - ?ы걧: %s attempts=%d", job_id, attempts)
        except Exception:
            attempts += 1
            await self._requeue_job(job, attempts)
            logger.exception("[GapConsumer] 泥섎━ ?덉쇅 - ?ы걧: %s attempts=%d", job_id, attempts)

    async def run_once(self, owner_id: Optional[str] = None) -> int:
        """
        ?⑤컻??泥섎━: ?섎굹??job??泥섎━(?먮뒗 ?쒕룄)?섍퀬 醫낅즺.
        諛섑솚: 泥섎━(?쒕룄)??job ??0/1)
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        job = await self._pop_job()
        if not job:
            logger.debug("[GapConsumer] 泥섎━??job ?놁쓬")
            return 0
        await self._process_job(job, owner)
        return 1

    async def run(self, poll_interval: float = 1.0, owner_id: Optional[str] = None):
        """
        ?곕が 紐⑤뱶: 怨꾩냽?댁꽌 ZSET?먯꽌 job??爰쇰궡 泥섎━.
        ?덉쟾 醫낅즺???몃??먯꽌 loop??SIGINT/SIGTERM???꾨떖?댁빞 ??
        """
        owner = owner_id or f"consumer:{os.getpid()}:{int(time.time())}"
        self._running = True
        logger.info("[GapConsumer] ?곕が ?쒖옉 owner=%s", owner)
        try:
            while self._running:
                try:
                    job = await self._pop_job()
                    if job:
                        await self._process_job(job, owner)
                        # 利됱떆 ?ㅼ쓬 job 泥섎━ (占쏙옙? ?ъ떆???湲??놁쓬)
                        await asyncio.sleep(0.01)
                    else:
                        # ?대쭅 諛깆삤??
                        await asyncio.sleep(poll_interval)
                except Exception:
                    logger.exception("[GapConsumer] 猷⑦봽 以??덉쇅 諛쒖깮")
                    await asyncio.sleep(1.0)
        finally:
            self._running = False
            logger.info("[GapConsumer] ?곕が 醫낅즺")

    def stop(self):
        self._running = False


# ---------------------------
# CLI / ?곗쿂
# ---------------------------
async def create_redis_client(url: str):
    """
    redis-clients 珥덇린?? redis.asyncio 瑜??곗꽑 ?쒕룄, ?놁쑝硫?aioredis瑜??쒕룄.
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
            logger.exception("[GapConsumer] Redis ?대씪?댁뼵???앹꽦 ?ㅽ뙣")
            raise


async def create_timescale_pool(dsn: Optional[str]):
    """
    asyncpg pool ?앹꽦(?좏깮). dsn ?놁쑝硫?None 諛섑솚.
    """
    if not dsn:
        return None
    try:
        import asyncpg  # type: ignore
        pool = await asyncpg.create_pool(dsn)
        return pool
    except Exception:
        logger.exception("[GapConsumer] timescale pool ?앹꽦 ?ㅽ뙣")
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
        # ?덉쟾 醫낅즺
        try:
            await _safe_close(redis_client)
        except Exception:
            pass
        if timescale_pool:
            await timescale_pool.close()
    else:
        # ?곕が 紐⑤뱶: ?쒓렇??泥섎━
        loop = asyncio.get_running_loop()
        stop_evt = asyncio.Event()

        def _on_stop():
            logger.info("[GapConsumer] 醫낅즺 ?좏샇 ?섏떊")
            consumer.stop()
            stop_evt.set()

        try:
            loop.add_signal_handler(signal.SIGINT, _on_stop)   # type: ignore[name-defined]
            loop.add_signal_handler(signal.SIGTERM, _on_stop)  # type: ignore[name-defined]
        except Exception:
            logger.debug("[GapConsumer] ?쒓렇???몃뱾???깅줉 遺덇?(?섍꼍?쒗븳)")

        # 諛깃렇?쇱슫???ㅽ뻾
        task = asyncio.create_task(consumer.run(poll_interval=args.interval))
        await stop_evt.wait()
        # ?뺣━
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
    Redis/DB client ?덉쟾 醫낅즺: aclose -> close ?쒖쑝濡??쒕룄
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
        logger.debug("[GapConsumer] ?덉쟾 醫낅즺 以??덉쇅", exc_info=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gap consumer worker")
    parser.add_argument("--once", action="store_true", help="??踰덈쭔 泥섎━?섍퀬 醫낅즺")
    parser.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    parser.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("GAP_CONSUMER_INTERVAL", "1.0")))
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        logger.info("[GapConsumer] ?ъ슜???명꽣?쏀듃濡?醫낅즺")
    except Exception:
        logger.exception("[GapConsumer] ?덉쇅濡?醫낅즺")
        sys.exit(1)


if __name__ == "__main__":
    main()
