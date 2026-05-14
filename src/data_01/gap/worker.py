# -*- coding: utf-8 -*-
"""
Gap Backfill Worker

紐⑹쟻:
- Redis ZSET(gap_fill_queue)?먯꽌 gap_event瑜?pop(zpopmax)?섍굅??peek(zrange)?섏뿬
  ?묒뾽???대젅??SETNX)?섍퀬 泥섎━?⑸땲??
- 泥섎━ 諛⑸쾿: gap_event.start ~ gap_event.end 踰붿쐞?먯꽌 ?낅퉬??REST API濡?1遺꾨큺 ?곗씠??議고쉶 ??
  candles ?뚯씠釉붿뿉 idempotent(ON CONFLICT DO NOTHING)?섍쾶 ?쎌엯?⑸땲??
- ?ㅽ뙣/?덉쇅 ??DLQ???곸옱?섍퀬 ?ъ떆??移댁슫??increment)瑜?愿由ы빀?덈떎.
- ?뚯빱 ?곹깭瑜?Redis????ν븯??UI?먯꽌 紐⑤땲?곕쭅 媛?ν빀?덈떎.

?ъ슜踰?鍮꾨룞湲?CLI):
    python -m src.data_01.gap.worker --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "postgresql://postgres:postgres@localhost:58529/upbit_trader"

援ъ꽦(?섍꼍蹂???먮뒗 ?몄옄):
- --redis-url
- --timescale-dsn
- --zset-key (湲곕낯 gap_fill_queue)
- --dlq-key (湲곕낯 gap_dlq)
- --claim-ttl (珥? 湲곕낯 300)
- --max-candles-per-page (?섏씠吏??理쒕? 罹붾뱾 ?? 湲곕낯 200)
- --max-pages (理쒕? ?섏씠吏 ?? 湲곕낯 100: ??3.3??

紐⑤뱺 二쇱꽍? ?쒓??낅땲??
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    import orjson  # type: ignore
    def _json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode("utf-8")
    def _json_loads(s: Any) -> Any:
        return orjson.loads(s)
except ImportError:
    def _json_dumps(obj: Any) -> str:  # type: ignore[misc]
        return json.dumps(obj, ensure_ascii=False, default=str)
    def _json_loads(s: Any) -> Any:  # type: ignore[misc]
        if isinstance(s, (bytes, bytearray)):
            s = s.decode("utf-8")
        return json.loads(s)

logger = logging.getLogger("gap.worker")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# 湲곕낯 ??
DEFAULT_ZSET_KEY = os.environ.get("GAP_ZSET_KEY", "gap_fill_queue")
DEFAULT_DLQ_KEY = os.environ.get("GAP_DLQ_KEY", "gap_dlq")
DEFAULT_CLAIM_TTL = int(os.environ.get("GAP_CLAIM_TTL", "300"))  # seconds
DEFAULT_MAX_CANDLES_PER_PAGE = int(os.environ.get("GAP_MAX_CANDLES_PER_PAGE", "200"))
DEFAULT_MAX_PAGES = int(os.environ.get("GAP_MAX_PAGES", "100"))  # 理쒕? ?섏씠吏(?덉쟾 李⑤떒)

# ?낅퉬??REST API ?붾뱶?ъ씤??
UPBIT_CANDLE_API_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"

# ?낅퉬??API ?띾룄 ?쒗븳 以??(理쒕? 10req/s ??0.12珥?媛꾧꺽)
UPBIT_API_DELAY_SECONDS = 0.12

# Redis ?곹깭 ??
REDIS_KEY_WORKER_STATUS = "gap:worker:status"
REDIS_KEY_WORKER_GRACE_PERIOD = "gap:worker:grace_period"
REDIS_KEY_WORKER_COUNT = "gap:worker:count"
WORKER_GRACE_PERIOD_SECONDS = 30


def _get_default_redis_url() -> str:
    """config.yaml 湲곕컲 Redis URL 諛섑솚 (fallback: ?ы듃 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_gw", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


# ---------------------------
# ?대씪?댁뼵???앹꽦 ?ы띁
# ---------------------------
async def _create_redis(redis_url: str) -> Optional[Any]:
    """鍮꾨룞湲?Redis ?대씪?댁뼵???앹꽦."""
    try:
        mod = importlib.import_module("redis.asyncio")
        Redis = getattr(mod, "Redis")
        client = Redis.from_url(redis_url, decode_responses=False)
        await client.ping()
        logger.debug("[worker] redis.asyncio ?곌껐 ?깃났")
        return client
    except Exception:
        try:
            mod = importlib.import_module("aioredis")
            client = getattr(mod, "from_url")(redis_url)
            await client.ping()
            logger.debug("[worker] aioredis ?곌껐 ?깃났")
            return client
        except Exception:
            logger.exception("[worker] Redis ?곌껐 ?ㅽ뙣")
            return None


async def _create_pool(timescale_dsn: Optional[str]) -> Optional[Any]:
    """asyncpg ?곌껐 ? ?앹꽦."""
    if not timescale_dsn:
        logger.warning("[worker] timescale_dsn 誘몄???- DB ?곕룞 鍮꾪솢??)
        return None
    try:
        mod = importlib.import_module("asyncpg")
        pool = await mod.create_pool(timescale_dsn)
        logger.debug("[worker] asyncpg pool ?앹꽦 ?깃났")
        return pool
    except Exception:
        logger.exception("[worker] asyncpg pool ?앹꽦 ?ㅽ뙣")
        return None


# ---------------------------
# ?낅퉬??REST API ?몄텧 ?ы띁
# ---------------------------
async def _fetch_upbit_candles(
    symbol: str,
    to: str,
    unit: int = 1,
    count: int = 200,
) -> List[Dict[str, Any]]:
    """?낅퉬??REST API?먯꽌 遺꾨큺 罹붾뱾 ?곗씠?곕? 議고쉶?⑸땲??

    Args:
        symbol:  ?낅퉬??留덉폆 肄붾뱶 (?? KRW-BTC)
        to:      議고쉶 湲곗? ?쒓컖 (ISO 8601, ?대떦 ?쒓컖 ?댁쟾 ?곗씠??諛섑솚)
        unit:    遺꾨큺 ?⑥쐞 (1, 3, 5, 15, 30, 60, 240)
        count:   議고쉶 嫄댁닔 (理쒕? 200)

    Returns:
        ?낅퉬??API ?묐떟 ?뺤뀛?덈━ 紐⑸줉 (理쒖떊 ??怨쇨굅 ?쒖꽌)
    """
    try:
        import aiohttp  # type: ignore
    except ImportError:
        logger.error("[worker] aiohttp 誘몄꽕移???pip install aiohttp")
        return []

    url = UPBIT_CANDLE_API_URL.format(unit=unit)
    params = {"market": symbol, "count": count, "to": to}
    headers = {"Accept": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("[worker] ?낅퉬??API ?묐떟 ?댁긽: status=%d symbol=%s", resp.status, symbol)
                    return []
                data = await resp.json(content_type=None)
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("[worker] ?낅퉬??API ?몄텧 ?ㅽ뙣: symbol=%s err=%s", symbol, exc)
        return []


# ---------------------------
# DB ?쎌엯 ?ы띁 (idempotent)
# ---------------------------
INSERT_CANDLE_SQL = """
INSERT INTO candles
    (time, symbol, timeframe, exchange, open, high, low, close, volume, quote_volume, trade_count)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (time, symbol, timeframe) DO NOTHING;
"""


async def _insert_candles_batch(
    pool: Any,
    rows: List[tuple],
) -> int:
    """candles ?뚯씠釉붿뿉 諛곗튂 ?쎌엯(idempotent).

    Args:
        pool: asyncpg ?곌껐 ?
        rows: (time, symbol, timeframe, exchange, open, high, low, close, volume, quote_volume, trade_count) ?쒗뵆 紐⑸줉

    Returns:
        ?쎌엯??????(異붿젙)
    """
    if pool is None or not rows:
        return 0
    try:
        async with pool.acquire() as conn:
            await conn.executemany(INSERT_CANDLE_SQL, rows)
        return len(rows)
    except Exception as exc:
        logger.exception("[worker] candles 諛곗튂 ?쎌엯 ?ㅽ뙣: %s", exc)
        return 0


def _parse_timeframe_unit(timeframe: str) -> int:
    """??꾪봽?덉엫 臾몄옄?댁쓣 遺??⑥쐞濡?蹂?섑빀?덈떎."""
    tf_map = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15,
        "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
    }
    return tf_map.get(timeframe, 1)


# ---------------------------
# Gap 泥섎━ 濡쒖쭅(?대젅???ㅽ뻾/DLQ)
# ---------------------------
class GapWorker:
    """Gap 諛깊븘 ?뚯빱 ???낅퉬??REST API ?ㅼ젣 ?몄텧 踰꾩쟾."""

    def __init__(
        self,
        redis_url: str,
        timescale_dsn: Optional[str],
        zset_key: str = DEFAULT_ZSET_KEY,
        dlq_key: str = DEFAULT_DLQ_KEY,
        claim_ttl: int = DEFAULT_CLAIM_TTL,
        max_candles_per_page: int = DEFAULT_MAX_CANDLES_PER_PAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self.redis_url = redis_url
        self.timescale_dsn = timescale_dsn
        self.zset_key = zset_key
        self.dlq_key = dlq_key
        self.claim_ttl = claim_ttl
        self.max_candles_per_page = min(max_candles_per_page, 200)
        self.max_pages = max_pages

        self._redis: Optional[Any] = None
        self._pool: Optional[Any] = None
        self._processed_count = 0

    async def start(self) -> None:
        """Redis 諛?DB ?곌껐??珥덇린?뷀빀?덈떎."""
        self._redis = await _create_redis(self.redis_url)
        self._pool = await _create_pool(self.timescale_dsn)
        await self._save_worker_status(running=True)

    async def stop(self) -> None:
        """?뚯빱瑜?醫낅즺?섍퀬 由ъ냼?ㅻ? ?댁젣?⑸땲??"""
        await self._save_worker_status(running=False)
        try:
            if self._redis is not None:
                if hasattr(self._redis, "aclose"):
                    res = self._redis.aclose()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self._redis, "close"):
                    res = self._redis.close()
                    if asyncio.iscoroutine(res):
                        await res
        except Exception:
            logger.debug("[worker] redis 醫낅즺 以??덉쇅", exc_info=True)
        try:
            if self._pool is not None:
                await self._pool.close()
        except Exception:
            logger.debug("[worker] pool 醫낅즺 以??덉쇅", exc_info=True)

    async def _save_worker_status(self, running: bool) -> None:
        """?뚯빱 ?곹깭瑜?Redis????ν빀?덈떎 (UI 紐⑤땲?곕쭅??.

        ?????
            gap:worker:status       ??{"running": bool, "processed": int, "last_processed": ISO str}
            gap:worker:grace_period ???좎삁 湲곌컙(珥?
            gap:worker:count        ???쒖꽦 ?뚯빱 ??
        """
        if self._redis is None:
            return
        try:
            status_obj = {
                "running": running,
                "processed": self._processed_count,
                "last_processed": datetime.now(tz=timezone.utc).isoformat(),
            }
            await self._redis.set(REDIS_KEY_WORKER_STATUS, _json_dumps(status_obj), ex=180)
            await self._redis.set(REDIS_KEY_WORKER_GRACE_PERIOD, str(WORKER_GRACE_PERIOD_SECONDS), ex=180)
            await self._redis.set(REDIS_KEY_WORKER_COUNT, "1" if running else "0", ex=180)
        except Exception as exc:
            logger.debug("[worker] ?곹깭 ????ㅽ뙣(臾댁떆): %s", exc)

    async def _zpopmax_once(self) -> List[Any]:
        """ZPOPMAX濡?媛???곗꽑?쒖쐞 ?믪? ??ぉ 1媛쒕? 爰쇰깄?덈떎."""
        if self._redis is None:
            return []
        try:
            if hasattr(self._redis, "zpopmax"):
                res = await self._redis.zpopmax(self.zset_key, count=1)
                if not res:
                    return []
                return res
            else:
                # fallback: zrange with scores then zrem
                items = await self._redis.zrange(self.zset_key, -1, -1, withscores=True)
                if not items:
                    return []
                member, score = items[-1]
                await self._redis.zrem(self.zset_key, member)
                return [(member, score)]
        except Exception:
            logger.exception("[worker] zpopmax ?ㅽ뙣")
            return []

    async def _claim_job(self, job_id: str) -> bool:
        """SETNX濡??묒뾽???대젅?꾪빀?덈떎. ?대? ?대젅?꾨맂 寃쎌슦 False 諛섑솚."""
        if self._redis is None:
            return False
        key = f"gap:claim:{job_id}"
        try:
            res = await self._redis.set(key, b"1", nx=True, ex=self.claim_ttl)
            return bool(res)
        except Exception:
            logger.exception("[worker] claim ?ㅽ뙣")
            return False

    async def _release_claim(self, job_id: str) -> None:
        """?대젅???ㅻ? ??젣?⑸땲??"""
        if self._redis is None:
            return
        key = f"gap:claim:{job_id}"
        try:
            await self._redis.delete(key)
        except Exception:
            logger.debug("[worker] claim ??젣 ?ㅽ뙣", exc_info=True)

    async def _move_to_dlq(self, gap_event: Dict[str, Any], reason: str) -> None:
        """?ㅽ뙣 ??ぉ??DLQ??push?⑸땲??"""
        if self._redis is None:
            return
        try:
            gap_event["attempts"] = int(gap_event.get("attempts", 0)) + 1
            gap_event["last_error"] = reason
            member = _json_dumps(gap_event)
            await self._redis.lpush(self.dlq_key, member)
            logger.warning("[worker] ?묒뾽 DLQ ?대룞: job_id=%s reason=%s", gap_event.get("job_id"), reason)
        except Exception:
            logger.exception("[worker] DLQ ?곸옱 ?ㅽ뙣")

    async def _process_gap_event(self, gap_event: Dict[str, Any]) -> bool:
        """?ㅼ젣 ?낅퉬??REST API瑜??몄텧?섏뿬 Gap 援ш컙??罹붾뱾 ?곗씠?곕? 諛깊븘?⑸땲??

        ??갑???섏씠吏?ㅼ씠??
            end ??start 諛⑺뼢?쇰줈 UPBIT_CANDLE_API_URL ?몄텧,
            candles ?뚯씠釉붿뿉 ON CONFLICT DO NOTHING?쇰줈 ?쎌엯.

        Args:
            gap_event: Gap ?대깽???뺤뀛?덈━ (job_id, symbol, timeframe, start, end ?ы븿)

        Returns:
            ?깃났 ?щ?
        """
        try:
            symbol: str = gap_event["symbol"]
            timeframe: str = gap_event.get("timeframe", "1m")
            start_str: str = gap_event.get("start", "")
            end_str: str = gap_event.get("end", "")
        except KeyError as exc:
            logger.error("[worker] gap_event ?꾨뱶 ?꾨씫: %s", exc)
            return False

        # ?쒓컙 ?뚯떛
        try:
            start_dt = datetime.fromisoformat(start_str) if start_str else None
            end_dt = datetime.fromisoformat(end_str) if end_str else datetime.now(tz=timezone.utc)
        except Exception as exc:
            logger.error("[worker] ?쒓컖 ?뚯떛 ?ㅽ뙣: %s", exc)
            return False

        unit = _parse_timeframe_unit(timeframe)
        inserted_total = 0
        page_count = 0
        cursor_to = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # ??갑???섏씠吏?ㅼ씠??(end ??start)
        while page_count < self.max_pages:
            candles = await _fetch_upbit_candles(
                symbol=symbol,
                to=cursor_to,
                unit=unit,
                count=self.max_candles_per_page,
            )
            if not candles:
                logger.info("[worker] ?낅퉬??API ?묐떟 ?놁쓬 ??諛깊븘 醫낅즺: symbol=%s", symbol)
                break

            rows: List[tuple] = []
            oldest_ts: Optional[datetime] = None

            for c in candles:
                try:
                    # ?낅퉬??API ?묐떟 ?꾨뱶 留ㅽ븨
                    ts_str = c.get("candle_date_time_utc") or c.get("timestamp", "")
                    if not ts_str:
                        continue
                    # ISO 8601 ?뚯떛 (Python 3.7+??'Z' 誘몄?????rstrip 泥섎━)
                    if isinstance(ts_str, str):
                        ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    else:
                        ts = datetime.fromtimestamp(ts_str / 1000, tz=timezone.utc)

                    rows.append((
                        ts,
                        symbol,
                        timeframe,
                        "upbit",
                        float(c.get("opening_price", 0)),
                        float(c.get("high_price", 0)),
                        float(c.get("low_price", 0)),
                        float(c.get("trade_price", 0)),
                        float(c.get("candle_acc_trade_volume", 0)),
                        float(c.get("candle_acc_trade_price", 0)),
                        0,  # Upbit 遺꾨큺 API??trade_count 誘몄젣怨?
                    ))

                    if oldest_ts is None or ts < oldest_ts:
                        oldest_ts = ts
                except Exception as row_exc:
                    logger.debug("[worker] ???뚯떛 ?ㅻ쪟(臾댁떆): %s", row_exc)

            if rows:
                n = await _insert_candles_batch(self._pool, rows)
                inserted_total += n
                logger.debug("[worker] ?섏씠吏 %d: %d???쎌엯 (symbol=%s)", page_count + 1, n, symbol)

            page_count += 1

            # start_dt???꾨떖?덉쑝硫?醫낅즺
            if start_dt is not None and oldest_ts is not None and oldest_ts <= start_dt:
                break

            # ?ㅼ쓬 ?섏씠吏: 媛???ㅻ옒??罹붾뱾 ?쒓컖??湲곗??쇰줈 ?ъ“??
            if oldest_ts is not None:
                cursor_to = oldest_ts.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                break

            # API ?띾룄 ?쒗븳 以??(Upbit: 理쒕? 10req/s ??UPBIT_API_DELAY_SECONDS 媛꾧꺽)
            await asyncio.sleep(UPBIT_API_DELAY_SECONDS)

        logger.info(
            "[worker] 諛깊븘 ?꾨즺: job_id=%s symbol=%s inserted=%d pages=%d",
            gap_event.get("job_id"), symbol, inserted_total, page_count,
        )
        return True

    async def claim_and_process_once(self) -> bool:
        """?먯뿉?????묒뾽??爰쇰궡 ?대젅?꾪븯怨?泥섎━?⑸땲??

        Returns:
            ?묒뾽??泥섎━?덉쑝硫?True, ?먭? 鍮꾩뿀嫄곕굹 ?ㅽ궢?덉쑝硫?False
        """
        items = await self._zpopmax_once()
        if not items:
            logger.debug("[worker] 泥섎━??gap ?놁쓬")
            return False

        member, score = items[0]
        try:
            if isinstance(member, (bytes, bytearray)):
                member = member.decode("utf-8")
            gap_event = _json_loads(member)
        except Exception:
            logger.exception("[worker] gap_event ?뚯떛 ?ㅽ뙣 - ?ㅽ궢")
            return False

        job_id = gap_event.get("job_id")
        if not job_id:
            logger.warning("[worker] job_id ?놁쓬 - ?ㅽ궢 (isolator.py??_enqueue_gap() ?뺤씤 ?꾩슂)")
            return False

        # ?대젅??
        claimed = await self._claim_job(job_id)
        if not claimed:
            logger.info("[worker] ?대? ?대젅?꾨맂 ?묒뾽, ?ㅽ궢: job_id=%s", job_id)
            return False

        try:
            ok = await self._process_gap_event(gap_event)
            if ok:
                self._processed_count += 1
                await self._save_worker_status(running=True)
                logger.info("[worker] job 泥섎━ ?깃났: job_id=%s", job_id)
            else:
                await self._move_to_dlq(gap_event, "process_failed")
        except Exception as exc:
            logger.exception("[worker] job 泥섎━ 以??덉쇅")
            await self._move_to_dlq(gap_event, f"exception:{exc}")
        finally:
            await self._release_claim(job_id)
        return True

    async def run_once(self) -> None:
        """?⑥씪 ?묒뾽??泥섎━?섍퀬 醫낅즺?⑸땲??"""
        await self.start()
        try:
            await self.claim_and_process_once()
        finally:
            await self.stop()

    async def run_loop(self, poll_interval: float = 5.0) -> None:
        """?먭? 鍮??뚭퉴吏 ?곗냽 泥섎━?⑸땲??"""
        await self.start()
        last_heartbeat = time.monotonic()
        try:
            while True:
                try:
                    has = await self.claim_and_process_once()
                    if not has:
                        await asyncio.sleep(poll_interval)
                    # 60珥덈쭏??heartbeat 媛깆떊 (idle ?곹깭?먯꽌???곹깭 ??留뚮즺 諛⑹?)
                    now = time.monotonic()
                    if now - last_heartbeat >= 60.0:
                        await self._save_worker_status(running=True)
                        last_heartbeat = now
                except Exception:
                    logger.exception("[worker] 猷⑦봽 泥섎━ 以??덉쇅")
                    await asyncio.sleep(poll_interval)
        finally:
            await self.stop()


# ---------------------------
# PyQt5 ?곕룞??諛깃렇?쇱슫???ㅻ젅??
# ---------------------------
class GapWorkerThread(threading.Thread):
    """GapWorker瑜?蹂꾨룄 ?ㅻ젅?쒖뿉???ㅽ뻾?섎뒗 ?섑띁 (PyQt5 ???곕룞??.

    ?ъ슜 ??
        thread = GapWorkerThread(redis_url=..., timescale_dsn=...)
        thread.start()
        # ??醫낅즺 ??
        thread.stop()
        thread.join(timeout=10)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        timescale_dsn: Optional[str] = None,
        poll_interval: float = 5.0,
        **worker_kwargs: Any,
    ) -> None:
        super().__init__(name="GapWorkerThread", daemon=True)
        self._redis_url = redis_url or _get_default_redis_url()
        self._timescale_dsn = timescale_dsn or os.environ.get("TIMESCALE_DSN", "")
        self._poll_interval = poll_interval
        self._worker_kwargs = worker_kwargs
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        """?ㅻ젅??吏꾩엯???????대깽??猷⑦봽?먯꽌 GapWorker.run_loop() ?ㅽ뻾."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        worker = GapWorker(
            redis_url=self._redis_url,
            timescale_dsn=self._timescale_dsn,
            **self._worker_kwargs,
        )
        try:
            self._loop.run_until_complete(worker.run_loop(self._poll_interval))
        except Exception:
            logger.exception("[GapWorkerThread] 猷⑦봽 醫낅즺")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def stop(self) -> None:
        """?ㅻ젅??醫낅즺瑜??붿껌?⑸땲??"""
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)


# ---------------------------
# CLI
# ---------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gap Backfill Worker (?낅퉬??REST API ?ㅼ젣 ?몄텧)")
    p.add_argument("--once", action="store_true", help="??踰덈쭔 ?ㅽ뻾")
    p.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    p.add_argument("--zset-key", type=str, default=DEFAULT_ZSET_KEY)
    p.add_argument("--dlq-key", type=str, default=DEFAULT_DLQ_KEY)
    p.add_argument("--claim-ttl", type=int, default=DEFAULT_CLAIM_TTL)
    p.add_argument("--max-candles-per-page", type=int, default=DEFAULT_MAX_CANDLES_PER_PAGE)
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    worker = GapWorker(
        redis_url=args.redis_url,
        timescale_dsn=args.timescale_dsn,
        zset_key=args.zset_key,
        dlq_key=args.dlq_key,
        claim_ttl=args.claim_ttl,
        max_candles_per_page=args.max_candles_per_page,
        max_pages=args.max_pages,
    )
    if args.once:
        asyncio.run(worker.run_once())
    else:
        try:
            asyncio.run(worker.run_loop())
        except KeyboardInterrupt:
            logger.info("[worker] ?ъ슜??以묐떒?쇰줈 醫낅즺")


if __name__ == "__main__":
    main()

