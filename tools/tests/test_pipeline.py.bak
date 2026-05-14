"""
tools/tests/test_pipeline.py
데이터 수집 파이프라인 단위 테스트

스코프:
    - CandleValidator (OHLC, volume, gap 검증)
    - CandleStager    (버퍼링 및 플러시)
    - CandlesFinalizer (UPSERT 로직)
    - RedisClient     (캐시 키 패턴)
    - GapDetector     (Gap 큐잉)
    - PipelineMonitor (메트릭 수집)
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# src 및 src/02_data 디렉터리를 패스에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "02_data"))

from pipeline.validator import (
    CandleValidator,
    GapExceededException,
    ValidationError,
)
from pipeline.monitor  import PipelineMonitor
from pipeline.checker  import CandleChecker


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
def _make_candle(
    symbol: str = "KRW-BTC",
    timeframe: str = "1m",
    dt: datetime = None,
    **kwargs,
) -> dict:
    """테스트용 캔들 dict를 생성합니다."""
    if dt is None:
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    base = {
        "time":         dt,
        "symbol":       symbol,
        "timeframe":    timeframe,
        "exchange":     "upbit",
        "open":         50_000_000.0,
        "high":         51_000_000.0,
        "low":          49_000_000.0,
        "close":        50_500_000.0,
        "volume":       100.0,
        "quote_volume": 5_000_000_000.0,
        "trade_count":  200,
        "is_complete":  True,
        "seq":          None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# CandleValidator 테스트
# ---------------------------------------------------------------------------
class TestCandleValidator:

    def setup_method(self):
        self.v = CandleValidator()

    def test_valid_candle_passes(self):
        c = _make_candle()
        self.v.validate(c)  # 예외 없어야 함

    def test_high_less_than_low_raises(self):
        c = _make_candle(high=49_000_000.0, low=51_000_000.0)
        with pytest.raises(ValidationError):
            self.v.validate_ohlc(c)

    def test_high_less_than_open_raises(self):
        c = _make_candle(open=52_000_000.0, high=51_000_000.0, low=49_000_000.0, close=50_000_000.0)
        with pytest.raises(ValidationError):
            self.v.validate_ohlc(c)

    def test_high_less_than_close_raises(self):
        c = _make_candle(close=52_000_000.0)
        with pytest.raises(ValidationError):
            self.v.validate_ohlc(c)

    def test_low_greater_than_open_raises(self):
        c = _make_candle(open=48_000_000.0, low=49_000_000.0)
        with pytest.raises(ValidationError):
            self.v.validate_ohlc(c)

    def test_negative_volume_raises(self):
        c = _make_candle(volume=-1.0)
        with pytest.raises(ValidationError):
            self.v.validate_volume(c)

    def test_negative_quote_volume_raises(self):
        c = _make_candle(quote_volume=-100.0)
        with pytest.raises(ValidationError):
            self.v.validate_volume(c)

    def test_gap_within_threshold_passes(self):
        last = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c    = _make_candle(dt=last + timedelta(minutes=2))
        self.v.validate_gap(c, last, "1m")  # 예외 없어야 함

    def test_gap_exceeds_threshold_raises(self):
        last = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 1분봉에서 11분 Gap → 10배 초과
        c    = _make_candle(dt=last + timedelta(minutes=11))
        with pytest.raises(GapExceededException) as exc_info:
            self.v.validate_gap(c, last, "1m")
        assert exc_info.value.gap_seconds > 0

    def test_gap_exception_carries_metadata(self):
        last = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c    = _make_candle(dt=last + timedelta(hours=2))
        with pytest.raises(GapExceededException) as exc_info:
            self.v.validate_gap(c, last, "1m")
        exc = exc_info.value
        assert exc.symbol    == "KRW-BTC"
        assert exc.timeframe == "1m"
        assert exc.gap_seconds > 0


# ---------------------------------------------------------------------------
# PipelineMonitor 테스트
# ---------------------------------------------------------------------------
class TestPipelineMonitor:

    def test_counters_start_at_zero(self):
        m = PipelineMonitor()
        snap = m.snapshot()
        assert snap["received"]   == 0
        assert snap["finalized"]  == 0
        assert snap["errors"]     == 0

    def test_inc_received(self):
        m = PipelineMonitor()
        m.inc_received()
        m.inc_received()
        assert m.snapshot()["received"] == 2

    def test_inc_errors(self):
        m = PipelineMonitor()
        m.inc_errors()
        assert m.snapshot()["errors"] == 1

    def test_measure_records_latency(self):
        import time
        m = PipelineMonitor()
        with m.measure():
            time.sleep(0.01)
        assert m.snapshot()["last_latency_ms"] >= 0


# ---------------------------------------------------------------------------
# CandleChecker 테스트
# ---------------------------------------------------------------------------
class TestCandleChecker:

    def test_l0_cache_miss_returns_none(self):
        checker = CandleChecker()
        assert checker.check_l0("KRW-BTC", "1m") is None

    def test_l0_cache_hit_returns_time(self):
        checker = CandleChecker()
        t = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        checker.update_l0("KRW-BTC", "1m", t)
        assert checker.check_l0("KRW-BTC", "1m") == t

    def test_get_missing_ranges_no_gap(self):
        checker = CandleChecker()
        last    = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now     = last + timedelta(seconds=30)
        ranges  = checker.get_missing_ranges(last, now, "1m")
        assert ranges == []

    def test_get_missing_ranges_with_gap(self):
        checker = CandleChecker()
        last    = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now     = last + timedelta(minutes=10)
        ranges  = checker.get_missing_ranges(last, now, "1m")
        assert len(ranges) == 1
        assert ranges[0][0] == last
        assert ranges[0][1] == now


# ---------------------------------------------------------------------------
# CandleStager 테스트 (Mock Pool)
# ---------------------------------------------------------------------------
class TestCandleStager:

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_returns_zero(self):
        from pipeline.stager import CandleStager
        pool = AsyncMock()
        stager = CandleStager(pool)
        count = await stager.flush()
        assert count == 0
        pool.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_and_flush(self):
        from pipeline.stager import CandleStager
        pool = AsyncMock()
        stager = CandleStager(pool)
        await stager.add_candle(_make_candle())
        assert stager.pending_count() == 1
        count = await stager.flush()
        assert count == 1
        pool.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_flush_on_batch_size(self):
        from pipeline.stager import CandleStager, BATCH_SIZE
        pool = AsyncMock()
        stager = CandleStager(pool)
        for i in range(BATCH_SIZE):
            await stager.add_candle(_make_candle())
        # BATCH_SIZE 에 도달하면 자동 flush → 버퍼가 비워짐
        assert stager.pending_count() == 0
        pool.executemany.assert_called_once()


# ---------------------------------------------------------------------------
# CandlesFinalizer 테스트 (Mock Pool)
# ---------------------------------------------------------------------------
class TestCandlesFinalizer:

    @pytest.mark.asyncio
    async def test_upsert_candles_calls_executemany(self):
        from pipeline.finalizer import CandlesFinalizer
        pool = AsyncMock()
        finalizer = CandlesFinalizer(pool)
        candles   = [_make_candle(), _make_candle(symbol="KRW-ETH")]
        count     = await finalizer.upsert_candles(candles)
        assert count == 2
        pool.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_empty_list_returns_zero(self):
        from pipeline.finalizer import CandlesFinalizer
        pool = AsyncMock()
        finalizer = CandlesFinalizer(pool)
        count = await finalizer.upsert_candles([])
        assert count == 0
        pool.executemany.assert_not_called()


# ---------------------------------------------------------------------------
# CacheHydrator 테스트 (Mock)
# ---------------------------------------------------------------------------
class TestCacheHydrator:

    @pytest.mark.asyncio
    async def test_hydrate_empty_returns_zero(self):
        from pipeline.hydrate import CacheHydrator
        pool  = AsyncMock()
        pool.fetch = AsyncMock(return_value=[])
        redis = AsyncMock()
        hydrator = CacheHydrator(pool, redis)
        count = await hydrator.hydrate("KRW-BTC", "1m")
        assert count == 0

    @pytest.mark.asyncio
    async def test_hydrate_calls_pipeline(self):
        from pipeline.hydrate import CacheHydrator
        pool  = AsyncMock()
        # asyncpg Record를 dict로 흉내
        pool.fetch = AsyncMock(return_value=[
            {"time": datetime(2024,1,1, tzinfo=timezone.utc),
             "symbol": "KRW-BTC", "timeframe": "1m", "exchange": "upbit",
             "open": 1, "high": 2, "low": 0.5, "close": 1.5,
             "volume": 10, "quote_volume": 20, "trade_count": 5,
             "is_complete": True, "seq": None}
        ])
        pipe_mock = MagicMock()
        pipe_mock.lpush  = MagicMock()
        pipe_mock.ltrim  = MagicMock()
        pipe_mock.expire = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=None)
        redis = AsyncMock()
        redis.pipeline = MagicMock(return_value=pipe_mock)
        hydrator = CacheHydrator(pool, redis)
        count = await hydrator.hydrate("KRW-BTC", "1m")
        assert count == 1
        pipe_mock.lpush.assert_called_once()
