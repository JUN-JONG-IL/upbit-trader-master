# -*- coding: utf-8 -*-
"""
src/data_01/gap/backfill_worker.py
Gap 諛깊븘 Worker

Redis ZSET ?곗꽑?쒖쐞 ??backfill:queue)?먯꽌 Gap??爰쇰궡 Upbit REST API瑜??몄텧?섏뿬
?꾨씫??罹붾뱾 援ш컙??TimescaleDB????ν빀?덈떎.

二쇱슂 湲곕뒫:
- ?곗꽑?쒖쐞 湲곕컲 諛곗튂 泥섎━ (zpopmax)
- Upbit REST API Rate Limit 以??(RateLimiter ?곸슜)
- 429 ?묐떟 ??Exponential Backoff ?ъ떆??
- 硫깅벑??蹂댁옣: ON CONFLICT DO NOTHING
- DLQ (Dead Letter Queue) 泥섎━
- gaps ?뚯씠釉??곹깭 ?낅뜲?댄듃
- ??硫ㅻ쾭 ???뺤떇 吏?? "symbol|timeframe|gap_start_iso"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp  # type: ignore
import orjson  # type: ignore

logger = logging.getLogger(__name__)

# Upbit REST API 湲곕낯 URL
UPBIT_API = "https://api.upbit.com/v1"

# ??꾪봽?덉엫 ??Upbit minutes ?⑥쐞
TF_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "1d": 1440,
}

# Rate Limit 429 ?ъ떆???ㅼ젙
_MAX_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BASE_SLEEP = 0.5  # 0.5s ??1s ??2s ??4s


class BackfillWorker:
    """Redis ZSET ?곗꽑?쒖쐞 ?먯뿉??Gap??媛?몄? Upbit API濡?諛깊븘"""

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
        """諛깊븘 ?뚯빱 ?쒖옉"""
        self._running = True
        logger.info("[BackfillWorker] ?쒖옉 (?대쭅: %gs)", self._poll_interval)

        while self._running:
            try:
                await self._process_batch()
            except Exception as exc:
                logger.error("[BackfillWorker] 泥섎━ ?ㅻ쪟: %s", exc, exc_info=True)

            await asyncio.sleep(self._poll_interval)

    async def stop(self):
        """諛깊븘 ?뚯빱 以묐떒"""
        self._running = False

    async def _process_batch(self):
        """Redis ?먯뿉??batch_size留뚰겮 Gap 泥섎━"""
        items = await self._redis.zpopmax("backfill:queue", count=self._batch_size)

        if not items:
            return

        for item in items:
            member = item[0] if isinstance(item, (list, tuple)) else item
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            try:
                # JSON ?뺤떇 ?쒕룄 (?덇굅???명솚)
                gap = orjson.loads(member)
            except Exception:
                # ???뺤떇: "symbol|timeframe|gap_start_iso"
                gap = self._parse_member_key(member)
            if gap is None:
                logger.warning("[BackfillWorker] Gap ?뚯떛 ?ㅽ뙣, 嫄대꼫?: %s", member)
                continue
            try:
                await self._backfill_gap(gap)
            except Exception as exc:
                logger.error("[BackfillWorker] Gap 泥섎━ ?ㅽ뙣: %s - %s", member, exc)

    @staticmethod
    def _parse_member_key(member: str) -> Optional[dict]:
        """Redis 硫ㅻ쾭 ???뚯떛: 'symbol|timeframe|gap_start_iso' ?뺤떇."""
        try:
            parts = member.split("|", 2)
            if len(parts) != 3:
                return None
            symbol, timeframe, gap_start_iso = parts
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "gap_start": gap_start_iso,
                "gap_end": None,  # ?꾩옱 ?쒓컖源뚯? 諛깊븘
            }
        except Exception:
            return None

    async def _backfill_gap(self, gap: dict):
        """Upbit REST API濡?Gap 援ш컙 罹붾뱾 ?곗씠??議고쉶 諛????(Rate Limit ???"""
        symbol = gap["symbol"]
        timeframe = gap.get("timeframe", "1m")
        gap_end_str = gap.get("gap_end")

        minutes = TF_TO_MINUTES.get(timeframe, 1)
        url = f"{UPBIT_API}/candles/minutes/{minutes}"

        params = {"market": symbol, "count": 200}
        if gap_end_str:
            params["to"] = gap_end_str

        logger.info("[BackfillWorker] 諛깊븘 ?쒖옉: %s/%s", symbol, timeframe)

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
                                "[BackfillWorker] Upbit REST Rate Limit ?꾨떖 (429) - %.1fs ?湲?(attempt %d/%d)",
                                sleep_time, attempt + 1, _MAX_RATE_LIMIT_RETRIES,
                            )
                            await asyncio.sleep(sleep_time)
                            continue
                        if resp.status != 200:
                            logger.warning(
                                "[BackfillWorker] Upbit API ?ㅻ쪟 %d: %s",
                                resp.status, symbol,
                            )
                            await self._move_to_dlq(gap, f"API error {resp.status}")
                            return
                        data = await resp.json(content_type=None)
                        break
            except Exception as exc:
                if attempt < _MAX_RATE_LIMIT_RETRIES - 1:
                    sleep_time = _RATE_LIMIT_BASE_SLEEP * (2 ** attempt)
                    logger.warning("[BackfillWorker] API ?몄텧 ?ㅽ뙣 (attempt %d/%d) - %.1fs ?湲? %s", attempt + 1, _MAX_RATE_LIMIT_RETRIES, sleep_time, exc)
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error("[BackfillWorker] API ?몄텧 理쒖쥌 ?ㅽ뙣: %s", exc)
                    await self._move_to_dlq(gap, str(exc))
                    return

        if data is None:
            logger.error("[BackfillWorker] Rate Limit 珥덇낵濡?諛깊븘 ?ㅽ뙣: %s/%s", symbol, timeframe)
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
                logger.warning("[BackfillWorker] 罹붾뱾 ?뚯떛 ?ㅽ뙣: %s", exc)

        if rows:
            await self._upsert_candles(rows)
            logger.info(
                "[BackfillWorker] 諛깊븘 ?꾨즺: %s/%s (%d媛?",
                symbol, timeframe, len(rows),
            )

        await self._mark_gap_resolved(gap)
        await asyncio.sleep(0.1)  # 湲곕낯 ?붿껌 媛꾧꺽 以??

    async def _upsert_candles(self, rows: list):
        """TimescaleDB 諛곗튂 UPSERT"""
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
        """gaps ?뚯씠釉??곹깭瑜?'resolved'濡??낅뜲?댄듃"""
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
        """?ㅽ뙣??Gap??DLQ濡??대룞"""
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
            "[BackfillWorker] Gap ??DLQ: %s (?댁쑀: %s)", gap["symbol"], reason
        )

