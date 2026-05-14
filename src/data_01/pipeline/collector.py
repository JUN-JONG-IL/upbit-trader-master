#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터 수집기 (Collector) — WebSocket/REST API → 파이프라인 1단계

목적:
    DB설계.md §9 10단계 파이프라인의 1단계:
    Upbit WebSocket/REST API에서 실시간 틱 데이터를 수신하고
    staging_candles에 즉시 저장 후 파이프라인으로 전달합니다.

처리 흐름:
    WebSocket 수신 → staging 저장 → Redis L1 캐시 갱신 →
    Kafka Producer 배치 전송 → Gap Detection

사용 예:
    collector = DataCollector(pool=pg_pool, redis=redis_client, producer=kafka_producer)
    await collector.start(symbols=["KRW-BTC", "KRW-ETH"])
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataCollector:
    """WebSocket/REST API 데이터 수집기.

    수신된 데이터를 파이프라인 순서대로 처리합니다:
    1. staging_candles 즉시 저장
    2. Redis L1 캐시 갱신
    3. Kafka Producer 배치 전송

    외부 의존성이 없을 경우 (pool/redis/producer = None)
    각 단계를 안전하게 스킵합니다.
    """

    def __init__(
        self,
        pool=None,
        redis_client=None,
        producer=None,
        batch_size: int = 1_000,
        flush_interval: float = 5.0,
    ) -> None:
        """
        Args:
            pool:           asyncpg 연결 풀 (TimescaleDB).
            redis_client:   Redis 클라이언트.
            producer:       KafkaProducer 인스턴스.
            batch_size:     배치 크기 (기본값: 1000).
            flush_interval: 강제 플러시 간격(초) (기본값: 5).
        """
        self._pool = pool
        self._redis = redis_client
        self._producer = producer
        self._batch_size = batch_size
        self._flush_interval = flush_interval

        self._buffer: List[Dict[str, Any]] = []
        # asyncio.Lock은 이벤트 루프가 실행 중일 때 생성해야 하므로 지연 초기화합니다.
        self._lock: Optional[asyncio.Lock] = None
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._on_candle: Optional[Callable] = None

    @property
    def _alock(self) -> asyncio.Lock:
        """이벤트 루프 컨텍스트 내에서 Lock을 지연 생성합니다."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def set_candle_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """캔들 수신 시 호출될 콜백을 등록합니다.

        Args:
            callback: 캔들 dict를 인자로 받는 함수/코루틴.
        """
        self._on_candle = callback

    async def receive(self, data: Dict[str, Any]) -> None:
        """WebSocket/REST에서 수신한 원시 데이터를 처리합니다.

        Args:
            data: 원시 캔들/틱 데이터 dict.
        """
        candle = self._normalize(data)
        async with self._alock:
            self._buffer.append(candle)
            if len(self._buffer) >= self._batch_size:
                await self._flush_locked()

        # Redis 심볼별 통계 기록 (WebSocket 탭 UI에서 사용)
        if self._redis:
            try:
                await self._update_ws_stats(candle)
            except Exception as exc:
                logger.debug("Redis WebSocket 통계 갱신 오류(무시): %s", exc)

        if self._on_candle:
            try:
                if asyncio.iscoroutinefunction(self._on_candle):
                    await self._on_candle(candle)
                else:
                    self._on_candle(candle)
            except Exception as exc:
                logger.warning("on_candle 콜백 오류: %s", exc)

    async def flush(self) -> int:
        """버퍼를 강제 플러시합니다.

        Returns:
            처리된 캔들 수.
        """
        async with self._alock:
            return await self._flush_locked()

    async def start(self, symbols: Optional[List[str]] = None) -> None:
        """수집기를 시작하고 자동 플러시 타스크를 등록합니다.

        Args:
            symbols: 수집할 심볼 목록 (로깅 목적).
        """
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        if symbols:
            logger.info("✅ DataCollector 시작 (%d 심볼)", len(symbols))

    async def stop(self) -> None:
        """수집기를 중지합니다."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info("✅ DataCollector 중지")

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    async def _update_ws_stats(self, candle: Dict[str, Any]) -> None:
        """Redis에 심볼별 WebSocket 수신 통계를 기록합니다.

        저장 키:
            ws:stats:{symbol}   — {"recv_count": N, "last_time": ISO, "status": "active"}
            ws:symbols          — 수신 중인 심볼 집합 (Set)
            ws:total_recv       — 누적 수신 건수 (INCR)
            ws:qps:{초}         — 초당 수신 건수 (INCR, EXPIRE 10초)
        """
        import json as _json
        import time as _time

        symbol: str = candle.get("symbol", "")
        if not symbol:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        stats_key = f"ws:stats:{symbol}"

        # 심볼 통계 갱신
        try:
            raw = self._redis.get(stats_key) if hasattr(self._redis, "get") else None
            if asyncio.iscoroutine(raw):
                raw = await raw
        except Exception:
            raw = None

        recv_count = 1
        if raw:
            try:
                prev = _json.loads(raw)
                recv_count = int(prev.get("recv_count", 0)) + 1
            except Exception:
                pass

        stats_obj = {
            "recv_count": recv_count,
            "last_time": now_iso,
            "status": "active",
            "compression_ratio": 0.0,
        }
        stats_json = _json.dumps(stats_obj, ensure_ascii=False)

        # 비동기/동기 Redis API 모두 지원
        if hasattr(self._redis, "set"):
            res = self._redis.set(stats_key, stats_json, ex=60)
            if asyncio.iscoroutine(res):
                await res
        if hasattr(self._redis, "sadd"):
            res = self._redis.sadd("ws:symbols", symbol)
            if asyncio.iscoroutine(res):
                await res
        if hasattr(self._redis, "incr"):
            res = self._redis.incr("ws:total_recv")
            if asyncio.iscoroutine(res):
                await res

        # QPS 카운터 (초 단위)
        sec_key = f"ws:qps:{int(_time.time())}"
        if hasattr(self._redis, "incr"):
            res = self._redis.incr(sec_key)
            if asyncio.iscoroutine(res):
                await res
            if hasattr(self._redis, "expire"):
                res = self._redis.expire(sec_key, 10)
                if asyncio.iscoroutine(res):
                    await res

    async def _flush_locked(self) -> int:
        """버퍼를 처리합니다 (락 획득 후 호출)."""
        if not self._buffer:
            return 0
        batch = self._buffer.copy()
        self._buffer.clear()

        count = len(batch)
        await self._save_staging(batch)
        await self._update_redis(batch)
        await self._send_kafka(batch)
        return count

    async def _periodic_flush(self) -> None:
        """주기적으로 버퍼를 플러시합니다."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            try:
                await self.flush()
            except Exception as exc:
                logger.error("주기적 플러시 오류: %s", exc)

    async def _save_staging(self, candles: List[Dict[str, Any]]) -> None:
        """staging_candles 테이블에 배치 저장합니다."""
        if not self._pool:
            return
        try:
            rows = [self._to_staging_row(c) for c in candles]
            import json
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO staging_candles
                        (symbol, timeframe, exchange, time,
                         open, high, low, close,
                         volume, quote_volume, trade_count, is_complete, seq)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    """,
                    rows,
                )
            logger.debug("staging_candles 저장: %d행", len(rows))
        except Exception as exc:
            logger.error("staging 저장 오류: %s", exc)

    async def _update_redis(self, candles: List[Dict[str, Any]]) -> None:
        """Redis L1 캐시를 갱신합니다."""
        if not self._redis:
            return
        try:
            from redis.cache_manager import CacheManager  # noqa: F401
            cm = CacheManager(self._redis)
            grouped: Dict[str, List] = {}
            for c in candles:
                k = f"{c.get('symbol')}:{c.get('timeframe', '1m')}"
                grouped.setdefault(k, []).append(c)
            for key, group in grouped.items():
                symbol, tf = key.split(":", 1)
                await cm.push_candle_batch(symbol, tf, group)
        except Exception as exc:
            logger.error("Redis 캐시 갱신 오류: %s", exc)

    async def _send_kafka(self, candles: List[Dict[str, Any]]) -> None:
        """Kafka Producer로 캔들 메시지를 배치 전송합니다."""
        if not self._producer:
            return
        try:
            for candle in candles:
                tf = candle.get("timeframe", "1m")
                topic = f"candle.{tf}"
                await self._producer.send_candle(topic, candle)
        except Exception as exc:
            logger.error("Kafka 전송 오류: %s", exc)

    # ------------------------------------------------------------------
    # 데이터 정규화
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
        """원시 데이터를 표준 캔들 형식으로 변환합니다."""
        now = datetime.now(timezone.utc)
        return {
            "symbol": data.get("symbol") or data.get("code") or "",
            "timeframe": data.get("timeframe") or data.get("interval") or "1m",
            "exchange": data.get("exchange", "upbit"),
            "time": data.get("time") or data.get("timestamp") or now,
            "open": float(data.get("open") or data.get("opening_price") or 0),
            "high": float(data.get("high") or data.get("high_price") or 0),
            "low": float(data.get("low") or data.get("low_price") or 0),
            "close": float(data.get("close") or data.get("trade_price") or 0),
            "volume": float(data.get("volume") or data.get("candle_acc_trade_volume") or 0),
            "quote_volume": float(data.get("quote_volume") or data.get("candle_acc_trade_price") or 0),
            "trade_count": int(data.get("trade_count") or 0),
            "is_complete": bool(data.get("is_complete", False)),
            "seq": data.get("seq"),
        }

    @staticmethod
    def _to_staging_row(c: Dict[str, Any]) -> tuple:
        return (
            c.get("symbol", ""),
            c.get("timeframe", "1m"),
            c.get("exchange", "upbit"),
            c.get("time"),
            c.get("open"),
            c.get("high"),
            c.get("low"),
            c.get("close"),
            c.get("volume", 0),
            c.get("quote_volume", 0),
            c.get("trade_count", 0),
            bool(c.get("is_complete", False)),
            c.get("seq"),
        )
