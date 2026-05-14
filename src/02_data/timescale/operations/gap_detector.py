#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimescaleDB 갭 감지기 (Gap Detector)

목적:
    latest_snapshot 테이블을 기반으로 심볼/타임프레임별 데이터 누락 구간을
    자동으로 감지하고 Redis Gap Fill 큐에 등록합니다.

Gap Detection 로직 (DB설계.md §12):
    1. latest_snapshot에서 마지막 수신 시각 조회
    2. 현재 시각과의 차이 계산
    3. 타임프레임 간격의 10배 초과 시 Gap으로 판정
    4. Redis gap_fill_queue에 우선순위와 함께 등록

사용 예:
    pool = await get_pool()
    redis = await get_redis()
    detector = GapDetector(pool, redis)
    gaps = await detector.detect("KRW-BTC", "1m")
    await detector.enqueue_all(gaps)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 타임프레임 → 초 단위
_TF_SECONDS: Dict[str, int] = {
    "1s": 1,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Gap 판정 배수 (타임프레임 간격의 N배 초과 시 Gap)
_GAP_FACTOR = 10

# Redis Gap Fill 큐 키
_QUEUE_KEY = "gap_fill_queue"


@dataclass
class GapRange:
    """감지된 갭 구간.

    Attributes:
        symbol:    심볼 (예: KRW-BTC).
        timeframe: 타임프레임 (예: 1m).
        start:     갭 시작 시각.
        end:       갭 종료 시각.
        priority:  큐 우선순위 (낮을수록 높음, 기본값: 5).
    """

    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    priority: int = 5

    @property
    def gap_seconds(self) -> float:
        """갭 크기(초)."""
        return (self.end - self.start).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Redis 큐 등록용 dict로 변환합니다."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "priority": self.priority,
            "gap_seconds": self.gap_seconds,
        }


class GapDetector:
    """TimescaleDB 기반 갭 감지기.

    최신 스냅샷을 쿼리하고 현재 시각과의 차이로 갭을 판정합니다.
    감지된 갭은 Redis 우선순위 큐에 등록됩니다.
    """

    def __init__(
        self,
        pool,
        redis_client=None,
        gap_factor: int = _GAP_FACTOR,
    ) -> None:
        """
        Args:
            pool:         asyncpg 연결 풀 (TimescaleDB).
            redis_client: Redis 클라이언트 (None이면 큐 등록 스킵).
            gap_factor:   Gap 판정 배수 (기본값: 10).
        """
        self._pool = pool
        self._redis = redis_client
        self._gap_factor = gap_factor

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def detect(
        self,
        symbol: str,
        timeframe: str,
    ) -> List[GapRange]:
        """단일 심볼/타임프레임의 갭을 감지합니다.

        Args:
            symbol:    심볼 (예: KRW-BTC).
            timeframe: 타임프레임 (예: 1m).

        Returns:
            감지된 GapRange 목록.
        """
        last_time = await self._get_latest_time(symbol, timeframe)
        if last_time is None:
            logger.debug("[GapDetector] %s/%s: 스냅샷 없음 — Gap 감지 스킵", symbol, timeframe)
            return []

        interval_sec = _TF_SECONDS.get(timeframe, 60)
        threshold = timedelta(seconds=interval_sec * self._gap_factor)
        now = datetime.now(timezone.utc)

        if (now - last_time) <= threshold:
            return []

        gap = GapRange(
            symbol=symbol,
            timeframe=timeframe,
            start=last_time,
            end=now,
            priority=self._calc_priority(now - last_time, interval_sec),
        )
        logger.info(
            "[GapDetector] Gap 감지: %s/%s  %.0f초 누락 (start=%s)",
            symbol,
            timeframe,
            gap.gap_seconds,
            last_time.isoformat(),
        )
        return [gap]

    async def detect_all(
        self,
        symbols: List[str],
        timeframes: Optional[List[str]] = None,
    ) -> List[GapRange]:
        """여러 심볼/타임프레임에 대해 갭을 일괄 감지합니다.

        Args:
            symbols:    심볼 목록.
            timeframes: 타임프레임 목록 (None이면 ["1m", "5m", "1h"]).

        Returns:
            감지된 GapRange 목록.
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "1h"]

        gaps: List[GapRange] = []
        for symbol in symbols:
            for tf in timeframes:
                detected = await self.detect(symbol, tf)
                gaps.extend(detected)
        return gaps

    async def enqueue(self, gap: GapRange) -> bool:
        """갭을 Redis gap_fill_queue에 등록합니다.

        Args:
            gap: 등록할 GapRange.

        Returns:
            성공 여부.
        """
        if not self._redis:
            return False
        try:
            import json
            score = float(gap.priority)
            value = json.dumps(gap.to_dict())
            await self._redis.zadd(_QUEUE_KEY, {value: score})
            logger.debug("[GapDetector] 큐 등록: %s/%s (priority=%d)", gap.symbol, gap.timeframe, gap.priority)
            return True
        except Exception as exc:
            logger.error("[GapDetector] 큐 등록 실패: %s", exc)
            return False

    async def enqueue_all(self, gaps: List[GapRange]) -> int:
        """갭 목록을 Redis 큐에 일괄 등록합니다.

        Args:
            gaps: 등록할 GapRange 목록.

        Returns:
            등록 성공 수.
        """
        count = 0
        for gap in gaps:
            if await self.enqueue(gap):
                count += 1
        return count

    async def get_queue_length(self) -> int:
        """Redis gap_fill_queue의 현재 길이를 반환합니다."""
        if not self._redis:
            return 0
        try:
            return await self._redis.zcard(_QUEUE_KEY)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    async def _get_latest_time(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[datetime]:
        """latest_snapshot 또는 candles 테이블에서 마지막 시각을 조회합니다."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                # latest_snapshot 우선 조회
                row = await conn.fetchrow(
                    """
                    SELECT last_candle_time
                    FROM latest_snapshot
                    WHERE symbol = $1 AND timeframe = $2
                    """,
                    symbol,
                    timeframe,
                )
                if row and row["last_candle_time"]:
                    return row["last_candle_time"]

                # fallback: candles 테이블 직접 조회
                row = await conn.fetchrow(
                    """
                    SELECT MAX(time) AS last_time
                    FROM candles
                    WHERE symbol = $1 AND timeframe = $2
                    """,
                    symbol,
                    timeframe,
                )
                if row and row["last_time"]:
                    return row["last_time"]
        except Exception as exc:
            logger.error("[GapDetector] 최신 시각 조회 실패 (%s/%s): %s", symbol, timeframe, exc)
        return None

    @staticmethod
    def _calc_priority(gap_delta: timedelta, interval_sec: int) -> int:
        """갭 크기에 따른 우선순위를 계산합니다 (1=최고, 5=최저).

        갭이 클수록 높은 우선순위(낮은 숫자)를 부여합니다.
        """
        ratio = gap_delta.total_seconds() / max(interval_sec, 1)
        if ratio > 1440:    # 1일 이상
            return 1
        elif ratio > 288:   # 5시간 이상
            return 2
        elif ratio > 60:    # 1시간 이상
            return 3
        elif ratio > 12:    # 12분 이상
            return 4
        else:
            return 5
