#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap-fill worker (Upbit REST) - PoC

목적
- Redis 리스트 "gap_fill_queue"에서 gap task 소비
- 각 task에 대해 Upbit REST candles API로 누락된 캔들(예: 1m)을 백필
- 취득한 캔들을 staging_candles에 asyncpg.copy_records_to_table로 삽입
- 재시도 / rate-limit / 단순 backoff 처리

사용법
- REDIS_*, POSTGRES_* 환경변수 설정 필요
- 의존성: aiohttp, asyncpg, redis.asyncio (또는 aioredis)
- 실행:
    python src/data/gap_fill_worker.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import json
import logging
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List, Dict, Any

# 타입 검사 시에만 ClientSession을 import 하도록 처리 -> Pylance 타입-문제 회피
if TYPE_CHECKING:
    from aiohttp import ClientSession  # type: ignore

try:
    import aiohttp
except Exception:
    aiohttp = None  # type: ignore

try:
    import asyncpg
except Exception:
    asyncpg = None  # type: ignore

# redis.asyncio preferred, fall back to aioredis
try:
    import redis.asyncio as redis  # type: ignore
except Exception:
    try:
        import aioredis as redis  # type: ignore
    except Exception:
        redis = None  # type: ignore

LOG = logging.getLogger("gap_fill_worker")
# DEBUG로 설정하여 HTTP 요청/응답 및 DB 삽입 과정을 자세히 기록
LOG.setLevel(logging.DEBUG)

UPBIT_BASE_DEFAULT = "https://api.upbit.com"
UPBIT_MAX_PER_REQUEST = 200  # Upbit limit for candles/minutes

# ---------------------------------------------------------------------------
# constants.py 로드 (01_core 패키지명 Python 식별자 제한으로 직접 import 불가)
# ---------------------------------------------------------------------------
_CONST_PATH = Path(__file__).parents[3] / "01_core" / "config" / "constants.py"

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_gap_fill_consts", str(_CONST_PATH))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        LOG.debug("[gap_fill_worker] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()
_DEFAULT_TIMESCALE_HOST: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_CONSTS, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_DB", "upbit_trader")
_DEFAULT_REDIS_HOST: str = getattr(_CONSTS, "DEFAULT_REDIS_HOST", "127.0.0.1")
_DEFAULT_REDIS_PORT: int = getattr(_CONSTS, "DEFAULT_REDIS_PORT", 58530)


def _parse_iso(dt_str: str) -> datetime:
    """안정적인 ISO 파싱: 'Z'를 '+00:00'으로 변환 후 fromisoformat 사용"""
    if not dt_str:
        raise ValueError("empty datetime string")
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        # 최후수단: current UTC
        return datetime.now(timezone.utc)


class GapFillWorker:
    """
    GapFillWorker PoC

    Redis task 예시:
    {
      "symbol": "KRW-BTC",
      "timeframe": "1m",
      "start": "2026-02-20T00:00:00+00:00",   # optional
      "end": "2026-02-20T00:10:00+00:00",     # optional
      "approx_time": "2026-02-20T00:05:00+00:00",
      "priority": 100
    }
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_password: Optional[str] = None,
        pg_host: Optional[str] = None,
        pg_port: Optional[int] = None,
        pg_db: Optional[str] = None,
        pg_user: Optional[str] = None,
        pg_password: Optional[str] = None,
        upbit_base: str = UPBIT_BASE_DEFAULT,
    ) -> None:
        # Redis
        self.redis_host = redis_host or os.getenv("REDIS_HOST", _DEFAULT_REDIS_HOST)
        self.redis_port = int(redis_port or os.getenv("REDIS_PORT", str(_DEFAULT_REDIS_PORT)))
        self.redis_password = redis_password or os.getenv("REDIS_PASSWORD", None)

        # Postgres
        self.pg_host = pg_host or (
            os.getenv("TIMESCALE_HOST")
            or os.getenv("POSTGRES_HOST")
            or _DEFAULT_TIMESCALE_HOST
        )
        self.pg_port = int(pg_port or (
            os.getenv("TIMESCALE_PORT")
            or os.getenv("POSTGRES_PORT")
            or str(_DEFAULT_TIMESCALE_PORT)
        ))
        self.pg_db = pg_db or (
            os.getenv("TIMESCALE_DB")
            or os.getenv("POSTGRES_DB")
            or _DEFAULT_TIMESCALE_DB
        )
        self.pg_user = pg_user or (
            os.getenv("TIMESCALE_USER")
            or os.getenv("POSTGRES_USER")
            or _DEFAULT_TIMESCALE_USER
        )
        self.pg_password = pg_password or (
            os.getenv("TIMESCALE_PASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
            or ""
        )

        # Upbit
        self.upbit_base = upbit_base.rstrip("/")

        # clients
        self.redis: Any = None
        self.pg_pool: Any = None
        # 타입 힌트는 TYPE_CHECKING 블록에서 처리했으므로 안전하게 어노테이션 사용
        self.http: Optional["ClientSession"] = None  # type: ignore

        # control
        self._running = False

    async def initialize(self) -> None:
        if redis is None:
            raise RuntimeError("redis.asyncio or aioredis not available")
        self.redis = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            decode_responses=True,
        )
        await self.redis.ping()
        LOG.info("✅ GapFillWorker - Redis connected")

        if asyncpg is None:
            raise RuntimeError("asyncpg not available")
        self.pg_pool = await asyncpg.create_pool(
            host=self.pg_host,
            port=self.pg_port,
            database=self.pg_db,
            user=self.pg_user,
            password=self.pg_password,
            min_size=1,
            max_size=5,
        )
        LOG.info("✅ GapFillWorker - Postgres pool created")

        if aiohttp is None:
            raise RuntimeError("aiohttp not available")
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        LOG.info("✅ GapFillWorker - HTTP client ready")

    async def close(self) -> None:
        if self.http:
            try:
                await self.http.close()
            except Exception:
                pass
        if self.pg_pool:
            try:
                await self.pg_pool.close()
            except Exception:
                pass
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass

    async def run(self, poll_interval: float = 1.0) -> None:
        """메인 루프: gap_fill_queue에서 작업을 가져와 처리"""
        self._running = True
        LOG.info("▶ GapFillWorker started")
        try:
            while self._running:
                try:
                    raw = await self.redis.rpop("gap_fill_queue")
                    if not raw:
                        await asyncio.sleep(poll_interval)
                        continue

                    try:
                        task = json.loads(raw)
                    except Exception:
                        LOG.warning("malformed gap task, skipping")
                        continue

                    LOG.debug("Processing task (detailed): %s", task)
                    success = await self._process_task(task)
                    if not success:
                        LOG.warning("Requeueing task due to failure: %s", task)
                        await asyncio.sleep(1)
                        await self.redis.lpush("gap_fill_queue", json.dumps(task))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    LOG.exception("GapFillWorker main loop error: %s", e)
                    await asyncio.sleep(2)
        finally:
            LOG.info("◼ GapFillWorker stopped")

    async def _process_task(self, task: Dict[str, Any]) -> bool:
        """단일 task 처리"""
        symbol = task.get("symbol")
        timeframe = task.get("timeframe", "1m")
        approx = task.get("approx_time")
        start_iso = task.get("start")
        end_iso = task.get("end")

        if not symbol:
            LOG.error("Task missing symbol: %s", task)
            return True  # drop bad task

        # PoC: minute-based만 지원
        if not timeframe.endswith("m") and timeframe not in ("60m",):
            LOG.error("Unsupported timeframe for PoC: %s", timeframe)
            return True

        try:
            to_iso = end_iso or approx or datetime.now(timezone.utc).isoformat()
            LOG.debug("Task fetch window: start=%s end=%s to=%s", start_iso, end_iso, to_iso)
            candles = await self._fetch_candles_range(symbol, timeframe, to_iso, start_iso)
            LOG.debug("Fetched %d candles for %s %s", len(candles) if candles else 0, symbol, timeframe)
            if not candles:
                LOG.info("No candles returned from Upbit for task %s", task)
                return True

            inserted = await self._insert_into_staging(candles, symbol, timeframe)
            LOG.info("Inserted %d candles into staging for %s %s", inserted, symbol, timeframe)
            return True
        except Exception as e:
            LOG.exception("Task processing error: %s", e)
            return False

    async def _fetch_candles_range(self, symbol: str, timeframe: str, to_iso: str, start_iso: Optional[str]) -> List[Dict[str, Any]]:
        """
        'to' 기준으로 뒤로 가며 Upbit API에서 캔들 취득.
        결과는 oldest -> newest 순서로 반환.
        """
        # unit extraction: "1m" => 1
        unit = None
        try:
            if timeframe.endswith("m"):
                unit = int(timeframe[:-1])
            elif timeframe.endswith("h"):
                unit = int(timeframe[:-1]) * 60
        except Exception:
            unit = None

        if unit is None:
            LOG.error("Unsupported unit parsed from timeframe: %s", timeframe)
            return []

        all_chunks: List[Dict[str, Any]] = []

        to = to_iso
        headers = {"Accept": "application/json"}
        count = UPBIT_MAX_PER_REQUEST

        while True:
            url = "{}/v1/candles/minutes/{}".format(self.upbit_base, unit)
            params = {"market": symbol, "to": to, "count": count}
            LOG.debug("HTTP GET %s params=%s", url, params)
            try:
                async with self.http.get(url, params=params, headers=headers) as resp:
                    LOG.debug("Upbit response status=%s", resp.status)
                    if resp.status != 200:
                        text = await resp.text()
                        LOG.error("Upbit API error %s -> %s", resp.status, text)
                        raise RuntimeError("Upbit API {}: {}".format(resp.status, text))

                    chunk = await resp.json()
            except Exception as e:
                LOG.exception("HTTP request to Upbit failed: %s", e)
                raise

            if not chunk or not isinstance(chunk, list):
                LOG.debug("Upbit returned empty or non-list chunk: %s", chunk)
                break

            # Upbit returns newest-first for given 'to'; convert to oldest->newest for this batch
            batch = list(reversed(chunk))
            LOG.debug("Fetched batch size=%d (earliest=%s latest=%s)", len(batch), batch[0].get("candle_date_time_utc"), batch[-1].get("candle_date_time_utc"))
            all_chunks.extend(batch)

            # determine next 'to' based on earliest time in this batch
            earliest = batch[0].get("candle_date_time_utc") or batch[0].get("candle_date_time_kst")
            if not earliest:
                LOG.debug("No earliest timestamp in batch, stopping")
                break

            # If we have a start_iso and we've already fetched earlier-or-equal than start, we can stop
            if start_iso:
                try:
                    start_dt = _parse_iso(start_iso)
                    earliest_dt = _parse_iso(earliest)
                    if earliest_dt <= start_dt:
                        LOG.debug("Reached requested start (earliest_dt=%s <= start_dt=%s)", earliest_dt, start_dt)
                        break
                except Exception:
                    LOG.debug("Failed to parse start/earliest for comparison, continuing", exc_info=True)

            # prepare next to: earliest (Upbit returns candles strictly before or equal to 'to')
            to = earliest

            # polite sleep for rate-limit
            await asyncio.sleep(0.2)

            # if chunk smaller than requested count, we've reached beginning
            if len(chunk) < count:
                LOG.debug("Chunk smaller than count (%d < %d), stopping", len(chunk), count)
                break

        # Trim to start..end if start_iso provided
        if start_iso:
            try:
                start_dt = _parse_iso(start_iso)
                filtered = []
                for r in all_chunks:
                    ts = r.get("candle_date_time_utc") or r.get("candle_date_time_kst")
                    if not ts:
                        continue
                    try:
                        dt = _parse_iso(ts)
                        if dt >= start_dt:
                            filtered.append(r)
                    except Exception:
                        continue
                all_chunks = filtered
            except Exception:
                LOG.debug("Failed trimming by start_iso", exc_info=True)

        # Final sort to ensure oldest->newest
        def _ts_key(item: Dict[str, Any]) -> float:
            ts = item.get("candle_date_time_utc") or item.get("candle_date_time_kst")
            try:
                return _parse_iso(ts).timestamp()
            except Exception:
                return 0.0

        all_chunks.sort(key=_ts_key)
        LOG.debug("Total fetched candles after trim/sort: %d", len(all_chunks))
        return all_chunks

    async def _insert_into_staging(self, candles: List[Dict[str, Any]], symbol: str, timeframe: str) -> int:
        """Upbit 캔들 리스트를 staging_candles 스키마로 변환하여 bulk insert"""
        if not self.pg_pool:
            raise RuntimeError("No pg_pool")

        records: List[tuple] = []
        for c in candles:
            time_str = c.get("candle_date_time_utc") or c.get("candle_date_time_kst")
            try:
                time = _parse_iso(time_str)
            except Exception:
                time = datetime.now(timezone.utc)

            open_p = float(c.get("opening_price", c.get("open", 0)))
            high_p = float(c.get("high_price", c.get("high", 0)))
            low_p = float(c.get("low_price", c.get("low", 0)))
            close_p = float(c.get("trade_price", c.get("close", 0)))
            volume = float(c.get("candle_acc_trade_volume", c.get("candle_acc_trade_volume_24h", c.get("volume", 0))))
            seq = c.get("timestamp")  # surrogate
            trades = None
            received_at = datetime.now(timezone.utc)

            records.append((time, symbol, timeframe, open_p, high_p, low_p, close_p, volume, seq, trades, received_at))

        LOG.debug("Prepared %d records for staging insert", len(records))
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    res = await conn.copy_records_to_table(
                        "staging_candles",
                        records=records,
                        columns=[
                            "time", "symbol", "timeframe", "open", "high", "low", "close",
                            "volume", "seq", "trades", "received_at"
                        ]
                    )
                    if res:
                        # "COPY 123"
                        try:
                            inserted = int(str(res).split()[-1])
                        except Exception:
                            inserted = len(records)
                        LOG.debug("COPY result: %s -> inserted=%d", res, inserted)
                        return inserted
                    LOG.debug("COPY returned empty result, fallback to len(records)")
                    return len(records)
                except Exception as e:
                    LOG.exception("COPY failed, falling back to executemany: %s", e)
                    query = """
                        INSERT INTO staging_candles 
                        (time, symbol, timeframe, open, high, low, close, volume, seq, trades, received_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """
                    await conn.executemany(query, records)
                    LOG.debug("executemany inserted %d records", len(records))
                    return len(records)


async def main():
    # main에서도 DEBUG로 설정하여 전체 로그 보이게 함
    logging.basicConfig(level=logging.DEBUG)
    worker = GapFillWorker()
    await worker.initialize()
    try:
        await worker.run(poll_interval=0.5)
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())