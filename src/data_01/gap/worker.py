# -*- coding: utf-8 -*-
"""
Gap Backfill Worker

ëª©ì :
- Redis ZSET(gap_fill_queue)?ì„œ gap_eventë¥?pop(zpopmax)?˜ê±°??peek(zrange)?˜ì—¬
  ?‘ì—…???´ë ˆ??SETNX)?˜ê³  ì²˜ë¦¬?©ë‹ˆ??
- ì²˜ë¦¬ ë°©ë²•: gap_event.start ~ gap_event.end ë²”ìœ„?ì„œ ?…ë¹„??REST APIë¡?1ë¶„ë´‰ ?°ì´??ì¡°íšŒ ??
  candles ?Œì´ë¸”ì— idempotent(ON CONFLICT DO NOTHING)?˜ê²Œ ?½ì…?©ë‹ˆ??
- ?¤íŒ¨/?ˆì™¸ ??DLQ???ì¬?˜ê³  ?¬ì‹œ??ì¹´ìš´??increment)ë¥?ê´€ë¦¬í•©?ˆë‹¤.
- ?Œì»¤ ?íƒœë¥?Redis???€?¥í•˜??UI?ì„œ ëª¨ë‹ˆ?°ë§ ê°€?¥í•©?ˆë‹¤.

?¬ìš©ë²?ë¹„ë™ê¸?CLI):
    python -m src.data_01.gap.worker --once --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "postgresql://postgres:postgres@localhost:58529/upbit_trader"

êµ¬ì„±(?˜ê²½ë³€???ëŠ” ?¸ì):
- --redis-url
- --timescale-dsn
- --zset-key (ê¸°ë³¸ gap_fill_queue)
- --dlq-key (ê¸°ë³¸ gap_dlq)
- --claim-ttl (ì´? ê¸°ë³¸ 300)
- --max-candles-per-page (?˜ì´ì§€??ìµœë? ìº”ë“¤ ?? ê¸°ë³¸ 200)
- --max-pages (ìµœë? ?˜ì´ì§€ ?? ê¸°ë³¸ 100: ??3.3??

ëª¨ë“  ì£¼ì„?€ ?œê??…ë‹ˆ??
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

# ê¸°ë³¸ ??
DEFAULT_ZSET_KEY = os.environ.get("GAP_ZSET_KEY", "gap_fill_queue")
DEFAULT_DLQ_KEY = os.environ.get("GAP_DLQ_KEY", "gap_dlq")
DEFAULT_CLAIM_TTL = int(os.environ.get("GAP_CLAIM_TTL", "300"))  # seconds
DEFAULT_MAX_CANDLES_PER_PAGE = int(os.environ.get("GAP_MAX_CANDLES_PER_PAGE", "200"))
DEFAULT_MAX_PAGES = int(os.environ.get("GAP_MAX_PAGES", "100"))  # ìµœë? ?˜ì´ì§€(?ˆì „ ì°¨ë‹¨)

# ?…ë¹„??REST API ?”ë“œ?¬ì¸??
UPBIT_CANDLE_API_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"

# ?…ë¹„??API ?ë„ ?œí•œ ì¤€??(ìµœë? 10req/s ??0.12ì´?ê°„ê²©)
UPBIT_API_DELAY_SECONDS = 0.12

# Redis ?íƒœ ??
REDIS_KEY_WORKER_STATUS = "gap:worker:status"
REDIS_KEY_WORKER_GRACE_PERIOD = "gap:worker:grace_period"
REDIS_KEY_WORKER_COUNT = "gap:worker:count"
WORKER_GRACE_PERIOD_SECONDS = 30


def _get_default_redis_url() -> str:
    """config.yaml ê¸°ë°˜ Redis URL ë°˜í™˜ (fallback: ?¬íŠ¸ 58530, password=dummy)"""
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
# ?´ë¼?´ì–¸???ì„± ?¬í¼
# ---------------------------
async def _create_redis(redis_url: str) -> Optional[Any]:
    """ë¹„ë™ê¸?Redis ?´ë¼?´ì–¸???ì„±."""
    try:
        mod = importlib.import_module("redis.asyncio")
        Redis = getattr(mod, "Redis")
        client = Redis.from_url(redis_url, decode_responses=False)
        await client.ping()
        logger.debug("[worker] redis.asyncio ?°ê²° ?±ê³µ")
        return client
    except Exception:
        try:
            mod = importlib.import_module("aioredis")
            client = getattr(mod, "from_url")(redis_url)
            await client.ping()
            logger.debug("[worker] aioredis ?°ê²° ?±ê³µ")
            return client
        except Exception:
            logger.exception("[worker] Redis ?°ê²° ?¤íŒ¨")
            return None


async def _create_pool(timescale_dsn: Optional[str]) -> Optional[Any]:
    """asyncpg ?°ê²° ?€ ?ì„±."""
    if not timescale_dsn:
        logger.warning("[worker] timescale_dsn ë¯¸ì???- DB ?°ë™ ë¹„í™œ??)
        return None
    try:
        mod = importlib.import_module("asyncpg")
        pool = await mod.create_pool(timescale_dsn)
        logger.debug("[worker] asyncpg pool ?ì„± ?±ê³µ")
        return pool
    except Exception:
        logger.exception("[worker] asyncpg pool ?ì„± ?¤íŒ¨")
        return None


# ---------------------------
# ?…ë¹„??REST API ?¸ì¶œ ?¬í¼
# ---------------------------
async def _fetch_upbit_candles(
    symbol: str,
    to: str,
    unit: int = 1,
    count: int = 200,
) -> List[Dict[str, Any]]:
    """?…ë¹„??REST API?ì„œ ë¶„ë´‰ ìº”ë“¤ ?°ì´?°ë? ì¡°íšŒ?©ë‹ˆ??

    Args:
        symbol:  ?…ë¹„??ë§ˆì¼“ ì½”ë“œ (?? KRW-BTC)
        to:      ì¡°íšŒ ê¸°ì? ?œê° (ISO 8601, ?´ë‹¹ ?œê° ?´ì „ ?°ì´??ë°˜í™˜)
        unit:    ë¶„ë´‰ ?¨ìœ„ (1, 3, 5, 15, 30, 60, 240)
        count:   ì¡°íšŒ ê±´ìˆ˜ (ìµœë? 200)

    Returns:
        ?…ë¹„??API ?‘ë‹µ ?•ì…”?ˆë¦¬ ëª©ë¡ (ìµœì‹  ??ê³¼ê±° ?œì„œ)
    """
    try:
        import aiohttp  # type: ignore
    except ImportError:
        logger.error("[worker] aiohttp ë¯¸ì„¤ì¹???pip install aiohttp")
        return []

    url = UPBIT_CANDLE_API_URL.format(unit=unit)
    params = {"market": symbol, "count": count, "to": to}
    headers = {"Accept": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("[worker] ?…ë¹„??API ?‘ë‹µ ?´ìƒ: status=%d symbol=%s", resp.status, symbol)
                    return []
                data = await resp.json(content_type=None)
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("[worker] ?…ë¹„??API ?¸ì¶œ ?¤íŒ¨: symbol=%s err=%s", symbol, exc)
        return []


# ---------------------------
# DB ?½ì… ?¬í¼ (idempotent)
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
    """candles ?Œì´ë¸”ì— ë°°ì¹˜ ?½ì…(idempotent).

    Args:
        pool: asyncpg ?°ê²° ?€
        rows: (time, symbol, timeframe, exchange, open, high, low, close, volume, quote_volume, trade_count) ?œí”Œ ëª©ë¡

    Returns:
        ?½ì…??????(ì¶”ì •)
    """
    if pool is None or not rows:
        return 0
    try:
        async with pool.acquire() as conn:
            await conn.executemany(INSERT_CANDLE_SQL, rows)
        return len(rows)
    except Exception as exc:
        logger.exception("[worker] candles ë°°ì¹˜ ?½ì… ?¤íŒ¨: %s", exc)
        return 0


def _parse_timeframe_unit(timeframe: str) -> int:
    """?€?„í”„?ˆì„ ë¬¸ì?´ì„ ë¶??¨ìœ„ë¡?ë³€?˜í•©?ˆë‹¤."""
    tf_map = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15,
        "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
    }
    return tf_map.get(timeframe, 1)


# ---------------------------
# Gap ì²˜ë¦¬ ë¡œì§(?´ë ˆ???¤í–‰/DLQ)
# ---------------------------
class GapWorker:
    """Gap ë°±í•„ ?Œì»¤ ???…ë¹„??REST API ?¤ì œ ?¸ì¶œ ë²„ì „."""

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
        """Redis ë°?DB ?°ê²°??ì´ˆê¸°?”í•©?ˆë‹¤."""
        self._redis = await _create_redis(self.redis_url)
        self._pool = await _create_pool(self.timescale_dsn)
        await self._save_worker_status(running=True)

    async def stop(self) -> None:
        """?Œì»¤ë¥?ì¢…ë£Œ?˜ê³  ë¦¬ì†Œ?¤ë? ?´ì œ?©ë‹ˆ??"""
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
            logger.debug("[worker] redis ì¢…ë£Œ ì¤??ˆì™¸", exc_info=True)
        try:
            if self._pool is not None:
                await self._pool.close()
        except Exception:
            logger.debug("[worker] pool ì¢…ë£Œ ì¤??ˆì™¸", exc_info=True)

    async def _save_worker_status(self, running: bool) -> None:
        """?Œì»¤ ?íƒœë¥?Redis???€?¥í•©?ˆë‹¤ (UI ëª¨ë‹ˆ?°ë§??.

        ?€????
            gap:worker:status       ??{"running": bool, "processed": int, "last_processed": ISO str}
            gap:worker:grace_period ??? ì˜ˆ ê¸°ê°„(ì´?
            gap:worker:count        ???œì„± ?Œì»¤ ??
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
            logger.debug("[worker] ?íƒœ ?€???¤íŒ¨(ë¬´ì‹œ): %s", exc)

    async def _zpopmax_once(self) -> List[Any]:
        """ZPOPMAXë¡?ê°€???°ì„ ?œìœ„ ?’ì? ??ª© 1ê°œë? êº¼ëƒ…?ˆë‹¤."""
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
            logger.exception("[worker] zpopmax ?¤íŒ¨")
            return []

    async def _claim_job(self, job_id: str) -> bool:
        """SETNXë¡??‘ì—…???´ë ˆ?„í•©?ˆë‹¤. ?´ë? ?´ë ˆ?„ëœ ê²½ìš° False ë°˜í™˜."""
        if self._redis is None:
            return False
        key = f"gap:claim:{job_id}"
        try:
            res = await self._redis.set(key, b"1", nx=True, ex=self.claim_ttl)
            return bool(res)
        except Exception:
            logger.exception("[worker] claim ?¤íŒ¨")
            return False

    async def _release_claim(self, job_id: str) -> None:
        """?´ë ˆ???¤ë? ?? œ?©ë‹ˆ??"""
        if self._redis is None:
            return
        key = f"gap:claim:{job_id}"
        try:
            await self._redis.delete(key)
        except Exception:
            logger.debug("[worker] claim ?? œ ?¤íŒ¨", exc_info=True)

    async def _move_to_dlq(self, gap_event: Dict[str, Any], reason: str) -> None:
        """?¤íŒ¨ ??ª©??DLQ??push?©ë‹ˆ??"""
        if self._redis is None:
            return
        try:
            gap_event["attempts"] = int(gap_event.get("attempts", 0)) + 1
            gap_event["last_error"] = reason
            member = _json_dumps(gap_event)
            await self._redis.lpush(self.dlq_key, member)
            logger.warning("[worker] ?‘ì—… DLQ ?´ë™: job_id=%s reason=%s", gap_event.get("job_id"), reason)
        except Exception:
            logger.exception("[worker] DLQ ?ì¬ ?¤íŒ¨")

    async def _process_gap_event(self, gap_event: Dict[str, Any]) -> bool:
        """?¤ì œ ?…ë¹„??REST APIë¥??¸ì¶œ?˜ì—¬ Gap êµ¬ê°„??ìº”ë“¤ ?°ì´?°ë? ë°±í•„?©ë‹ˆ??

        ??°©???˜ì´ì§€?¤ì´??
            end ??start ë°©í–¥?¼ë¡œ UPBIT_CANDLE_API_URL ?¸ì¶œ,
            candles ?Œì´ë¸”ì— ON CONFLICT DO NOTHING?¼ë¡œ ?½ì….

        Args:
            gap_event: Gap ?´ë²¤???•ì…”?ˆë¦¬ (job_id, symbol, timeframe, start, end ?¬í•¨)

        Returns:
            ?±ê³µ ?¬ë?
        """
        try:
            symbol: str = gap_event["symbol"]
            timeframe: str = gap_event.get("timeframe", "1m")
            start_str: str = gap_event.get("start", "")
            end_str: str = gap_event.get("end", "")
        except KeyError as exc:
            logger.error("[worker] gap_event ?„ë“œ ?„ë½: %s", exc)
            return False

        # ?œê°„ ?Œì‹±
        try:
            start_dt = datetime.fromisoformat(start_str) if start_str else None
            end_dt = datetime.fromisoformat(end_str) if end_str else datetime.now(tz=timezone.utc)
        except Exception as exc:
            logger.error("[worker] ?œê° ?Œì‹± ?¤íŒ¨: %s", exc)
            return False

        unit = _parse_timeframe_unit(timeframe)
        inserted_total = 0
        page_count = 0
        cursor_to = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # ??°©???˜ì´ì§€?¤ì´??(end ??start)
        while page_count < self.max_pages:
            candles = await _fetch_upbit_candles(
                symbol=symbol,
                to=cursor_to,
                unit=unit,
                count=self.max_candles_per_page,
            )
            if not candles:
                logger.info("[worker] ?…ë¹„??API ?‘ë‹µ ?†ìŒ ??ë°±í•„ ì¢…ë£Œ: symbol=%s", symbol)
                break

            rows: List[tuple] = []
            oldest_ts: Optional[datetime] = None

            for c in candles:
                try:
                    # ?…ë¹„??API ?‘ë‹µ ?„ë“œ ë§¤í•‘
                    ts_str = c.get("candle_date_time_utc") or c.get("timestamp", "")
                    if not ts_str:
                        continue
                    # ISO 8601 ?Œì‹± (Python 3.7+??'Z' ë¯¸ì?????rstrip ì²˜ë¦¬)
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
                        0,  # Upbit ë¶„ë´‰ API??trade_count ë¯¸ì œê³?
                    ))

                    if oldest_ts is None or ts < oldest_ts:
                        oldest_ts = ts
                except Exception as row_exc:
                    logger.debug("[worker] ???Œì‹± ?¤ë¥˜(ë¬´ì‹œ): %s", row_exc)

            if rows:
                n = await _insert_candles_batch(self._pool, rows)
                inserted_total += n
                logger.debug("[worker] ?˜ì´ì§€ %d: %d???½ì… (symbol=%s)", page_count + 1, n, symbol)

            page_count += 1

            # start_dt???„ë‹¬?ˆìœ¼ë©?ì¢…ë£Œ
            if start_dt is not None and oldest_ts is not None and oldest_ts <= start_dt:
                break

            # ?¤ìŒ ?˜ì´ì§€: ê°€???¤ë˜??ìº”ë“¤ ?œê°??ê¸°ì??¼ë¡œ ?¬ì¡°??
            if oldest_ts is not None:
                cursor_to = oldest_ts.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                break

            # API ?ë„ ?œí•œ ì¤€??(Upbit: ìµœë? 10req/s ??UPBIT_API_DELAY_SECONDS ê°„ê²©)
            await asyncio.sleep(UPBIT_API_DELAY_SECONDS)

        logger.info(
            "[worker] ë°±í•„ ?„ë£Œ: job_id=%s symbol=%s inserted=%d pages=%d",
            gap_event.get("job_id"), symbol, inserted_total, page_count,
        )
        return True

    async def claim_and_process_once(self) -> bool:
        """?ì—?????‘ì—…??êº¼ë‚´ ?´ë ˆ?„í•˜ê³?ì²˜ë¦¬?©ë‹ˆ??

        Returns:
            ?‘ì—…??ì²˜ë¦¬?ˆìœ¼ë©?True, ?ê? ë¹„ì—ˆê±°ë‚˜ ?¤í‚µ?ˆìœ¼ë©?False
        """
        items = await self._zpopmax_once()
        if not items:
            logger.debug("[worker] ì²˜ë¦¬??gap ?†ìŒ")
            return False

        member, score = items[0]
        try:
            if isinstance(member, (bytes, bytearray)):
                member = member.decode("utf-8")
            gap_event = _json_loads(member)
        except Exception:
            logger.exception("[worker] gap_event ?Œì‹± ?¤íŒ¨ - ?¤í‚µ")
            return False

        job_id = gap_event.get("job_id")
        if not job_id:
            logger.warning("[worker] job_id ?†ìŒ - ?¤í‚µ (isolator.py??_enqueue_gap() ?•ì¸ ?„ìš”)")
            return False

        # ?´ë ˆ??
        claimed = await self._claim_job(job_id)
        if not claimed:
            logger.info("[worker] ?´ë? ?´ë ˆ?„ëœ ?‘ì—…, ?¤í‚µ: job_id=%s", job_id)
            return False

        try:
            ok = await self._process_gap_event(gap_event)
            if ok:
                self._processed_count += 1
                await self._save_worker_status(running=True)
                logger.info("[worker] job ì²˜ë¦¬ ?±ê³µ: job_id=%s", job_id)
            else:
                await self._move_to_dlq(gap_event, "process_failed")
        except Exception as exc:
            logger.exception("[worker] job ì²˜ë¦¬ ì¤??ˆì™¸")
            await self._move_to_dlq(gap_event, f"exception:{exc}")
        finally:
            await self._release_claim(job_id)
        return True

    async def run_once(self) -> None:
        """?¨ì¼ ?‘ì—…??ì²˜ë¦¬?˜ê³  ì¢…ë£Œ?©ë‹ˆ??"""
        await self.start()
        try:
            await self.claim_and_process_once()
        finally:
            await self.stop()

    async def run_loop(self, poll_interval: float = 5.0) -> None:
        """?ê? ë¹??Œê¹Œì§€ ?°ì† ì²˜ë¦¬?©ë‹ˆ??"""
        await self.start()
        last_heartbeat = time.monotonic()
        try:
            while True:
                try:
                    has = await self.claim_and_process_once()
                    if not has:
                        await asyncio.sleep(poll_interval)
                    # 60ì´ˆë§ˆ??heartbeat ê°±ì‹  (idle ?íƒœ?ì„œ???íƒœ ??ë§Œë£Œ ë°©ì?)
                    now = time.monotonic()
                    if now - last_heartbeat >= 60.0:
                        await self._save_worker_status(running=True)
                        last_heartbeat = now
                except Exception:
                    logger.exception("[worker] ë£¨í”„ ì²˜ë¦¬ ì¤??ˆì™¸")
                    await asyncio.sleep(poll_interval)
        finally:
            await self.stop()


# ---------------------------
# PyQt5 ?°ë™??ë°±ê·¸?¼ìš´???¤ë ˆ??
# ---------------------------
class GapWorkerThread(threading.Thread):
    """GapWorkerë¥?ë³„ë„ ?¤ë ˆ?œì—???¤í–‰?˜ëŠ” ?˜í¼ (PyQt5 ???°ë™??.

    ?¬ìš© ??
        thread = GapWorkerThread(redis_url=..., timescale_dsn=...)
        thread.start()
        # ??ì¢…ë£Œ ??
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
        """?¤ë ˆ??ì§„ì…???????´ë²¤??ë£¨í”„?ì„œ GapWorker.run_loop() ?¤í–‰."""
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
            logger.exception("[GapWorkerThread] ë£¨í”„ ì¢…ë£Œ")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def stop(self) -> None:
        """?¤ë ˆ??ì¢…ë£Œë¥??”ì²­?©ë‹ˆ??"""
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)


# ---------------------------
# CLI
# ---------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gap Backfill Worker (?…ë¹„??REST API ?¤ì œ ?¸ì¶œ)")
    p.add_argument("--once", action="store_true", help="??ë²ˆë§Œ ?¤í–‰")
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
            logger.info("[worker] ?¬ìš©??ì¤‘ë‹¨?¼ë¡œ ì¢…ë£Œ")


if __name__ == "__main__":
    main()

