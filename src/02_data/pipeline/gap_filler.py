#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap Filler (자동 백필) — 파이프라인 10단계

목적:
    DB설계.md §12 Gap Detection 및 자동 백필:
    Redis gap_fill_queue에서 우선순위대로 갭 작업을 꺼내
    Upbit REST API에서 누락 구간을 다운로드하여 candles 테이블에 저장합니다.

처리 흐름:
    Redis gap_fill_queue (ZPOPMIN) → Upbit REST API 조회 →
    CandleWriter UPSERT → MetadataManager 스냅샷 갱신

사용 예:
    filler = GapFiller(pool=pg_pool, redis=redis_client)
    await filler.start()
    await filler.run_loop()   # 블로킹 — Ctrl+C로 중지
    await filler.stop()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_QUEUE_KEY = "gap_fill_queue"
_LOOP_INTERVAL = 10.0        # 큐 확인 간격 (초)
_MAX_CANDLES_PER_REQUEST = 200  # Upbit API 최대 조회 수

# 타임프레임 → 초 단위
_TF_SECONDS = {
    "1s": 1, "1m": 60, "3m": 180, "5m": 300,
    "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}

# Upbit API 타임프레임 매핑
_UPBIT_TF_MAP = {
    "1m": ("minutes", 1),
    "3m": ("minutes", 3),
    "5m": ("minutes", 5),
    "15m": ("minutes", 15),
    "30m": ("minutes", 30),
    "1h": ("minutes", 60),
    "4h": ("minutes", 240),
    "1d": ("days", 1),
}


class GapFiller:
    """Redis 우선순위 큐 기반 자동 갭 백필 워커.

    gap_fill_queue에서 작업을 순서대로 꺼내 Upbit REST API로
    누락된 캔들 데이터를 채웁니다.
    """

    def __init__(
        self,
        pool=None,
        redis_client=None,
        loop_interval: float = _LOOP_INTERVAL,
    ) -> None:
        """
        Args:
            pool:          asyncpg 연결 풀 (TimescaleDB).
            redis_client:  Redis 클라이언트.
            loop_interval: 큐 확인 간격(초) (기본값: 10).
        """
        self._pool = pool
        self._redis = redis_client
        self._loop_interval = loop_interval
        self._running = False
        self._total_filled = 0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """GapFiller를 활성화합니다."""
        self._running = True
        logger.info("✅ GapFiller 시작 (interval=%.1fs)", self._loop_interval)

    async def stop(self) -> None:
        """GapFiller를 중지합니다."""
        self._running = False
        logger.info("✅ GapFiller 중지 (총 백필: %d 캔들)", self._total_filled)

    async def run_loop(self) -> None:
        """큐를 주기적으로 확인하고 갭을 채웁니다 (블로킹).

        stop()이 호출될 때까지 실행됩니다.
        """
        while self._running:
            try:
                processed = await self.process_one()
                if not processed:
                    await asyncio.sleep(self._loop_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("GapFiller 루프 오류: %s", exc)
                await asyncio.sleep(self._loop_interval)

    async def process_one(self) -> bool:
        """큐에서 우선순위 최고 작업을 하나 처리합니다.

        Returns:
            작업이 처리되었으면 True, 큐가 비었으면 False.
        """
        if not self._redis:
            return False

        try:
            import json
            # 우선순위 최고 항목 추출 (score 최소값)
            items = await self._redis.zpopmin(_QUEUE_KEY, 1)
            if not items:
                return False

            raw, score = items[0]
            gap_info = json.loads(raw)
        except Exception as exc:
            logger.error("큐 추출 오류: %s", exc)
            return False

        await self._fill_gap(gap_info)
        return True

    async def process_all(self) -> int:
        """큐의 모든 작업을 처리합니다.

        Returns:
            처리된 작업 수.
        """
        count = 0
        while True:
            processed = await self.process_one()
            if not processed:
                break
            count += 1
        return count

    async def backfill(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> int:
        """특정 구간의 캔들 데이터를 즉시 백필합니다.

        Args:
            symbol:    심볼 (예: KRW-BTC).
            timeframe: 타임프레임 (예: 1m).
            start:     백필 시작 시각.
            end:       백필 종료 시각 (None이면 현재 시각).

        Returns:
            저장된 캔들 수.
        """
        if end is None:
            end = datetime.now(timezone.utc)
        gap_info = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        return await self._fill_gap(gap_info)

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    async def _fill_gap(self, gap_info: Dict[str, Any]) -> int:
        """단일 갭 정보를 처리합니다."""
        symbol = gap_info.get("symbol", "")
        timeframe = gap_info.get("timeframe", "1m")
        start_str = gap_info.get("start", "")
        end_str = gap_info.get("end", "")

        if not symbol:
            return 0

        try:
            start = datetime.fromisoformat(start_str) if start_str else datetime.now(timezone.utc)
            end = datetime.fromisoformat(end_str) if end_str else datetime.now(timezone.utc)
        except ValueError:
            logger.warning("잘못된 갭 시간 형식: %s ~ %s", start_str, end_str)
            return 0

        logger.info(
            "[GapFiller] 백필 시작: %s/%s  %s ~ %s",
            symbol,
            timeframe,
            start.isoformat(),
            end.isoformat(),
        )

        candles = await self._fetch_candles(symbol, timeframe, start, end)
        if not candles:
            return 0

        saved = await self._save_candles(candles)
        self._total_filled += saved
        logger.info("[GapFiller] 백필 완료: %s/%s  %d 캔들", symbol, timeframe, saved)
        return saved

    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        """Upbit REST API에서 캔들 데이터를 조회합니다.

        단일 aiohttp.ClientSession을 재사용하여 연결 오버헤드를 최소화합니다.
        """
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp 미설치 — 캔들 조회 불가")
            return []

        unit_type, unit = _UPBIT_TF_MAP.get(timeframe, ("minutes", 1))
        interval_sec = _TF_SECONDS.get(timeframe, 60)
        all_candles: List[Dict[str, Any]] = []

        current_end = end
        # 단일 세션으로 모든 페이지 요청 처리 (연결 재사용)
        async with aiohttp.ClientSession() as session:
            while current_end > start:
                url = f"https://api.upbit.com/v1/candles/{unit_type}/{unit}"
                params = {
                    "market": symbol,
                    "to": current_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "count": _MAX_CANDLES_PER_REQUEST,
                }
                try:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                        if not data:
                            break
                        for item in data:
                            candle = self._parse_upbit_candle(item, symbol, timeframe)
                            if candle["time"] >= start:
                                all_candles.append(candle)
                        oldest = min(c["time"] for c in all_candles) if all_candles else start
                        if oldest <= start:
                            break
                        current_end = oldest - timedelta(seconds=interval_sec)
                except Exception as exc:
                    logger.error("캔들 조회 오류 (%s/%s): %s", symbol, timeframe, exc)
                    break

        return all_candles

    @staticmethod
    def _parse_upbit_candle(item: Dict[str, Any], symbol: str, timeframe: str) -> Dict[str, Any]:
        """Upbit API 응답을 표준 캔들 형식으로 변환합니다."""
        ts_str = item.get("candle_date_time_utc", "") or item.get("timestamp", "")
        try:
            if ts_str:
                t = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                t = datetime.now(timezone.utc)
        except ValueError:
            t = datetime.now(timezone.utc)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": "upbit",
            "time": t,
            "open": float(item.get("opening_price", 0)),
            "high": float(item.get("high_price", 0)),
            "low": float(item.get("low_price", 0)),
            "close": float(item.get("trade_price", 0)),
            "volume": float(item.get("candle_acc_trade_volume", 0)),
            "quote_volume": float(item.get("candle_acc_trade_price", 0)),
            "trade_count": int(item.get("unit", 0)),
            "is_complete": True,
        }

    async def _save_candles(self, candles: List[Dict[str, Any]]) -> int:
        """candles 테이블에 배치 UPSERT합니다."""
        if not self._pool or not candles:
            return 0
        from timescale.operations.candle_writer import CandleWriter
        writer = CandleWriter(self._pool)
        return await writer.upsert_batch(candles)
