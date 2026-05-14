#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
Gap Detection 워커 - 캔들 데이터 누락 탐지 및 복구

[Responsibilities]
- 심볼별 캔들 데이터 연속성 검사 (Checker)
- 누락된 구간 탐지 및 로깅
- 복구 신호 발행 (Redis Pub/Sub)

[References]
- work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md 10장 (Checker)

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TIMEFRAME_MINUTES: Dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

_DEFAULT_CHECK_INTERVAL = 300  # 5분마다 Gap 검사

# 수집할 타임프레임 목록 (환경변수로 설정 가능, 기본: 1m/5m/1h)
_raw_enabled = os.getenv("ENABLED_TIMEFRAMES", "1m,5m,1h")
ENABLED_TIMEFRAMES: Tuple[str, ...] = tuple(
    tf.strip() for tf in _raw_enabled.split(",") if tf.strip()
)


class GapDetector:
    """
    캔들 데이터 Gap 탐지 워커

    타임프레임별 캔들 데이터의 연속성을 검사하고,
    누락된 구간을 Redis를 통해 복구 워커에 알립니다.

    Attributes:
        check_interval: 검사 주기 (초)
        timeframes: 검사할 타임프레임 목록
        max_gaps_per_run: 단일 실행당 최대 처리 Gap 수
    """

    def __init__(
        self,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
        timeframes: Optional[Tuple[str, ...]] = None,
        max_gaps_per_run: int = 100,
    ) -> None:
        self.check_interval = check_interval
        # 환경변수 ENABLED_TIMEFRAMES 또는 생성자 인자에서 타임프레임 결정
        self.timeframes = timeframes if timeframes is not None else ENABLED_TIMEFRAMES
        self.max_gaps_per_run = max_gaps_per_run
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Gap Detector 시작"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
        logger.info("[GapDetector] 시작 (interval=%ds)", self.check_interval)

    async def stop(self) -> None:
        """Gap Detector 중지"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("[GapDetector] 중지됨")

    async def run_once(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        단일 Gap 검사 실행

        Args:
            symbols: 검사할 심볼 목록 (None이면 활성 심볼 전체)

        Returns:
            탐지된 Gap 목록
        """
        return await detect_gaps(
            symbols=symbols,
            timeframes=self.timeframes,
            max_gaps=self.max_gaps_per_run,
        )

    async def _detection_loop(self) -> None:
        """주기적 Gap 탐지 루프"""
        while self._running:
            try:
                gaps = await self.run_once()
                if gaps:
                    logger.warning(
                        "[GapDetector] %d개의 Gap 탐지됨",
                        len(gaps),
                    )
                    await self._publish_gaps(gaps)
                else:
                    logger.debug("[GapDetector] Gap 없음")
            except Exception as exc:
                logger.warning("[GapDetector] 검사 오류: %s", exc)

            await asyncio.sleep(self.check_interval)

    async def _publish_gaps(self, gaps: List[Dict[str, Any]]) -> None:
        """Redis를 통해 Gap 복구 신호 발행"""
        try:
            import redis as redis_lib  # type: ignore
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            client = redis_lib.Redis(host=host, port=port, decode_responses=True)
            for gap in gaps:
                client.publish("gap:detected", json.dumps(gap))
            logger.debug("[GapDetector] %d개 Gap 발행됨", len(gaps))
        except Exception as exc:
            logger.debug("[GapDetector] Redis 발행 실패: %s", exc)


async def detect_gaps(
    symbols: Optional[List[str]] = None,
    timeframes: Optional[Tuple[str, ...]] = None,
    max_gaps: int = 100,
) -> List[Dict[str, Any]]:
    """
    캔들 데이터 Gap 탐지

    Args:
        symbols: 검사할 심볼 목록 (None이면 활성 심볼 전체)
        timeframes: 검사할 타임프레임 목록 (None이면 ENABLED_TIMEFRAMES 사용)
        max_gaps: 최대 반환 Gap 수

    Returns:
        탐지된 Gap 목록 (symbol, timeframe, gap_start, gap_end, missing_count 포함)
    """
    if timeframes is None:
        timeframes = ENABLED_TIMEFRAMES
    if symbols is None:
        symbols = await _get_active_symbols()

    if not symbols:
        return []

    all_gaps: List[Dict[str, Any]] = []

    for symbol in symbols:
        for tf in timeframes:
            if len(all_gaps) >= max_gaps:
                break
            gaps = await _check_symbol_gaps(symbol, tf)
            all_gaps.extend(gaps)

    return all_gaps[:max_gaps]


async def _check_symbol_gaps(symbol: str, tf: str) -> List[Dict[str, Any]]:
    """
    특정 심볼/타임프레임의 Gap 검사

    캔들 시간 목록에서 예상 시간 간격보다 큰 구간을 찾습니다.

    Args:
        symbol: 코인 심볼
        tf: 타임프레임

    Returns:
        탐지된 Gap 목록
    """
    interval_minutes = _TIMEFRAME_MINUTES.get(tf, 1)
    expected_delta = datetime.timedelta(minutes=interval_minutes)
    tolerance = datetime.timedelta(seconds=30)  # 허용 오차

    try:
        times = await _fetch_candle_times(symbol, tf, limit=10_000)
        if len(times) < 2:
            return []

        gaps = []
        for i in range(1, len(times)):
            gap = times[i - 1] - times[i]  # 최신 → 과거 순
            if gap > expected_delta + tolerance:
                missing = int(gap.total_seconds() // (interval_minutes * 60)) - 1
                if missing > 0:
                    gaps.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "gap_start": times[i].isoformat(),
                        "gap_end": times[i - 1].isoformat(),
                        "missing_count": missing,
                    })
        return gaps

    except Exception as exc:
        logger.debug("[GapDetector] %s %s 검사 실패: %s", symbol, tf, exc)
        return []


async def _fetch_candle_times(
    symbol: str, tf: str, limit: int = 10_000
) -> List[datetime.datetime]:
    """캔들 시간 목록 조회 (최신 순)"""
    try:
        from mongodb.core.handler import DBHandler  # type: ignore
        db = DBHandler(
            ip=os.getenv("MONGO_IP", "localhost"),
            port=int(os.getenv("MONGO_PORT", "27017")),
            id=os.getenv("MONGO_ID", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
        )
        collection = f"{symbol}_minute_1" if tf == "1m" else f"{symbol}_{tf}"
        result = await db.find_items(
            db_name="candles",
            collection_name=collection,
            query={},
            sort=[("time", -1)],
            limit=limit,
        )
        times = []
        for r in (result or []):
            raw_time = r.get("time")
            if raw_time:
                try:
                    if isinstance(raw_time, datetime.datetime):
                        times.append(raw_time)
                    else:
                        times.append(datetime.datetime.fromisoformat(str(raw_time)))
                except Exception:
                    pass
        return times
    except Exception:
        return []


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
