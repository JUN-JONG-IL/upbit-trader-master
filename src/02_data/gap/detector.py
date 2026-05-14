# -*- coding: utf-8 -*-
"""
Gap Detector - TimescaleDB + Redis 기반 Gap 검출 및 백필 큐 등록

설명:
- LEAD 윈도우 함수로 candles 테이블의 시간 간격 Gap 검출
- Cold Start 판별 (데이터 없을 때 스킵)
- Redis ZSET 우선순위 큐 및 TimescaleDB gaps 테이블에 동시 등록
- 우선순위 점수: priority_weight * log1p(gap_seconds) (중복 방지: NX)
- 주기적 자동 검사 지원 (run_forever)

사용:
    detector = GapDetector(pool, redis_client)
    count = await detector.detect_and_enqueue_all(["KRW-BTC", "KRW-ETH"])
    await detector.run_forever(["KRW-BTC"])
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import orjson  # type: ignore

logger = logging.getLogger(__name__)

# 타임프레임 → 초 단위
TF_SECONDS: Dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "1h": 3600,
    "1d": 86400,
}

# 우선순위 → 가중치 (높을수록 먼저 처리)
_PRIORITY_WEIGHTS: Dict[str, int] = {
    'HIGH': 1000,
    'MEDIUM': 500,
    'LOW': 100,
}


def _calculate_score(gap_seconds: float, priority_str: str) -> float:
    """Gap 우선순위 점수 계산.

    점수 = priority_weight * log1p(gap_seconds)
    """
    weight = _PRIORITY_WEIGHTS.get(priority_str.upper(), 500)
    return weight * math.log1p(gap_seconds)


class GapDetector:
    """TimescaleDB + Redis 기반 Gap 검출 및 백필 큐 등록"""

    def __init__(self, pool, redis_client, gap_factor: int = 2):
        """
        Args:
            pool: asyncpg.Pool
            redis_client: redis.asyncio.Redis
            gap_factor: Gap 판정 배수 (1분봉 기준 2분 이상 = Gap)
        """
        self._pool = pool
        self._redis = redis_client
        self._gap_factor = gap_factor

    async def has_initial_data(self, symbol: str, timeframe: str) -> bool:
        """Cold Start 판별: 데이터 최소 1건 이상 존재하면 True"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM candles WHERE symbol=$1 AND timeframe=$2 LIMIT 1",
                symbol, timeframe
            )
            return row is not None

    async def detect_gaps(
        self, symbol: str, timeframe: str, hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Gap 검출 (LEAD 윈도우 함수)

        Returns:
            [{"symbol": "KRW-BTC", "timeframe": "1m",
              "gap_start": datetime, "gap_end": datetime,
              "gap_seconds": 180, "priority": "MEDIUM"}, ...]
        """
        # Cold Start 스킵
        if not await self.has_initial_data(symbol, timeframe):
            logger.debug(
                "[GapDetector] %s/%s: 데이터 없음 - Gap 검사 스킵", symbol, timeframe
            )
            return []

        interval_sec = TF_SECONDS.get(timeframe, 60)
        threshold_sec = interval_sec * self._gap_factor

        sql = """
            WITH ranked AS (
                SELECT
                    time,
                    LEAD(time) OVER (ORDER BY time) AS next_time
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                    AND time > NOW() - ($3 * INTERVAL '1 hour')
            )
            SELECT time, next_time
            FROM ranked
            WHERE next_time IS NOT NULL
                AND EXTRACT(EPOCH FROM (next_time - time)) > $4
            ORDER BY time
        """

        gaps = []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, symbol, timeframe, hours, threshold_sec)

            for row in rows:
                gap_sec = (row["next_time"] - row["time"]).total_seconds()
                # 우선순위 문자열 분류
                if gap_sec >= interval_sec * 60:
                    priority_str = 'HIGH'
                elif gap_sec >= interval_sec * 10:
                    priority_str = 'MEDIUM'
                else:
                    priority_str = 'LOW'

                gaps.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "gap_start": row["time"],
                    "gap_end": row["next_time"],
                    "gap_seconds": int(gap_sec),
                    "priority": priority_str,
                })

                logger.info(
                    "[GapDetector] Gap 발견: %s/%s %gs 누락 (start=%s)",
                    symbol, timeframe, gap_sec, row["time"].isoformat(),
                )

        return gaps

    async def enqueue_gap(self, gap: Dict[str, Any]) -> bool:
        """Redis ZSET + TimescaleDB gaps 테이블 등록 (NX 중복 방지)."""
        gap_start = gap["gap_start"]
        gap_end = gap["gap_end"]
        gap_seconds = gap.get("gap_seconds", 0)
        priority_str = gap.get("priority", "MEDIUM")

        # 우선순위 점수 계산
        score = _calculate_score(float(gap_seconds), priority_str)

        # ISO 문자열 변환
        gap_start_iso = gap_start.isoformat() if isinstance(gap_start, datetime) else str(gap_start)

        # Redis ZSET 등록: JSON 형식 멤버 + 우선순위 점수 (NX로 중복 방지)
        try:
            member_key = orjson.dumps({
                "job_id": str(uuid.uuid4()),
                "symbol": gap["symbol"],
                "timeframe": gap["timeframe"],
                "start": gap_start_iso,
                "end": gap_end.isoformat() if isinstance(gap_end, datetime) else str(gap_end),
            }).decode("utf-8")
            await self._redis.zadd("gap_fill_queue", {member_key: score}, nx=True)
        except Exception as exc:
            logger.error("[GapDetector] Redis 큐 등록 실패: %s", exc)

        # DB 기록
        sql = """
            INSERT INTO gaps
                (symbol, timeframe, gap_start, gap_end, gap_seconds, priority, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending')
            ON CONFLICT (symbol, timeframe, gap_start) DO NOTHING
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                gap["symbol"], gap["timeframe"],
                gap_start, gap_end,
                gap_seconds, score,
            )

        return True

    async def detect_and_enqueue_all(
        self, symbols: List[str], timeframes: Optional[List[str]] = None, hours: int = 24
    ) -> int:
        """여러 심볼/타임프레임 Gap 검출 및 큐 등록"""
        if timeframes is None:
            timeframes = ["1m", "5m", "1h"]

        total = 0
        for symbol in symbols:
            for tf in timeframes:
                gaps = await self.detect_gaps(symbol, tf, hours)
                for gap in gaps:
                    await self.enqueue_gap(gap)
                    total += 1

        logger.info("[GapDetector] 총 %d개 Gap 등록 완료", total)
        return total

    async def run_forever(self, symbols: List[str], interval_sec: int = 300):
        """주기적 Gap 검사 (5분 주기)"""
        logger.info(
            "[GapDetector] 자동 Gap 검사 시작 (주기: %d초)", interval_sec
        )

        while True:
            try:
                count = await self.detect_and_enqueue_all(symbols, hours=24)
                logger.info("[GapDetector] Gap 검사 완료: %d개 발견", count)
            except Exception as exc:
                logger.error("[GapDetector] Gap 검사 실패: %s", exc, exc_info=True)

            await asyncio.sleep(interval_sec)


__all__ = ["GapDetector", "TF_SECONDS"]