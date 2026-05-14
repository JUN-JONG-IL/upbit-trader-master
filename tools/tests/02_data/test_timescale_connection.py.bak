"""
TimescaleDB 연결 및 CandleWriter 단위 테스트

테스트 범위:
    - CandleWriter 버퍼 관리 (upsert / flush / batch_size)
    - _to_row() 데이터 변환
    - pool이 None일 때 안전 동작
    - 배치 크기 초과 시 자동 플러시
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# src 및 src/02_data 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "02_data"))

from timescale.operations.candle_writer import CandleWriter, _to_row, BATCH_SIZE


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def _candle(symbol: str = "KRW-BTC", timeframe: str = "1m", **kwargs) -> Dict[str, Any]:
    """테스트용 캔들 dict"""
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    base = {
        "symbol": symbol,
        "timeframe": timeframe,
        "exchange": "upbit",
        "time": now,
        "open": 50000000.0,
        "high": 51000000.0,
        "low": 49000000.0,
        "close": 50500000.0,
        "volume": 10.5,
        "quote_volume": 525000000.0,
        "trade_count": 100,
        "is_complete": True,
        "seq": 1,
    }
    base.update(kwargs)
    return base


def _make_mock_pool():
    """asyncpg 연결 풀 Mock"""
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn),
                                                     __aexit__=AsyncMock(return_value=None)))
    return pool, conn


# ---------------------------------------------------------------------------
# _to_row() 변환 테스트
# ---------------------------------------------------------------------------

class TestToRow:
    def test_basic_conversion(self):
        """기본 캔들 dict를 올바른 튜플로 변환"""
        c = _candle()
        row = _to_row(c)
        assert isinstance(row, tuple)
        assert len(row) == 14
        assert row[1] == "KRW-BTC"    # symbol
        assert row[2] == "1m"          # timeframe
        assert row[3] == "upbit"       # exchange
        assert row[5] == 51000000.0    # high

    def test_timestamp_alias(self):
        """timestamp 키를 time으로 처리"""
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        c = {"timestamp": now, "symbol": "KRW-ETH", "timeframe": "5m",
             "exchange": "upbit", "open": 1, "high": 2, "low": 0.5, "close": 1.5,
             "volume": 1, "is_complete": False}
        row = _to_row(c)
        assert row[0] == now

    def test_interval_alias_for_timeframe(self):
        """interval 키를 timeframe으로 처리"""
        c = _candle()
        c.pop("timeframe")
        c["interval"] = "1h"
        row = _to_row(c)
        assert row[2] == "1h"

    def test_is_complete_bool(self):
        """is_complete는 bool로 변환"""
        c = _candle(is_complete=1)  # int -> bool
        row = _to_row(c)
        assert isinstance(row[11], bool)
        assert row[11] is True

    def test_meta_json(self):
        """meta dict는 JSON 문자열로 직렬화"""
        c = _candle(meta={"key": "value"})
        row = _to_row(c)
        assert row[13] is not None
        import json
        assert json.loads(row[13]) == {"key": "value"}

    def test_meta_none(self):
        """meta 없을 때 None"""
        c = _candle()
        row = _to_row(c)
        assert row[13] is None


# ---------------------------------------------------------------------------
# CandleWriter 테스트
# ---------------------------------------------------------------------------

class TestCandleWriter:
    def test_init_empty_buffer(self):
        """초기화 시 버퍼가 비어있음"""
        writer = CandleWriter(pool=None)
        assert writer.buffered_count == 0
        assert writer.total_upserted == 0

    @pytest.mark.asyncio
    async def test_upsert_accumulates_buffer(self):
        """upsert() 호출 시 버퍼에 캔들 추가"""
        writer = CandleWriter(pool=None, batch_size=10)
        for i in range(5):
            await writer.upsert(_candle())
        assert writer.buffered_count == 5

    @pytest.mark.asyncio
    async def test_flush_empty_returns_zero(self):
        """빈 버퍼 flush는 0 반환"""
        writer = CandleWriter(pool=None)
        result = await writer.flush()
        assert result == 0

    @pytest.mark.asyncio
    async def test_flush_without_pool_returns_zero(self):
        """pool이 None이면 flush는 0 반환"""
        writer = CandleWriter(pool=None, batch_size=10)
        for _ in range(5):
            await writer.upsert(_candle())
        result = await writer.flush()
        assert result == 0

    @pytest.mark.asyncio
    async def test_auto_flush_on_batch_size(self):
        """배치 크기 초과 시 자동 플러시 트리거"""
        pool, conn = _make_mock_pool()
        writer = CandleWriter(pool=pool, batch_size=3)

        for i in range(3):
            await writer.upsert(_candle())

        # 배치 크기에 도달하면 자동 플러시
        assert conn.executemany.called
        assert writer.total_upserted == 3

    @pytest.mark.asyncio
    async def test_upsert_batch_direct(self):
        """upsert_batch()는 버퍼 우회하여 즉시 저장"""
        pool, conn = _make_mock_pool()
        writer = CandleWriter(pool=pool)
        candles = [_candle() for _ in range(5)]
        count = await writer.upsert_batch(candles)
        assert count == 5
        assert conn.executemany.called

    @pytest.mark.asyncio
    async def test_upsert_batch_empty(self):
        """빈 목록은 0 반환"""
        pool, _ = _make_mock_pool()
        writer = CandleWriter(pool=pool)
        count = await writer.upsert_batch([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self):
        """flush 후 버퍼가 비워짐"""
        pool, conn = _make_mock_pool()
        writer = CandleWriter(pool=pool, batch_size=100)
        for _ in range(5):
            await writer.upsert(_candle())
        assert writer.buffered_count == 5
        flushed = await writer.flush()
        assert flushed == 5
        assert writer.buffered_count == 0

    @pytest.mark.asyncio
    async def test_total_upserted_accumulates(self):
        """total_upserted는 플러시마다 누적"""
        pool, _ = _make_mock_pool()
        writer = CandleWriter(pool=pool, batch_size=100)
        for _ in range(7):
            await writer.upsert(_candle())
        await writer.flush()
        for _ in range(3):
            await writer.upsert(_candle())
        await writer.flush()
        assert writer.total_upserted == 10

    @pytest.mark.asyncio
    async def test_db_error_returns_zero(self):
        """DB 오류 시 0 반환하고 예외 전파 안 함"""
        pool = MagicMock()
        conn = AsyncMock()
        conn.executemany = AsyncMock(side_effect=Exception("DB Error"))
        pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=conn),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        writer = CandleWriter(pool=pool, batch_size=100)
        for _ in range(3):
            await writer.upsert(_candle())
        result = await writer.flush()
        assert result == 0
