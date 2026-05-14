# -*- coding: utf-8 -*-
"""
TimescaleDB 캔들 UPSERT 배치 라이터 (안정화판)

주요 특징:
- 입력 시각(time/timestamp)을 UTC-aware datetime으로 표준화
- 수치 필드 강제 변환으로 정합성 보장
- asyncpg 스타일의 비동기 풀을 기본으로 지원(동기 pool/engine은 실행기에서 작업)
- 배치 업서트를 트랜잭션으로 수행하고 실패 시 지수 백오프 재시도
- 선택적 outbox 동작 지원(동일 트랜잭션 내 삽입 시도)
- 상세 한글 주석과 로깅 포함
- Pipeline에서 사용하는 async upsert/upsert_batch/flush API 제공
"""
from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BATCH_SIZE = 200
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.2  # 초, 지수 백오프

# asyncpg 스타일 positional placeholders 사용($1, $2, ...)
_UPSERT_SQL = """
INSERT INTO candles
    (time, symbol, timeframe, exchange,
     open, high, low, close,
     volume, quote_volume, trade_count,
     is_complete, seq, meta)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
ON CONFLICT (symbol, time, timeframe)
DO UPDATE SET
    open         = EXCLUDED.open,
    high         = EXCLUDED.high,
    low          = EXCLUDED.low,
    close        = EXCLUDED.close,
    volume       = EXCLUDED.volume,
    quote_volume = EXCLUDED.quote_volume,
    trade_count  = EXCLUDED.trade_count,
    is_complete  = EXCLUDED.is_complete,
    seq          = EXCLUDED.seq,
    meta         = EXCLUDED.meta
"""

_OUTBOX_SQL = """
INSERT INTO outbox (topic, key, payload, created_at)
VALUES ($1, $2, $3::jsonb, NOW())
"""

# ---------------------------------------------------------------------
# 헬퍼: 타입 정규화
# ---------------------------------------------------------------------
def _ensure_dt(value: Any) -> datetime:
    """다양한 형식(time / timestamp)을 UTC-aware datetime으로 표준화."""
    if isinstance(value, datetime):
        dt = value
    else:
        # 숫자(초 또는 ms) 또는 문자열 처리
        try:
            if isinstance(value, (int, float)):
                if value > 1e12:  # ms
                    dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            elif isinstance(value, str):
                s = value.strip()
                # ISO 'Z' 처리: '2023-01-01T00:00:00Z' -> '+00:00'
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                try:
                    dt = datetime.fromisoformat(s)
                except Exception:
                    # fallback: 숫자 문자열(epoch)
                    try:
                        num = float(s)
                        if num > 1e12:
                            dt = datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
                        else:
                            dt = datetime.fromtimestamp(num, tz=timezone.utc)
                    except Exception:
                        raise ValueError(f"time 파싱 실패: {value}")
            else:
                raise ValueError(f"지원되지 않는 time 타입: {type(value)}")
        except Exception as e:
            raise ValueError(f"time 파싱 실패: {value} ({e})")

    # timezone 처리: 없으면 UTC로 설정, 있으면 UTC로 변환
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _to_number(value: Any, default: Optional[float] = 0.0) -> float:
    """숫자 변환 시도, 실패 시 기본값 반환(로깅)."""
    if value is None:
        return float(default) if default is not None else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        logger.debug("숫자 변환 실패, 기본값 사용: %s", value)
        return float(default) if default is not None else 0.0


# ---------------------------------------------------------------------
# 행 변환: 입력 candle -> DB 행 튜플
# ---------------------------------------------------------------------
def _to_row(c: Dict[str, Any]) -> Tuple:
    """캔들 dict를 asyncpg executemany 행 튜플로 변환합니다."""
    # time 표준화
    t_raw = c.get("time") or c.get("timestamp") or c.get("start_ts") or c.get("ts")
    t = _ensure_dt(t_raw) if t_raw is not None else datetime.now(timezone.utc)

    meta = c.get("meta") or {}
    # trace_id 병합
    trace = c.get("trace_id") or c.get("trace") or None
    if trace:
        meta.setdefault("trace_id", trace)

    # seq 강제 정수화(존재하면)
    seq = c.get("seq")
    if seq is not None:
        try:
            seq = int(seq)
        except Exception:
            seq = None

    return (
        t,
        c.get("symbol", ""),
        c.get("timeframe", c.get("interval", "1m")),
        c.get("exchange", "upbit"),
        _to_number(c.get("open")),
        _to_number(c.get("high")),
        _to_number(c.get("low")),
        _to_number(c.get("close")),
        _to_number(c.get("volume"), 0.0),
        _to_number(c.get("quote_volume"), 0.0),
        int(c.get("trade_count") or 0),
        bool(c.get("is_complete", False)),
        seq,
        json.dumps(meta) if meta else None,
    )


# ---------------------------------------------------------------------
# CandleWriter 클래스
# ---------------------------------------------------------------------
class CandleWriter:
    """
    Candles 업서트 배치 라이터

    pool: asyncpg.pool (권장) 또는 sync 커넥션/엔진(호환성 옵션)
    사용방법:
      writer = CandleWriter(pool)
      await writer.upsert(candle)
      await writer.flush()
    """
    def __init__(self, pool: Any, batch_size: int = BATCH_SIZE) -> None:
        self._pool = pool
        self.batch_size = int(batch_size)
        self._buffer: List[Dict[str, Any]] = []
        # asyncio.Lock은 이벤트 루프가 실행 중일 때 생성해야 하므로 지연 초기화합니다.
        self._lock: Optional[asyncio.Lock] = None
        self._total_upserted = 0

        # 풀 종류 감지
        self._is_async_pool = False
        self._is_sync_pool = False
        try:
            # asyncpg 스타일 판단: acquire가 있으면 async pool로 간주(최선의 노력)
            if hasattr(pool, "acquire"):
                self._is_async_pool = True
            # sync 스타일: execute 메서드가 있으면 sync로 간주
            if not self._is_async_pool and hasattr(pool, "execute"):
                self._is_sync_pool = True
        except Exception:
            pass

        logger.info("[CandleWriter] initialized pool=%s async=%s sync=%s batch_size=%d", type(pool).__name__ if pool is not None else None, self._is_async_pool, self._is_sync_pool, self.batch_size)

    @property
    def _alock(self) -> asyncio.Lock:
        """이벤트 루프 컨텍스트 내에서 Lock을 지연 생성합니다."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # 공개 API
    async def upsert(self, candle: Dict[str, Any]) -> None:
        """단일 캔들을 버퍼에 추가하고 필요하면 flush 트리거."""
        async with self._alock:
            self._buffer.append(candle)
            if len(self._buffer) >= self.batch_size:
                await self._flush_locked()

    async def upsert_batch(self, candles: List[Dict[str, Any]]) -> int:
        """버퍼를 거치지 않고 즉시 업서트(비동기)."""
        if not candles:
            return 0
        rows = [_to_row(c) for c in candles]
        return await self._execute_with_outbox(rows, candles)

    async def flush(self) -> int:
        """버퍼에 남은 항목을 강제로 DB에 저장."""
        async with self._alock:
            return await self._flush_locked()

    @property
    def buffered_count(self) -> int:
        return len(self._buffer)

    @property
    def total_upserted(self) -> int:
        return self._total_upserted

    # 내부: 락 획득된 상태에서 호출
    async def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        if not self._pool:
            logger.warning("[CandleWriter] pool 미설정으로 flush 불가")
            return 0

        batch = list(self._buffer)
        rows = [_to_row(c) for c in batch]

        try:
            count = await self._execute_with_outbox(rows, batch)
            if count > 0:
                self._buffer.clear()
                self._total_upserted += count
            return count
        except Exception as exc:
            logger.exception("[CandleWriter] flush 실패: %s", exc)
            # 실패 시 버퍼는 유지(재시도 가능)
            raise

    # 핵심: asyncpg 스타일 실행 또는 동기풀에 대한 executor 실행
    async def _execute_with_outbox(self, rows: List[Tuple], source_candles: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        rows: asyncpg용 튜플 목록
        source_candles: outbox payload 생성용 원본
        반환: 업서트된 행 수 (추정)
        """
        attempt = 0
        last_exc: Optional[Exception] = None

        # 비동기 풀 사용 시(권장)
        if self._is_async_pool:
            while attempt <= _MAX_RETRIES:
                try:
                    # asyncpg pool acquire 패턴 가정
                    async with self._pool.acquire() as conn:
                        async with conn.transaction():
                            await conn.executemany(_UPSERT_SQL, rows)
                            # optional outbox
                            if source_candles:
                                outbox_rows = []
                                for c in source_candles:
                                    topic = c.get("outbox_topic") or f"market.candle.{c.get('timeframe','1m')}"
                                    key = c.get("symbol", "")
                                    payload = {
                                        "symbol": c.get("symbol"),
                                        "time": (c.get("time").isoformat() if isinstance(c.get("time"), datetime) else str(c.get("time"))),
                                        "timeframe": c.get("timeframe"),
                                        "meta": c.get("meta") or {},
                                        "trace_id": c.get("trace_id") or c.get("meta", {}).get("trace_id"),
                                    }
                                    outbox_rows.append((topic, key, json.dumps(payload)))
                                if outbox_rows:
                                    try:
                                        await conn.executemany(_OUTBOX_SQL, outbox_rows)
                                    except Exception as out_exc:
                                        # outbox 실패는 경고로 남기고 계속 진행
                                        logger.warning("[CandleWriter] outbox 삽입 실패(무시): %s", out_exc)
                    return len(rows)
                except Exception as exc:
                    last_exc = exc
                    attempt += 1
                    if attempt > _MAX_RETRIES:
                        logger.exception("[CandleWriter] DB 업서트 최종 실패: %s", exc)
                        raise
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning("[CandleWriter] DB 업서트 오류: %s — 재시도 %d/%d (%.2fs 대기)", exc, attempt, _MAX_RETRIES, delay)
                    await asyncio.sleep(delay)

        # 동기 풀/엔진일 경우: asyncio executor 에서 블로킹 호출로 처리
        if self._is_sync_pool:
            loop = asyncio.get_event_loop()
            while attempt <= _MAX_RETRIES:
                try:
                    result = await loop.run_in_executor(None, self._sync_execute_rows, rows, source_candles)
                    return result
                except Exception as exc:
                    last_exc = exc
                    attempt += 1
                    if attempt > _MAX_RETRIES:
                        logger.exception("[CandleWriter] sync DB 업서트 최종 실패: %s", exc)
                        raise
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning("[CandleWriter] sync DB 업서트 오류: %s — 재시도 %d/%d (%.2fs 대기)", exc, attempt, _MAX_RETRIES, delay)
                    await asyncio.sleep(delay)

        # pool 타입을 인식하지 못하면 실패
        logger.error("[CandleWriter] 실행할 수 있는 DB pool/engine이 없습니다")
        if last_exc:
            raise last_exc
        return 0

    # 동기 실행 헬퍼(동기 풀/엔진을 지원하기 위한 최후수단)
    def _sync_execute_rows(self, rows: List[Tuple], source_candles: Optional[List[Dict[str, Any]]]) -> int:
        """
        동기 DB 커넥션을 사용하여 업서트를 수행.
        - TimescaleConnector.get_connection() 사용 (재연결 로직 포함)
        - executemany 배치 처리 (개별 execute 대신)
        - 사용 후 put_connection()으로 연결 반환
        """
        pool = self._pool
        conn = None

        try:
            # ✅ TimescaleConnector에서 연결 가져오기 (재연결 로직 포함)
            if hasattr(pool, "get_connection"):
                conn = pool.get_connection(retry=True)
            elif hasattr(pool, "connect"):
                conn = pool.connect()
            elif hasattr(pool, "acquire"):
                conn = pool.acquire()
            else:
                conn = pool  # 이미 connection-like 객체일 수 있음

            # ✅ psycopg2 placeholder 변환 ($1 → %s)
            upsert_sql = _UPSERT_SQL
            for i in range(14, 0, -1):
                upsert_sql = upsert_sql.replace(f"${i}", "%s")

            # ✅ executemany 배치 처리
            with conn.cursor() as cur:
                cur.executemany(upsert_sql, rows)

            # ✅ outbox 처리
            if source_candles:
                outbox_rows = []
                outbox_sql = _OUTBOX_SQL
                for i in range(3, 0, -1):
                    outbox_sql = outbox_sql.replace(f"${i}", "%s")
                for c in source_candles:
                    topic = c.get("outbox_topic") or f"market.candle.{c.get('timeframe','1m')}"
                    key = c.get("symbol", "")
                    payload = {
                        "symbol": c.get("symbol"),
                        "time": (c.get("time").isoformat() if isinstance(c.get("time"), datetime) else str(c.get("time"))),
                        "timeframe": c.get("timeframe"),
                        "meta": c.get("meta") or {},
                        "trace_id": c.get("trace_id") or c.get("meta", {}).get("trace_id"),
                    }
                    outbox_rows.append((topic, key, json.dumps(payload)))
                try:
                    with conn.cursor() as cur:
                        cur.executemany(outbox_sql, outbox_rows)
                except Exception:
                    logger.warning("[CandleWriter] sync outbox 삽입 실패(무시)")

            conn.commit()
            logger.debug("[CandleWriter] ✅ 동기 executemany 성공: %d건", len(rows))
            return len(rows)

        except Exception as exc:
            logger.exception("[CandleWriter] ❌ sync executemany 실패: %s", exc)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise

        finally:
            # ✅ 연결 반환 (풀에 돌려주기)
            if conn is not None:
                if hasattr(pool, "put_connection"):
                    try:
                        pool.put_connection(conn)
                    except Exception as e:
                        logger.warning("[CandleWriter] 연결 반환 실패: %s", e)
                elif hasattr(conn, "close") and not hasattr(pool, "get_connection"):
                    try:
                        conn.close()
                    except Exception:
                        pass
