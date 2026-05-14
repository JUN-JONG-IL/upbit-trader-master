"""
TimescaleDB ?곌껐 諛?CandleWriter ?⑥쐞 ?뚯뒪??

?뚯뒪??踰붿쐞:
    - CandleWriter 踰꾪띁 愿由?(upsert / flush / batch_size)
    - _to_row() ?곗씠??蹂??
    - pool??None?????덉쟾 ?숈옉
    - 諛곗튂 ?ш린 珥덇낵 ???먮룞 ?뚮윭??
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# src 諛?src/data_01 寃쎈줈 異붽?
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "data_01"))

from timescale.operations.candle_writer import CandleWriter, _to_row, BATCH_SIZE


# ---------------------------------------------------------------------------
# ?쎌뒪泥?
# ---------------------------------------------------------------------------

def _candle(symbol: str = "KRW-BTC", timeframe: str = "1m", **kwargs) -> Dict[str, Any]:
    """?뚯뒪?몄슜 罹붾뱾 dict"""
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
    """asyncpg ?곌껐 ? Mock"""
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn),
                                                     __aexit__=AsyncMock(return_value=None)))
    return pool, conn


# ---------------------------------------------------------------------------
# _to_row() 蹂???뚯뒪??
# ---------------------------------------------------------------------------

class TestToRow:
    def test_basic_conversion(self):
        """湲곕낯 罹붾뱾 dict瑜??щ컮瑜??쒗뵆濡?蹂??""
        c = _candle()
        row = _to_row(c)
        assert isinstance(row, tuple)
        assert len(row) == 14
        assert row[1] == "KRW-BTC"    # symbol
        assert row[2] == "1m"          # timeframe
        assert row[3] == "upbit"       # exchange
        assert row[5] == 51000000.0    # high

    def test_timestamp_alias(self):
        """timestamp ?ㅻ? time?쇰줈 泥섎━"""
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        c = {"timestamp": now, "symbol": "KRW-ETH", "timeframe": "5m",
             "exchange": "upbit", "open": 1, "high": 2, "low": 0.5, "close": 1.5,
             "volume": 1, "is_complete": False}
        row = _to_row(c)
        assert row[0] == now

    def test_interval_alias_for_timeframe(self):
        """interval ?ㅻ? timeframe?쇰줈 泥섎━"""
        c = _candle()
        c.pop("timeframe")
        c["interval"] = "1h"
        row = _to_row(c)
        assert row[2] == "1h"

    def test_is_complete_bool(self):
        """is_complete??bool濡?蹂??""
        c = _candle(is_complete=1)  # int -> bool
        row = _to_row(c)
        assert isinstance(row[11], bool)
        assert row[11] is True

    def test_meta_json(self):
        """meta dict??JSON 臾몄옄?대줈 吏곷젹??""
        c = _candle(meta={"key": "value"})
        row = _to_row(c)
        assert row[13] is not None
        import json
        assert json.loads(row[13]) == {"key": "value"}

    def test_meta_none(self):
        """meta ?놁쓣 ??None"""
        c = _candle()
        row = _to_row(c)
        assert row[13] is None


# ---------------------------------------------------------------------------
# CandleWriter ?뚯뒪??
# ---------------------------------------------------------------------------

class TestCandleWriter:
    def test_init_empty_buffer(self):
        """珥덇린????踰꾪띁媛 鍮꾩뼱?덉쓬"""
        writer = CandleWriter(pool=None)
        assert writer.buffered_count == 0
        assert writer.total_upserted == 0

    @pytest.mark.asyncio
    async def test_upsert_accumulates_buffer(self):
        """upsert() ?몄텧 ??踰꾪띁??罹붾뱾 異붽?"""
        writer = CandleWriter(pool=None, batch_size=10)
        for i in range(5):
            await writer.upsert(_candle())
        assert writer.buffered_count == 5

    @pytest.mark.asyncio
    async def test_flush_empty_returns_zero(self):
        """鍮?踰꾪띁 flush??0 諛섑솚"""
        writer = CandleWriter(pool=None)
        result = await writer.flush()
        assert result == 0

    @pytest.mark.asyncio
    async def test_flush_without_pool_returns_zero(self):
        """pool??None?대㈃ flush??0 諛섑솚"""
        writer = CandleWriter(pool=None, batch_size=10)
        for _ in range(5):
            await writer.upsert(_candle())
        result = await writer.flush()
        assert result == 0

    @pytest.mark.asyncio
    async def test_auto_flush_on_batch_size(self):
        """諛곗튂 ?ш린 珥덇낵 ???먮룞 ?뚮윭???몃━嫄?""
        pool, conn = _make_mock_pool()
        writer = CandleWriter(pool=pool, batch_size=3)

        for i in range(3):
            await writer.upsert(_candle())

        # 諛곗튂 ?ш린???꾨떖?섎㈃ ?먮룞 ?뚮윭??
        assert conn.executemany.called
        assert writer.total_upserted == 3

    @pytest.mark.asyncio
    async def test_upsert_batch_direct(self):
        """upsert_batch()??踰꾪띁 ?고쉶?섏뿬 利됱떆 ???""
        pool, conn = _make_mock_pool()
        writer = CandleWriter(pool=pool)
        candles = [_candle() for _ in range(5)]
        count = await writer.upsert_batch(candles)
        assert count == 5
        assert conn.executemany.called

    @pytest.mark.asyncio
    async def test_upsert_batch_empty(self):
        """鍮?紐⑸줉? 0 諛섑솚"""
        pool, _ = _make_mock_pool()
        writer = CandleWriter(pool=pool)
        count = await writer.upsert_batch([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self):
        """flush ??踰꾪띁媛 鍮꾩썙吏?""
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
        """total_upserted???뚮윭?쒕쭏???꾩쟻"""
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
        """DB ?ㅻ쪟 ??0 諛섑솚?섍퀬 ?덉쇅 ?꾪뙆 ????""
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

