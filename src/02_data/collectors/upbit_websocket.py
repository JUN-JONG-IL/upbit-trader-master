#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit WebSocket 클라이언트

실시간 Ticker/Orderbook/Trade 데이터를 WebSocket 으로 수신하고
TimescaleDB staging_candles 테이블에 Batch Insert 합니다.

주요 기능:
- 수신 데이터를 버퍼에 적재 후 Batch Insert
- Redis Pub/Sub 으로 실시간 업데이트 발행 (호환성: ticker:{symbol} 및 market.ticker.{symbol})
- 발행 시 채널 레지스트리(pubsub:channels)를 SADD로 등록
- 비치명적 실패는 경고로 처리
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 선택적 의존성
# ---------------------------------------------------------------------------
try:
    import websockets  # type: ignore
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    logger.warning("[UpbitWebSocket] websockets 미설치 — WebSocket 기능 비활성화")

try:
    import asyncpg  # type: ignore
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False
    logger.warning("[UpbitWebSocket] asyncpg 미설치 — TimescaleDB 저장 비활성화")

try:
    import redis.asyncio as aioredis  # type: ignore
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logger.warning("[UpbitWebSocket] redis 미설치 — Redis Pub/Sub 비활성화")

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
_WS_URI = "wss://api.upbit.com/websocket/v1"

# TimescaleDB 연결 설정: TIMESCALEDB_* 우선, 없으면 공통 PG* 환경변수 사용
_PG_HOST = os.getenv("TIMESCALEDB_HOST") or os.getenv("PGHOST", "127.0.0.1")
_PG_PORT = int(os.getenv("TIMESCALEDB_PORT") or os.getenv("PGPORT", "5432"))
_PG_DB = os.getenv("TIMESCALEDB_DB") or os.getenv("PGDATABASE", "upbit_trader")
_PG_USER = os.getenv("TIMESCALEDB_USER") or os.getenv("PGUSER", "postgres")
_PG_PASSWORD = os.getenv("TIMESCALEDB_PASSWORD") or os.getenv("PGPASSWORD", "")

# Redis connection envs (used to create aioredis client)
_REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
_REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
_REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# publish registry set name (can be overridden)
_PUBSUB_CHANNELS_SET = os.getenv("PUBSUB_CHANNELS_SET", "pubsub:channels")

_BATCH_SIZE = int(os.getenv("UPBIT_WS_BATCH_SIZE", "1000"))       # 버퍼 최대 건수
_FLUSH_INTERVAL = float(os.getenv("UPBIT_WS_FLUSH_INTERVAL", "1.0"))    # 강제 플러시 간격 (초)
_MAX_RECONNECT = int(os.getenv("UPBIT_WS_MAX_RECONNECT", "10"))      # 최대 재연결 횟수
_RECONNECT_DELAY = float(os.getenv("UPBIT_WS_RECONNECT_DELAY", "3.0"))   # 재연결 대기 시간 (초)

# staging_candles INSERT SQL
_STAGING_SQL = """
    INSERT INTO staging_candles
        (symbol, timeframe, time, open, high, low, close, volume,
         quote_volume, trade_count, exchange)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT DO NOTHING
"""

# ---------------------------------------------------------------------------
# UpbitWebSocket
# ---------------------------------------------------------------------------
class UpbitWebSocket:
    """Upbit WebSocket 클라이언트"""

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        on_ticker: Optional[Any] = None,
        max_reconnect: int = _MAX_RECONNECT,
    ) -> None:
        self.symbols: List[str] = symbols or []
        self.on_ticker = on_ticker
        self.max_reconnect = max_reconnect

        self._buffer: List[Dict[str, Any]] = []
        self._last_flush: float = time.monotonic()
        self._running: bool = False

        self._pg_pool: Optional[Any] = None  # asyncpg pool
        self._redis_client: Optional[Any] = None

    # ------------------------------------------------------------------
    # 진입점
    # ------------------------------------------------------------------
    async def start(self, symbols: Optional[List[str]] = None) -> None:
        if symbols:
            self.symbols = symbols
        if not self.symbols:
            logger.warning("[UpbitWebSocket] 구독 심볼 없음 — 실행 건너뜀")
            return

        self._running = True
        await self._init_connections()

        reconnect_count = 0
        while self._running and reconnect_count <= self.max_reconnect:
            try:
                await self._run_session()
                reconnect_count = 0
            except Exception as exc:
                reconnect_count += 1
                logger.error(
                    "[UpbitWebSocket] 연결 오류 (%d/%d): %s",
                    reconnect_count,
                    self.max_reconnect,
                    exc,
                )
                if reconnect_count <= self.max_reconnect:
                    await asyncio.sleep(_RECONNECT_DELAY)

        logger.info("[UpbitWebSocket] 종료")

    async def stop(self) -> None:
        self._running = False
        if self._buffer:
            await self._flush_buffer()

    # ------------------------------------------------------------------
    # 연결 초기화
    # ------------------------------------------------------------------
    async def _init_connections(self) -> None:
        if _ASYNCPG_AVAILABLE and self._pg_pool is None:
            try:
                logger.info(
                    "[UpbitWebSocket] TimescaleDB 연결 시도: host=%s port=%d db=%s user=%s",
                    _PG_HOST, _PG_PORT, _PG_DB, _PG_USER,
                )
                self._pg_pool = await asyncpg.create_pool(
                    host=_PG_HOST,
                    port=_PG_PORT,
                    database=_PG_DB,
                    user=_PG_USER,
                    password=_PG_PASSWORD,
                    min_size=2,
                    max_size=10,
                )
                logger.info("[UpbitWebSocket] TimescaleDB 연결 성공")
            except Exception as exc:
                logger.warning("[UpbitWebSocket] TimescaleDB 연결 실패: %s", exc)

        if _REDIS_AVAILABLE and self._redis_client is None:
            try:
                # Use connection URL if provided (compat)
                redis_url = os.getenv("REDIS_URL")
                if redis_url:
                    self._redis_client = aioredis.from_url(redis_url, decode_responses=True)
                else:
                    self._redis_client = aioredis.Redis(
                        host=_REDIS_HOST,
                        port=_REDIS_PORT,
                        password=_REDIS_PASSWORD,
                        decode_responses=True,
                    )
                await self._redis_client.ping()
                logger.info("[UpbitWebSocket] Redis 연결 성공")
            except Exception as exc:
                logger.warning("[UpbitWebSocket] Redis 연결 실패: %s", exc)
                self._redis_client = None

    # ------------------------------------------------------------------
    # WebSocket 세션
    # ------------------------------------------------------------------
    async def _run_session(self) -> None:
        if not _WS_AVAILABLE:
            logger.error("[UpbitWebSocket] websockets 미설치")
            self._running = False
            return

        ticket = str(uuid.uuid4())
        subscribe_msg = [
            {"ticket": ticket},
            {
                "type": "ticker",
                "codes": self.symbols,
                "isOnlyRealtime": True,
            },
            {"format": "SIMPLE"},
        ]

        logger.info("[UpbitWebSocket] 구독 시작: %d개 심볼", len(self.symbols))

        async with websockets.connect(
            _WS_URI,
            ping_interval=30,
            ping_timeout=10,
        ) as ws:
            await ws.send(json.dumps(subscribe_msg))
            logger.info("[UpbitWebSocket] 구독 메시지 전송 완료")

            async for raw in ws:
                if not self._running:
                    break

                try:
                    if isinstance(raw, bytes):
                        ticker = json.loads(raw.decode("utf-8"))
                    else:
                        ticker = json.loads(raw)
                    await self._handle_ticker(ticker)
                except (json.JSONDecodeError, UnicodeDecodeError, Exception) as exc:
                    logger.debug("[UpbitWebSocket] 틱 파싱 오류: %s", exc)

    # ------------------------------------------------------------------
    # 틱 처리
    # ------------------------------------------------------------------
    async def _handle_ticker(self, ticker: Dict[str, Any]) -> None:
        candle = self._to_candle(ticker)
        if candle is None:
            return

        symbol = candle.get("symbol", "")
        logger.debug("[WebSocket] 틱 수신: symbol=%s", symbol)

        if self.on_ticker:
            try:
                self.on_ticker(ticker)
            except Exception:
                pass

        self._buffer.append(candle)

        now = time.monotonic()
        should_flush = (
            len(self._buffer) >= _BATCH_SIZE
            or (now - self._last_flush) >= _FLUSH_INTERVAL
        )
        if should_flush:
            await self._flush_buffer()

    @staticmethod
    def _to_candle(ticker: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            symbol = ticker.get("cd") or ticker.get("code", "")
            if not symbol:
                return None

            trade_price = float(ticker.get("tp") or ticker.get("trade_price", 0))
            trade_volume = float(ticker.get("tv") or ticker.get("trade_volume", 0))
            timestamp_ms = int(
                ticker.get("tms") or ticker.get("timestamp", time.time() * 1000)
            )
            trade_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return {
                "symbol": symbol,
                "timeframe": "1t",
                "time": trade_time,
                "open": trade_price,
                "high": trade_price,
                "low": trade_price,
                "close": trade_price,
                "volume": trade_volume,
                "quote_volume": trade_price * trade_volume,
                "trade_count": 1,
                "exchange": "upbit",
            }
        except (KeyError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 버퍼 플러시
    # ------------------------------------------------------------------
    async def _flush_buffer(self) -> None:
        if not self._buffer:
            return

        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.monotonic()

        # TimescaleDB 저장
        if self._pg_pool is not None:
            await self._batch_insert_pg(batch)

        # Redis Pub/Sub 발행
        if self._redis_client is not None:
            await self._publish_redis(batch)

        # Redis 수신 통계 기록 (WebSocket 탭 UI에서 사용)
        if self._redis_client is not None:
            await self._record_ws_stats(batch)

        logger.debug("[UpbitWebSocket] 플러시 완료: %d건", len(batch))

    async def _record_ws_stats(self, candles: List[Dict[str, Any]]) -> None:
        """WebSocket 수신 통계를 Redis에 기록합니다.

        기록 항목:
            ws:symbols             — 수신 중인 심볼 목록 (Set)
            ws:stats:{symbol}      — 심볼별 수신 통계 Hash
            ws:total_recv          — 전체 누적 수신 카운터
            ws:qps:{epoch_second}  — 초당 QPS 슬라이딩 카운터 (TTL: 10초)
        모든 키 TTL: 300초 (5분)
        파이프라인을 사용하여 성능 최적화.

        Args:
            candles: 플러시된 캔들 목록
        """
        if not candles:
            return
        try:
            # 심볼별 수신 건수 집계
            symbol_counts: Dict[str, int] = {}
            symbol_last_time: Dict[str, str] = {}
            for c in candles:
                sym: str = str(c.get("symbol", ""))
                if not sym:
                    continue
                symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
                t = c.get("time")
                if t is not None:
                    symbol_last_time[sym] = t.isoformat() if hasattr(t, "isoformat") else str(t)

            now_sec = int(time.time())
            qps_key = f"ws:qps:{now_sec}"
            total_count = len(candles)

            pipe = self._redis_client.pipeline()
            for sym, count in symbol_counts.items():
                pipe.sadd("ws:symbols", sym)
                pipe.expire("ws:symbols", 300)
                # recv_count는 누적 카운터로 관리 (HSET 대신 HINCRBY 사용)
                pipe.hset(f"ws:stats:{sym}", mapping={
                    "status": "active",
                    "last_time": symbol_last_time.get(sym, ""),
                    "compression_ratio": "0.0",
                })
                pipe.hincrby(f"ws:stats:{sym}", "recv_count", count)
                pipe.expire(f"ws:stats:{sym}", 300)
            pipe.incr("ws:total_recv", total_count)
            pipe.expire("ws:total_recv", 300)
            pipe.incr(qps_key, total_count)
            pipe.expire(qps_key, 10)
            try:
                await pipe.execute()
            except Exception as pipe_exc:
                logger.warning("[UpbitWebSocket] Redis 통계 파이프라인 실패: %s", pipe_exc)
        except Exception as exc:
            logger.warning("[UpbitWebSocket] Redis 수신 통계 기록 실패(무시): %s", exc)

    async def _batch_insert_pg(self, candles: List[Dict[str, Any]]) -> None:
        try:
            records = [
                (
                    c["symbol"], c["timeframe"], c["time"],
                    c["open"], c["high"], c["low"], c["close"],
                    c["volume"], c["quote_volume"], c["trade_count"],
                    c["exchange"],
                )
                for c in candles
            ]
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(_STAGING_SQL, records)
            logger.info("[UpbitWebSocket] staging_candles 저장 완료: %d건", len(candles))
        except Exception as exc:
            logger.error("[UpbitWebSocket] TimescaleDB 저장 실패: %s", exc)
            await self._reset_pg_pool()

    async def _reset_pg_pool(self) -> None:
        if not _ASYNCPG_AVAILABLE:
            return
        try:
            if self._pg_pool:
                await self._pg_pool.close()
        except Exception:
            pass
        self._pg_pool = None
        try:
            self._pg_pool = await asyncpg.create_pool(
                host=_PG_HOST, port=_PG_PORT,
                database=_PG_DB, user=_PG_USER, password=_PG_PASSWORD,
                min_size=2, max_size=10,
            )
            logger.info("[UpbitWebSocket] TimescaleDB 재연결 성공")
        except Exception as exc:
            logger.error("[UpbitWebSocket] TimescaleDB 재연결 실패: %s", exc)

    async def _publish_redis(self, candles: List[Dict[str, Any]]) -> None:
        """
        최신 틱을 Redis 에 Pub/Sub 으로 발행합니다.
        변경점:
         - 채널 레지스트리(_PUBSUB_CHANNELS_SET)에 SADD로 채널을 등록합니다.
         - 기존 호환성 유지를 위해 두 채널명(ticker:{symbol} 및 market.ticker.{symbol})에 발행합니다.
         - 실패 시 경고 로깅만 수행합니다.
        """
        if not _REDIS_AVAILABLE or not self._redis_client:
            return

        try:
            pipe = self._redis_client.pipeline()
            for c in candles:
                # payload
                payload = json.dumps({
                    "symbol": c["symbol"],
                    "price": c["close"],
                    "volume": c["volume"],
                    "time": c["time"].isoformat(),
                }, default=str, ensure_ascii=False)

                # two channel naming schemes for compatibility
                ch1 = f"ticker:{c['symbol']}"
                ch2 = f"market.ticker.{c['symbol']}"

                # publish to both channels
                try:
                    pipe.publish(ch1, payload)
                    pipe.sadd(_PUBSUB_CHANNELS_SET, ch1)
                except Exception:
                    # continue; we'll try non-transactional later if pipeline fails
                    logger.debug("[UpbitWebSocket] pipeline publish/sadd failed for %s", ch1, exc_info=True)

                try:
                    pipe.publish(ch2, payload)
                    pipe.sadd(_PUBSUB_CHANNELS_SET, ch2)
                except Exception:
                    logger.debug("[UpbitWebSocket] pipeline publish/sadd failed for %s", ch2, exc_info=True)

            # execute pipeline
            try:
                await pipe.execute()
            except Exception:
                # If pipeline.execute fails, fallback to per-item best-effort calls
                logger.warning("[UpbitWebSocket] Redis pipeline execute failed; falling back to per-item publish")
                for c in candles:
                    payload = json.dumps({
                        "symbol": c["symbol"],
                        "price": c["close"],
                        "volume": c["volume"],
                        "time": c["time"].isoformat(),
                    }, default=str, ensure_ascii=False)
                    ch1 = f"ticker:{c['symbol']}"
                    ch2 = f"market.ticker.{c['symbol']}"
                    try:
                        await self._redis_client.publish(ch1, payload)
                    except Exception:
                        logger.debug("[UpbitWebSocket] publish failed for %s", ch1, exc_info=True)
                    try:
                        await self._redis_client.sadd(_PUBSUB_CHANNELS_SET, ch1)
                    except Exception:
                        logger.debug("[UpbitWebSocket] sadd failed for %s", ch1, exc_info=True)

                    try:
                        await self._redis_client.publish(ch2, payload)
                    except Exception:
                        logger.debug("[UpbitWebSocket] publish failed for %s", ch2, exc_info=True)
                    try:
                        await self._redis_client.sadd(_PUBSUB_CHANNELS_SET, ch2)
                    except Exception:
                        logger.debug("[UpbitWebSocket] sadd failed for %s", ch2, exc_info=True)

        except Exception as exc:
            logger.debug("[UpbitWebSocket] Redis 발행 처리 중 예외: %s", exc, exc_info=True)