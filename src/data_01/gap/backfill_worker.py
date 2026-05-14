# -*- coding: utf-8 -*-
"""
src/data_01/gap/backfill_worker.py
Gap Î∞±ÌïÑ Worker

Redis ZSET ?∞ÏÑ†?úÏúÑ ??backfill:queue)?êÏÑú Gap??Í∫ºÎÇ¥ Upbit REST APIÎ•??∏Ï∂ú?òÏó¨
?ÑÎùΩ??Ï∫îÎì§ Íµ¨Í∞Ñ??TimescaleDB???Ä?•Ìï©?àÎã§.

Ï£ºÏöî Í∏∞Îä•:
- ?∞ÏÑ†?úÏúÑ Í∏∞Î∞ò Î∞∞Ïπò Ï≤òÎ¶¨ (zpopmax)
- Upbit REST API Rate Limit Ï§Ä??(RateLimiter ?ÅÏö©)
- 429 ?ëÎãµ ??Exponential Backoff ?¨Ïãú??
- Î©±Îì±??Î≥¥Ïû•: ON CONFLICT DO NOTHING
- DLQ (Dead Letter Queue) Ï≤òÎ¶¨
- gaps ?åÏù¥Î∏??ÅÌÉú ?ÖÎç∞?¥Ìä∏
- ??Î©§Î≤Ñ ???ïÏãù ÏßÄ?? "symbol|timeframe|gap_start_iso"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp  # type: ignore
import orjson  # type: ignore

logger = logging.getLogger(__name__)

# Upbit REST API Í∏∞Î≥∏ URL
UPBIT_API = "https://api.upbit.com/v1"

# ?Ä?ÑÌîÑ?àÏûÑ ??Upbit minutes ?®ÏúÑ
TF_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "1d": 1440,
}

# Rate Limit 429 ?¨Ïãú???§Ï†ï
_MAX_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BASE_SLEEP = 0.5  # 0.5s ??1s ??2s ??4s


class BackfillWorker:
    """Redis ZSET ?∞ÏÑ†?úÏúÑ ?êÏóê??Gap??Í∞Ä?∏Ï? Upbit APIÎ°?Î∞±ÌïÑ"""

    def __init__(
        self,
        pool,
        redis_client,
        poll_interval: float = 5.0,
        batch_size: int = 5,
    ):
        self._pool = pool
        self._redis = redis_client
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = False

    async def start(self):
        """Î∞±ÌïÑ ?åÏª§ ?úÏûë"""
        self._running = True
        logger.info("[BackfillWorker] ?úÏûë (?¥ÎßÅ: %gs)", self._poll_interval)

        while self._running:
            try:
                await self._process_batch()
            except Exception as exc:
                logger.error("[BackfillWorker] Ï≤òÎ¶¨ ?§Î•ò: %s", exc, exc_info=True)

            await asyncio.sleep(self._poll_interval)

    async def stop(self):
        """Î∞±ÌïÑ ?åÏª§ Ï§ëÎã®"""
        self._running = False

    async def _process_batch(self):
        """Redis ?êÏóê??batch_sizeÎßåÌÅº Gap Ï≤òÎ¶¨"""
        items = await self._redis.zpopmax("backfill:queue", count=self._batch_size)

        if not items:
            return

        for item in items:
            member = item[0] if isinstance(item, (list, tuple)) else item
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            try:
                # JSON ?ïÏãù ?úÎèÑ (?àÍ±∞???∏Ìôò)
                gap = orjson.loads(member)
            except Exception:
                # ???ïÏãù: "symbol|timeframe|gap_start_iso"
                gap = self._parse_member_key(member)
            if gap is None:
                logger.warning("[BackfillWorker] Gap ?åÏã± ?§Ìå®, Í±¥ÎÑà?Ä: %s", member)
                continue
            try:
                await self._backfill_gap(gap)
            except Exception as exc:
                logger.error("[BackfillWorker] Gap Ï≤òÎ¶¨ ?§Ìå®: %s - %s", member, exc)

    @staticmethod
    def _parse_member_key(member: str) -> Optional[dict]:
        """Redis Î©§Î≤Ñ ???åÏã±: 'symbol|timeframe|gap_start_iso' ?ïÏãù."""
        try:
            parts = member.split("|", 2)
            if len(parts) != 3:
                return None
            symbol, timeframe, gap_start_iso = parts
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "gap_start": gap_start_iso,
                "gap_end": None,  # ?ÑÏû¨ ?úÍ∞ÅÍπåÏ? Î∞±ÌïÑ
            }
        except Exception:
            return None

    async def _backfill_gap(self, gap: dict):
        """Upbit REST APIÎ°?Gap Íµ¨Í∞Ñ Ï∫îÎì§ ?∞Ïù¥??Ï°∞Ìöå Î∞??Ä??(Rate Limit ?Ä??"""
        symbol = gap["symbol"]
        timeframe = gap.get("timeframe", "1m")
        gap_end_str = gap.get("gap_end")

        minutes = TF_TO_MINUTES.get(timeframe, 1)
        url = f"{UPBIT_API}/candles/minutes/{minutes}"

        params = {"market": symbol, "count": 200}
        if gap_end_str:
            params["to"] = gap_end_str

        logger.info("[BackfillWorker] Î∞±ÌïÑ ?úÏûë: %s/%s", symbol, timeframe)

        data = None
        for attempt in range(_MAX_RATE_LIMIT_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 429:
                            # Rate Limit: Exponential Backoff
                            sleep_time = _RATE_LIMIT_BASE_SLEEP * (2 ** attempt)
                            logger.warning(
                                "[BackfillWorker] Upbit REST Rate Limit ?ÑÎã¨ (429) - %.1fs ?ÄÍ∏?(attempt %d/%d)",
                                sleep_time, attempt + 1, _MAX_RATE_LIMIT_RETRIES,
                            )
                            await asyncio.sleep(sleep_time)
                            continue
                        if resp.status != 200:
                            logger.warning(
                                "[BackfillWorker] Upbit API ?§Î•ò %d: %s",
                                resp.status, symbol,
                            )
                            await self._move_to_dlq(gap, f"API error {resp.status}")
                            return
                        data = await resp.json(content_type=None)
                        break
            except Exception as exc:
                if attempt < _MAX_RATE_LIMIT_RETRIES - 1:
                    sleep_time = _RATE_LIMIT_BASE_SLEEP * (2 ** attempt)
                    logger.warning("[BackfillWorker] API ?∏Ï∂ú ?§Ìå® (attempt %d/%d) - %.1fs ?ÄÍ∏? %s", attempt + 1, _MAX_RATE_LIMIT_RETRIES, sleep_time, exc)
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error("[BackfillWorker] API ?∏Ï∂ú ÏµúÏ¢Ö ?§Ìå®: %s", exc)
                    await self._move_to_dlq(gap, str(exc))
                    return

        if data is None:
            logger.error("[BackfillWorker] Rate Limit Ï¥àÍ≥ºÎ°?Î∞±ÌïÑ ?§Ìå®: %s/%s", symbol, timeframe)
            await self._move_to_dlq(gap, "Rate Limit exceeded")
            return

        if not data:
            await self._mark_gap_resolved(gap)
            return

        # TimescaleDB UPSERT
        rows = []
        for item in data:
            try:
                raw_time = item["candle_date_time_utc"]
                candle_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                if candle_time.tzinfo is None:
                    candle_time = candle_time.replace(tzinfo=timezone.utc)

                rows.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "exchange": "upbit",
                    "time": candle_time,
                    "open": float(item["opening_price"]),
                    "high": float(item["high_price"]),
                    "low": float(item["low_price"]),
                    "close": float(item["trade_price"]),
                    "volume": float(item.get("candle_acc_trade_volume", 0)),
                })
            except Exception as exc:
                logger.warning("[BackfillWorker] Ï∫îÎì§ ?åÏã± ?§Ìå®: %s", exc)

        if rows:
            await self._upsert_candles(rows)
            logger.info(
                "[BackfillWorker] Î∞±ÌïÑ ?ÑÎ£å: %s/%s (%dÍ∞?",
                symbol, timeframe, len(rows),
            )

        await self._mark_gap_resolved(gap)
        await asyncio.sleep(0.1)  # Í∏∞Î≥∏ ?îÏ≤≠ Í∞ÑÍ≤© Ï§Ä??

    async def _upsert_candles(self, rows: list):
        """TimescaleDB Î∞∞Ïπò UPSERT"""
        sql = """
            INSERT INTO candles
                (symbol, timeframe, exchange, time, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol, time, timeframe) DO UPDATE SET
                high = GREATEST(EXCLUDED.high, candles.high),
                low = LEAST(EXCLUDED.low, candles.low),
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """

        async with self._pool.acquire() as conn:
            await conn.executemany(sql, [
                (
                    r["symbol"], r["timeframe"], r["exchange"],
                    r["time"], r["open"], r["high"], r["low"],
                    r["close"], r["volume"],
                )
                for r in rows
            ])

    async def _mark_gap_resolved(self, gap: dict):
        """gaps ?åÏù¥Î∏??ÅÌÉúÎ•?'resolved'Î°??ÖÎç∞?¥Ìä∏"""
        sql = """
            UPDATE gaps
            SET status = 'resolved', resolved_at = NOW()
            WHERE symbol = $1 AND timeframe = $2 AND gap_start = $3
        """
        gap_start = gap["gap_start"]
        if isinstance(gap_start, str):
            gap_start = datetime.fromisoformat(gap_start)
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql, gap["symbol"], gap["timeframe"], gap_start
            )

    async def _move_to_dlq(self, gap: dict, reason: str):
        """?§Ìå®??Gap??DLQÎ°??¥Îèô"""
        gap_json = orjson.dumps(gap).decode("utf-8")
        await self._redis.rpush("backfill:dlq", gap_json)

        sql = """
            UPDATE gaps
            SET status = 'failed', retry_count = retry_count + 1
            WHERE symbol = $1 AND timeframe = $2 AND gap_start = $3
        """
        gap_start = gap["gap_start"]
        if isinstance(gap_start, str):
            gap_start = datetime.fromisoformat(gap_start)
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql, gap["symbol"], gap["timeframe"], gap_start
            )

        logger.warning(
            "[BackfillWorker] Gap ??DLQ: %s (?¥Ïú†: %s)", gap["symbol"], reason
        )

