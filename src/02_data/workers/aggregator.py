#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
CAGG(Continuous Aggregate) Refresh 워커 - 집계 테이블 갱신

[Responsibilities]
- TimescaleDB Continuous Aggregate 갱신 (Aggregator 역할)
- 고차 타임프레임 캔들 계산 (1m → 5m, 15m, 1h, 4h, 1d)
- MongoDB 집계 데이터 갱신

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 10장 (Aggregator)
- work_order/DB설계.md 5.3

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 1m 기준 타임프레임 배수
_AGGREGATION_MAP: Dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

_DEFAULT_REFRESH_INTERVAL = 60  # 1분마다 집계 갱신


class Aggregator:
    """
    CAGG Refresh 워커

    1분 캔들 데이터를 기반으로 고차 타임프레임 캔들을
    주기적으로 집계 및 갱신합니다.

    Attributes:
        refresh_interval: 갱신 주기 (초)
        target_timeframes: 집계 대상 타임프레임
    """

    def __init__(
        self,
        refresh_interval: int = _DEFAULT_REFRESH_INTERVAL,
        target_timeframes: tuple = ("5m", "15m", "1h", "4h", "1d"),
    ) -> None:
        self.refresh_interval = refresh_interval
        self.target_timeframes = target_timeframes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Aggregator 시작"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("[Aggregator] 시작 (interval=%ds)", self.refresh_interval)

    async def stop(self) -> None:
        """Aggregator 중지"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("[Aggregator] 중지됨")

    async def run_once(
        self,
        symbols: Optional[List[str]] = None,
        since: Optional[datetime.datetime] = None,
    ) -> int:
        """
        단일 집계 실행

        Args:
            symbols: 집계할 심볼 목록 (None이면 활성 심볼 전체)
            since: 기준 시각 (None이면 최근 2시간)

        Returns:
            집계된 레코드 수
        """
        return await refresh_cagg(
            symbols=symbols,
            timeframes=self.target_timeframes,
            since=since,
        )

    async def _refresh_loop(self) -> None:
        """주기적 집계 루프"""
        while self._running:
            try:
                count = await self.run_once()
                logger.debug("[Aggregator] 집계 완료: %d 레코드", count)
            except Exception as exc:
                logger.warning("[Aggregator] 집계 오류: %s", exc)

            await asyncio.sleep(self.refresh_interval)


async def refresh_cagg(
    symbols: Optional[List[str]] = None,
    timeframes: tuple = ("5m", "15m", "1h", "4h", "1d"),
    since: Optional[datetime.datetime] = None,
) -> int:
    """
    Continuous Aggregate 갱신

    1m 캔들을 기반으로 고차 타임프레임 집계 데이터를 갱신합니다.

    Args:
        symbols: 집계할 심볼 목록 (None이면 활성 심볼 전체)
        timeframes: 집계 대상 타임프레임
        since: 기준 시각 (None이면 최근 2시간)

    Returns:
        갱신된 레코드 수
    """
    if since is None:
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)

    if symbols is None:
        symbols = await _get_active_symbols()

    if not symbols:
        return 0

    total = 0
    for symbol in symbols:
        for tf in timeframes:
            try:
                count = await _aggregate_candles(symbol, tf, since)
                total += count
            except Exception as exc:
                logger.debug("[Aggregator] %s %s 집계 실패: %s", symbol, tf, exc)

    return total


async def _aggregate_candles(
    symbol: str, tf: str, since: datetime.datetime
) -> int:
    """
    1m 캔들을 기반으로 특정 타임프레임 집계

    OHLCV 집계 규칙:
    - open: 첫 번째 캔들의 open
    - high: 모든 캔들의 high 최대값
    - low: 모든 캔들의 low 최소값
    - close: 마지막 캔들의 close
    - volume: 모든 캔들의 volume 합산

    Args:
        symbol: 코인 심볼
        tf: 목표 타임프레임
        since: 기준 시각

    Returns:
        갱신된 레코드 수
    """
    multiplier = _AGGREGATION_MAP.get(tf, 1)

    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )

        # 1m 캔들 조회
        collection_1m = f"{symbol}_minute_1"
        raw_candles = await db.find_items(
            db_name="candles",
            collection_name=collection_1m,
            query={"time": {"$gte": since.isoformat()}},
            sort=[("time", 1)],
        )

        if not raw_candles:
            return 0

        # 타임프레임 버킷으로 그룹화
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for candle in raw_candles:
            raw_time = candle.get("time", "")
            try:
                dt = (
                    raw_time
                    if isinstance(raw_time, datetime.datetime)
                    else datetime.datetime.fromisoformat(str(raw_time))
                )
                # 버킷 시작 시각 계산
                bucket_minutes = (dt.hour * 60 + dt.minute) // multiplier * multiplier
                bucket_dt = dt.replace(
                    hour=bucket_minutes // 60,
                    minute=bucket_minutes % 60,
                    second=0,
                    microsecond=0,
                )
                key = bucket_dt.isoformat()
                buckets.setdefault(key, []).append(candle)
            except Exception:
                continue

        # 집계 및 저장
        aggregated = []
        for bucket_time, candles in buckets.items():
            try:
                agg = {
                    "time": bucket_time,
                    "open": candles[0].get("open", 0),
                    "high": max(c.get("high", 0) for c in candles),
                    "low": min(c.get("low", float("inf")) for c in candles),
                    "close": candles[-1].get("close", 0),
                    "volume": sum(c.get("volume", 0) for c in candles),
                    "symbol": symbol,
                    "timeframe": tf,
                }
                aggregated.append(agg)
            except Exception:
                continue

        if aggregated:
            target_collection = f"{symbol}_{tf}"
            await db.insert_item_many(
                data=aggregated,
                db_name="candles",
                collection_name=target_collection,
                ordered=False,
            )
            logger.debug(
                "[Aggregator] %s %s 집계: %d 레코드",
                symbol, tf, len(aggregated),
            )
            return len(aggregated)

        return 0

    except ImportError:
        return 0
    except Exception as exc:
        logger.debug("[Aggregator] %s %s 집계 오류: %s", symbol, tf, exc)
        return 0


async def _get_active_symbols() -> List[str]:
    """MongoDB에서 활성 심볼 조회"""
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )
        result = await db.find_items(
            db_name="config",
            collection_name="active_symbols",
            query={"active": True},
        )
        return [r.get("symbol", "") for r in (result or []) if r.get("symbol")]
    except Exception:
        return []
