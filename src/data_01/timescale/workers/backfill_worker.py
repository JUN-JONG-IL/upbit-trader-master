#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
백필 워커 - 누락된 캔들 데이터 일괄 보충

역할:
- TimescaleDB의 candles에서 Gap 탐지
- Upbit REST API를 통해 누락 구간 복구
- GapFillWorker와 달리 Redis 없이 독립 실행 가능
"""
import asyncio
import importlib.util
import logging
import os
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import asyncpg
except Exception:
    asyncpg = None  # type: ignore

try:
    import aiohttp
except Exception:
    aiohttp = None  # type: ignore

from .gap_fill_worker import GapFillWorker

LOG = logging.getLogger("timescale.workers.backfill")

# ---------------------------------------------------------------------------
# constants.py 로드 (core 패키지명 Python 식별자 제한으로 직접 import 불가)
# ---------------------------------------------------------------------------
_CONST_PATH = Path(__file__).parents[3] / "core" / "config" / "constants.py"

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_backfill_consts", str(_CONST_PATH))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        LOG.debug("[backfill_worker] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()
_DEFAULT_TIMESCALE_HOST: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_CONSTS, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_CONSTS, "DEFAULT_TIMESCALE_DB", "upbit_trader")


class BackfillWorker:
    """
    백필 워커 - Redis 없이 DB에서 직접 Gap 탐지 후 보충.

    사용법:
        worker = BackfillWorker(symbols=["KRW-BTC"], timeframe="1m", days=7)
        await worker.initialize()
        await worker.run()
        await worker.close()
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframe: str = "1m",
        days: int = 7,
        pg_host: Optional[str] = None,
        pg_port: Optional[int] = None,
        pg_db: Optional[str] = None,
        pg_user: Optional[str] = None,
        pg_password: Optional[str] = None,
        upbit_base: str = "https://api.upbit.com",
    ):
        self.symbols = symbols or []
        self.timeframe = timeframe
        self.days = days
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
        self.upbit_base = upbit_base.rstrip("/")
        self.pg_pool: Any = None
        self.http: Any = None

    async def initialize(self):
        if asyncpg is None:
            raise RuntimeError("asyncpg not available")
        self.pg_pool = await asyncpg.create_pool(
            host=self.pg_host, port=self.pg_port,
            database=self.pg_db, user=self.pg_user,
            password=self.pg_password, min_size=1, max_size=5,
        )
        if aiohttp is None:
            raise RuntimeError("aiohttp not available")
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        LOG.info("✅ BackfillWorker 초기화 완료")

    async def close(self):
        if self.http:
            await self.http.close()
        if self.pg_pool:
            await self.pg_pool.close()

    async def run(self):
        """심볼 목록에 대해 Gap 탐지 및 백필 실행"""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.days)
        for symbol in self.symbols:
            LOG.info("🔄 백필 시작: %s %s (%d일)", symbol, self.timeframe, self.days)
            gaps = await self._detect_gaps(symbol, start, end)
            for gap_start, gap_end in gaps:
                await self._fill_gap(symbol, gap_start, gap_end)

    async def _detect_gaps(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[tuple]:
        """TimescaleDB에서 Gap 탐지"""
        if not self.pg_pool:
            return []
        try:
            async with self.pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT last_candle_time FROM latest_snapshot WHERE symbol=$1 AND timeframe=$2",
                    symbol, self.timeframe,
                )
                if not row or not row["last_candle_time"]:
                    return [(start, end)]
                last = row["last_candle_time"]
                if last < end - timedelta(minutes=2):
                    return [(last, end)]
        except Exception as e:
            LOG.error("Gap 탐지 실패: %s", e)
        return []

    async def _fill_gap(self, symbol: str, gap_start: datetime, gap_end: datetime):
        """단일 Gap 보충 (GapFillWorker 재사용)"""
        try:
            helper = GapFillWorker(
                pg_host=self.pg_host, pg_port=self.pg_port,
                pg_db=self.pg_db, pg_user=self.pg_user,
                pg_password=self.pg_password, upbit_base=self.upbit_base,
            )
            helper.pg_pool = self.pg_pool
            helper.http = self.http
            task = {
                "symbol": symbol, "timeframe": self.timeframe,
                "start": gap_start.isoformat(), "end": gap_end.isoformat(),
            }
            await helper._process_task(task)
            LOG.info("✅ Gap 보충 완료: %s %s~%s", symbol, gap_start, gap_end)
        except Exception as e:
            LOG.error("❌ Gap 보충 실패: %s - %s", symbol, e)


if __name__ == "__main__":
    async def _main():
        worker = BackfillWorker(symbols=["KRW-BTC"], days=1)
        await worker.initialize()
        try:
            await worker.run()
        finally:
            await worker.close()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
