# -*- coding: utf-8 -*-
"""
src/02_data/gap/backfill_worker.py
Gap 백필 Worker

Redis ZSET 우선순위 큐(backfill:queue)에서 Gap을 꺼내 Upbit REST API를 호출하여
누락된 캔들 구간을 TimescaleDB에 저장합니다.

주요 기능:
- 우선순위 기반 배치 처리 (zpopmax)
- Upbit REST API Rate Limit 준수 (RateLimiter 적용)
- 429 응답 시 Exponential Backoff 재시도
- 멱등성 보장: ON CONFLICT DO NOTHING
- DLQ (Dead Letter Queue) 처리
- gaps 테이블 상태 업데이트
- 새 멤버 키 형식 지원: "symbol|timeframe|gap_start_iso"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp  # type: ignore
import orjson  # type: ignore

logger = logging.getLogger(__name__)

# Upbit REST API 기본 URL
UPBIT_API = "https://api.upbit.com/v1"

# 타임프레임 → Upbit minutes 단위
TF_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "1d": 1440,
}

# Rate Limit 429 재시도 설정
_MAX_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BASE_SLEEP = 0.5  # 0.5s → 1s → 2s → 4s


class BackfillWorker:
    """Redis ZSET 우선순위 큐에서 Gap을 가져와 Upbit API로 백필"""

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
        """백필 워커 시작"""
        self._running = True
        logger.info("[BackfillWorker] 시작 (폴링: %gs)", self._poll_interval)

        while self._running:
            try:
                await self._process_batch()
            except Exception as exc:
                logger.error("[BackfillWorker] 처리 오류: %s", exc, exc_info=True)

            await asyncio.sleep(self._poll_interval)

    async def stop(self):
        """백필 워커 중단"""
        self._running = False

    async def _process_batch(self):
        """Redis 큐에서 batch_size만큼 Gap 처리"""
        items = await self._redis.zpopmax("backfill:queue", count=self._batch_size)

        if not items:
            return

        for item in items:
            member = item[0] if isinstance(item, (list, tuple)) else item
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            try:
                # JSON 형식 시도 (레거시 호환)
                gap = orjson.loads(member)
            except Exception:
                # 새 형식: "symbol|timeframe|gap_start_iso"
                gap = self._parse_member_key(member)
            if gap is None:
                logger.warning("[BackfillWorker] Gap 파싱 실패, 건너뜀: %s", member)
                continue
            try:
                await self._backfill_gap(gap)
            except Exception as exc:
                logger.error("[BackfillWorker] Gap 처리 실패: %s - %s", member, exc)

    @staticmethod
    def _parse_member_key(member: str) -> Optional[dict]:
        """Redis 멤버 키 파싱: 'symbol|timeframe|gap_start_iso' 형식."""
        try:
            parts = member.split("|", 2)
            if len(parts) != 3:
                return None
            symbol, timeframe, gap_start_iso = parts
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "gap_start": gap_start_iso,
                "gap_end": None,  # 현재 시각까지 백필
            }
        except Exception:
            return None

    async def _backfill_gap(self, gap: dict):
        """Upbit REST API로 Gap 구간 캔들 데이터 조회 및 저장 (Rate Limit 대응)"""
        symbol = gap["symbol"]
        timeframe = gap.get("timeframe", "1m")
        gap_end_str = gap.get("gap_end")

        minutes = TF_TO_MINUTES.get(timeframe, 1)
        url = f"{UPBIT_API}/candles/minutes/{minutes}"

        params = {"market": symbol, "count": 200}
        if gap_end_str:
            params["to"] = gap_end_str

        logger.info("[BackfillWorker] 백필 시작: %s/%s", symbol, timeframe)

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
                                "[BackfillWorker] Upbit REST Rate Limit 도달 (429) - %.1fs 대기 (attempt %d/%d)",
                                sleep_time, attempt + 1, _MAX_RATE_LIMIT_RETRIES,
                            )
                            await asyncio.sleep(sleep_time)
                            continue
                        if resp.status != 200:
                            logger.warning(
                                "[BackfillWorker] Upbit API 오류 %d: %s",
                                resp.status, symbol,
                            )
                            await self._move_to_dlq(gap, f"API error {resp.status}")
                            return
                        data = await resp.json(content_type=None)
                        break
            except Exception as exc:
                if attempt < _MAX_RATE_LIMIT_RETRIES - 1:
                    sleep_time = _RATE_LIMIT_BASE_SLEEP * (2 ** attempt)
                    logger.warning("[BackfillWorker] API 호출 실패 (attempt %d/%d) - %.1fs 대기: %s", attempt + 1, _MAX_RATE_LIMIT_RETRIES, sleep_time, exc)
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error("[BackfillWorker] API 호출 최종 실패: %s", exc)
                    await self._move_to_dlq(gap, str(exc))
                    return

        if data is None:
            logger.error("[BackfillWorker] Rate Limit 초과로 백필 실패: %s/%s", symbol, timeframe)
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
                logger.warning("[BackfillWorker] 캔들 파싱 실패: %s", exc)

        if rows:
            await self._upsert_candles(rows)
            logger.info(
                "[BackfillWorker] 백필 완료: %s/%s (%d개)",
                symbol, timeframe, len(rows),
            )

        await self._mark_gap_resolved(gap)
        await asyncio.sleep(0.1)  # 기본 요청 간격 준수

    async def _upsert_candles(self, rows: list):
        """TimescaleDB 배치 UPSERT"""
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
        """gaps 테이블 상태를 'resolved'로 업데이트"""
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
        """실패한 Gap을 DLQ로 이동"""
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
            "[BackfillWorker] Gap → DLQ: %s (이유: %s)", gap["symbol"], reason
        )
