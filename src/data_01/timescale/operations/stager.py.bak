#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stager (수정판)
- Validator 통합 (validate_candle_advanced + validate_candles_from_dicts)
- Gap-fill 큐잉 (Redis 'gap_fill_queue')
- Prometheus 메트릭(선택적) 연동

변경 요약:
- validator 모듈에서 단일-캔들 동기 함수(validate_candle_advanced)와
  비동기 배치 함수(validate_candles_from_dicts)를 우선적으로 import해서 사용.
- flush 시 배치 전체를 먼저 validator에 넘겨 비동기/벡터화된 이상치 검사를 시도.
- 이상 레코드는 isolated 처리, 정상 레코드만 bulk insert.
- validator가 없으면 기존 동작(무검증 insertion)을 유지.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import types
from typing import Optional, Dict, List, Set, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# constants.py 로드 (01_core 패키지명 Python 식별자 제한으로 직접 import 불가)
# ---------------------------------------------------------------------------
_CONST_PATH = Path(__file__).parents[3] / "01_core" / "config" / "constants.py"

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_stager_consts", str(_CONST_PATH))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        logging.debug("[stager] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()
_DEFAULT_TIMESCALE_HOST: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_CONSTS, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_DB", "upbit_trader")
_DEFAULT_REDIS_HOST: str = getattr(_CONSTS, "DEFAULT_REDIS_HOST", "127.0.0.1")
_DEFAULT_REDIS_PORT: int = getattr(_CONSTS, "DEFAULT_REDIS_PORT", 58530)

# 조건부 임포트
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logging.warning("⚠️  asyncpg 미설치 - TimescaleDB 연결 불가")

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except Exception:
    try:
        import aioredis as redis
        REDIS_AVAILABLE = True
    except Exception:
        REDIS_AVAILABLE = False
        logging.warning("⚠️  redis 미설치 - Redis 연결 불가")

try:
    import orjson
    ORJSON_AVAILABLE = True
except Exception:
    import json as orjson  # type: ignore
    ORJSON_AVAILABLE = False

# Validator import (단일/배치 모두 시도)
VALIDATOR_AVAILABLE = False
_validate_single = None  # type: ignore
_validate_batch = None  # type: ignore
try:
    # prefer both APIs if available
    from .validator import validate_candle_advanced, validate_candles_from_dicts  # type: ignore
    _validate_single = validate_candle_advanced
    _validate_batch = validate_candles_from_dicts
    VALIDATOR_AVAILABLE = True
except Exception:
    try:
        # fallback: single only
        from .validator import validate_candle_advanced  # type: ignore
        _validate_single = validate_candle_advanced
        VALIDATOR_AVAILABLE = True
    except Exception:
        VALIDATOR_AVAILABLE = False
        logging.warning("⚠️  validator 모듈 없음 - 검증 비활성")

# Metrics import (선택)
try:
    from utils.metrics.exporter import STAGER_RECEIVED, STAGER_INSERTED, VALIDATOR_ISOLATED
    METRICS_AVAILABLE = True
except Exception:
    STAGER_RECEIVED = STAGER_INSERTED = VALIDATOR_ISOLATED = None
    METRICS_AVAILABLE = False

LOG = logging.getLogger("data.stager")
LOG.setLevel(os.getenv("STAGER_LOG_LEVEL", "INFO"))

# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class StagingCandle:
    symbol: str
    timeframe: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    seq: Optional[int] = None
    trades: Optional[int] = None
    received_at: datetime = None

    def __post_init__(self):
        if self.received_at is None:
            self.received_at = datetime.now(timezone.utc)

    def to_dedupe_key(self) -> str:
        if self.seq is not None:
            return f"{self.symbol}:{self.timeframe}:{self.time.isoformat()}:{self.seq}"
        return f"{self.symbol}:{self.timeframe}:{self.time.isoformat()}"

@dataclass
class StagerStats:
    received_count: int = 0
    deduped_count: int = 0
    inserted_count: int = 0
    isolated_count: int = 0
    failed_count: int = 0
    last_flush_time: Optional[datetime] = None

# ============================================================
# DataStager
# ============================================================
class DataStager:
    def __init__(self, batch_size: int = 1000, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer: List[StagingCandle] = []
        self.stats = StagerStats()
        self._dedupe: Set[str] = set()
        self._flush_task: Optional[asyncio.Task] = None

        # DB / Redis pools (lazy)
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.redis: Optional[Any] = None

    async def initialize(self):
        if ASYNCPG_AVAILABLE and not self.pg_pool:
            pg_host = (
                os.getenv("TIMESCALE_HOST")
                or os.getenv("POSTGRES_HOST")
                or _DEFAULT_TIMESCALE_HOST
            )
            pg_port = int(
                os.getenv("TIMESCALE_PORT")
                or os.getenv("POSTGRES_PORT")
                or str(_DEFAULT_TIMESCALE_PORT)
            )
            pg_db = (
                os.getenv("TIMESCALE_DB")
                or os.getenv("POSTGRES_DB")
                or _DEFAULT_TIMESCALE_DB
            )
            pg_user = (
                os.getenv("TIMESCALE_USER")
                or os.getenv("POSTGRES_USER")
                or _DEFAULT_TIMESCALE_USER
            )
            self.pg_pool = await asyncpg.create_pool(
                host=pg_host,
                port=pg_port,
                database=pg_db,
                user=pg_user,
                password=os.getenv("TIMESCALE_PASSWORD") or os.getenv("POSTGRES_PASSWORD", ""),
                min_size=1, max_size=5
            )
            LOG.info("✅ Stager - Postgres pool ready")
        if REDIS_AVAILABLE and not self.redis:
            self.redis = redis.Redis(
                host=os.getenv("REDIS_HOST", _DEFAULT_REDIS_HOST),
                port=int(os.getenv("REDIS_PORT", str(_DEFAULT_REDIS_PORT))),
                password=os.getenv("REDIS_PASSWORD", None),
                decode_responses=True
            )
            try:
                await self.redis.ping()
                LOG.info("✅ Stager - Redis ready")
            except Exception as exc:
                LOG.warning("⚠️ Stager - Redis ping failed: %s", exc)
        # start periodic flush
        if not self._flush_task:
            self._flush_task = asyncio.create_task(self._periodic_flush())

    async def close(self):
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except Exception:
                pass
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass

    # --------------------------------------------------------
    # 수신된 원시 캔들을 내부 버퍼로 수신
    # --------------------------------------------------------
    def receive(self, candle: StagingCandle) -> None:
        key = candle.to_dedupe_key()
        self.stats.received_count += 1
        if key in self._dedupe:
            self.stats.deduped_count += 1
            return
        self._dedupe.add(key)
        self.buffer.append(candle)
        if METRICS_AVAILABLE and STAGER_RECEIVED:
            try:
                STAGER_RECEIVED.inc()
            except Exception:
                pass

    # --------------------------------------------------------
    # 주기적 flush
    # --------------------------------------------------------
    async def _periodic_flush(self):
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                if self.buffer:
                    await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOG.exception("Stager periodic flush failed: %s", e)

    # --------------------------------------------------------
    # 검증/격리/적재: 핵심 흐름
    # --------------------------------------------------------
    async def _flush(self):
        # Swap buffers to minimize lock time
        batch, self.buffer = self.buffer, []
        # Reset dedupe set to keep memory bounded (optional: keep recent keys)
        self._dedupe.clear()

        LOG.debug("Flushing %d candles", len(batch))
        # Convert to dicts for validator / insert
        batch_dicts = [
            {
                "symbol": c.symbol,
                "timeframe": c.timeframe,
                "time": c.time.isoformat() if isinstance(c.time, datetime) else c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "seq": c.seq,
                "received_at": c.received_at.isoformat() if isinstance(c.received_at, datetime) else c.received_at,
            }
            for c in batch
        ]

        # If validator available, use batch validation (best-effort)
        to_insert: List[StagingCandle] = []
        to_isolate: List[Tuple[StagingCandle, str]] = []

        if VALIDATOR_AVAILABLE and _validate_batch is not None:
            try:
                LOG.debug("Running batch validator for %d candles", len(batch_dicts))
                validation_summary = await _validate_batch(batch_dicts)
                # validation_summary expected to be same shape as CandleValidator.validate_candles
                # We infer outliers/failed_candles indices and warnings from returned structure.
                outliers = validation_summary.get("outliers", [])
                failed_idx_set = set()
                for o in outliers:
                    idx = o.get("index") if isinstance(o, dict) else None
                    if idx is not None:
                        failed_idx_set.add(int(idx))
                failed_list = validation_summary.get("failed_candles", [])
                for f in failed_list:
                    idx = f.get("index")
                    if idx is not None:
                        failed_idx_set.add(int(idx))

                # split
                for i, c in enumerate(batch):
                    if i in failed_idx_set:
                        reason = "validator_failed"
                        to_isolate.append((c, reason))
                    else:
                        to_insert.append(c)
                LOG.debug("Batch validator split -> insert=%d isolate=%d", len(to_insert), len(to_isolate))
            except Exception as e:
                LOG.warning("Batch validator failed, falling back to per-item validation: %s", e)
                # fallthrough to single-item validation below

        # If batch validator not used or failed, try per-item validator if available
        if (not to_insert and not to_isolate) and VALIDATOR_AVAILABLE and _validate_single is not None:
            LOG.debug("Running per-item validator for %d candles", len(batch))
            for c in batch:
                try:
                    # input as dict-like
                    cd = {
                        "symbol": c.symbol,
                        "timeframe": c.timeframe,
                        "time": c.time.isoformat() if isinstance(c.time, datetime) else c.time,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                        "seq": c.seq,
                    }
                    vr = _validate_single(cd)
                    if vr is None:
                        # treat as valid if validator returns None (older implementations)
                        to_insert.append(c)
                    elif isinstance(vr, dict):
                        # defensive: accept dict shaped result
                        valid_flag = vr.get("valid", True)
                        if not valid_flag:
                            to_isolate.append((c, "validator_failed"))
                        else:
                            to_insert.append(c)
                    else:
                        if vr.valid:
                            to_insert.append(c)
                        else:
                            reason = ";".join(vr.errors) if vr.errors else "validator_failed"
                            to_isolate.append((c, reason))
                except Exception as e:
                    LOG.exception("Per-item validation error: %s", e)
                    # On validator error, be conservative and isolate
                    to_isolate.append((c, f"validation_error:{e}"))

        # If still empty split (no validator present), insert all
        if not to_insert and not to_isolate:
            to_insert = batch

        # Attempt bulk insert of to_insert
        inserted = 0
        if to_insert:
            inserted = await self._bulk_insert_staging(to_insert)
            self.stats.inserted_count += inserted
            if METRICS_AVAILABLE and STAGER_INSERTED:
                try:
                    STAGER_INSERTED.inc(inserted)
                except Exception:
                    pass
            LOG.info(f"✅ Staging 저장: {inserted}개 (received={self.stats.received_count}, deduped={self.stats.deduped_count})")

        # Handle isolation of to_isolate
        if to_isolate:
            try:
                await self._isolate_candles([c for c, _ in to_isolate], ";".join(set(r for _, r in to_isolate)))
                self.stats.isolated_count += len(to_isolate)
                if METRICS_AVAILABLE and VALIDATOR_ISOLATED:
                    try:
                        VALIDATOR_ISOLATED.inc(len(to_isolate))
                    except Exception:
                        pass
                LOG.info(f"⚠️ Isolated {len(to_isolate)} candles after validation")
            except Exception as e:
                LOG.exception("Failed to isolate candles: %s", e)
                self.stats.failed_count += len(to_isolate)

        self.stats.last_flush_time = datetime.now(timezone.utc)

    # ----------------------------
    # DB insert helpers (기존 로직 유지)
    # ----------------------------
    async def _bulk_insert_staging(self, candles: List[StagingCandle]) -> int:
        if not self.pg_pool:
            logging.error("❌ TimescaleDB 연결 없음")
            return 0
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    records = [
                        (
                            c.time,
                            c.symbol,
                            c.timeframe,
                            c.open,
                            c.high,
                            c.low,
                            c.close,
                            c.volume,
                            c.seq,
                            c.trades,
                            c.received_at
                        )
                        for c in candles
                    ]
                    result = await conn.copy_records_to_table(
                        'staging_candles',
                        records=records,
                        columns=[
                            'time', 'symbol', 'timeframe', 'open', 'high', 'low', 'close',
                            'volume', 'seq', 'trades', 'received_at'
                        ]
                    )
                    count = int(str(result).split()[-1]) if result else len(records)
                    return count
        except Exception as e:
            logging.error(f"❌ Bulk insert 실패: {e}")
            try:
                return await self._fallback_insert_staging(candles)
            except Exception as ex:
                logging.error(f"❌ Fallback insert 실패: {ex}")
                raise

    async def _fallback_insert_staging(self, candles: List[StagingCandle]) -> int:
        if not self.pg_pool:
            return 0
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                query = """
                    INSERT INTO staging_candles 
                    (time, symbol, timeframe, open, high, low, close, volume, seq, trades, received_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """
                args = [
                    (
                        c.time, c.symbol, c.timeframe, c.open, c.high, c.low, c.close,
                        c.volume, c.seq, c.trades, c.received_at
                    )
                    for c in candles
                ]
                await conn.executemany(query, args)
                return len(candles)

    # ----------------------------
    # Isolate / Gap queue
    # ----------------------------
    async def _isolate_candles(self, candles: List[StagingCandle], reason: str):
        if not self.pg_pool:
            logging.error("❌ TimescaleDB 연결 없음 (isolate)")
            return
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    query = """
                        INSERT INTO isolated_candles 
                        (time, symbol, timeframe, payload, reason, isolation_reason, isolated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """
                    args = []
                    for c in candles:
                        payload = {
                            "symbol": c.symbol,
                            "time": c.time.isoformat() if isinstance(c.time, datetime) else c.time,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                            "seq": c.seq,
                            "received_at": c.received_at.isoformat() if isinstance(c.received_at, datetime) else c.received_at
                        }
                        args.append((c.time, c.symbol, c.timeframe, json.dumps(payload, default=str), reason, reason, datetime.now(timezone.utc)))
                    await conn.executemany(query, args)
        except Exception as e:
            logging.exception("❌ Isolate DB insert failed: %s", e)
            raise

# EOF