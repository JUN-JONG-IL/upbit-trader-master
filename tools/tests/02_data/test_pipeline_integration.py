"""
?뚯씠?꾨씪???듯빀 ?뚯뒪??

?뚯뒪??踰붿쐞:
    - DataCollector.receive() ??staging ?????Redis 媛깆떊 ??Kafka ?꾩넚
    - EventStore.append() / load() / load_by_type()
    - GapFiller.backfill() ??pool=None ?덉쟾 ?숈옉
    - KafkaProducer ?꾨찓??硫붿꽌??(send_candle, send_ticker ??
    - KafkaConsumer.consume_batch() ??aiokafka 誘몄꽕移????덉쟾 ?숈옉
    - MetadataManager.upsert_symbol() / get_active_symbols()
    - EventToMongo.project_event()
"""

from __future__ import annotations

import asyncio
import sys
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "data_01"))


# ---------------------------------------------------------------------------
# ?쎌뒪泥??ы띁
# ---------------------------------------------------------------------------

def _candle(**kw) -> Dict[str, Any]:
    base = {
        "symbol": "KRW-BTC",
        "timeframe": "1m",
        "exchange": "upbit",
        "time": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "open": 50000000.0,
        "high": 51000000.0,
        "low": 49000000.0,
        "close": 50500000.0,
        "volume": 5.0,
        "is_complete": True,
    }
    base.update(kw)
    return base


def _make_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={"next_ver": 1})
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return pool, conn


def _make_redis():
    r = AsyncMock()
    pipe = AsyncMock()
    pipe.zadd = AsyncMock()
    pipe.zremrangebyrank = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.lpush = AsyncMock()
    pipe.ltrim = AsyncMock()
    pipe.hset = AsyncMock()
    pipe.execute = AsyncMock(return_value=[1])
    r.pipeline = MagicMock(return_value=pipe)
    r.zadd = AsyncMock(return_value=1)
    r.zcard = AsyncMock(return_value=0)
    r.zpopmin = AsyncMock(return_value=[])
    r.zrevrange = AsyncMock(return_value=[])
    r.hgetall = AsyncMock(return_value={})
    r.lrange = AsyncMock(return_value=[])
    r.delete = AsyncMock(return_value=1)
    return r


# ---------------------------------------------------------------------------
# DataCollector ?듯빀 ?뚯뒪??
# ---------------------------------------------------------------------------

class TestDataCollector:
    @pytest.mark.asyncio
    async def test_receive_normalizes_upbit_format(self):
        """Upbit ?뺤떇???먯떆 ?곗씠?곕? ?쒖? 罹붾뱾濡?蹂??""
        from pipeline.collector import DataCollector

        pool, conn = _make_pool()
        redis = _make_redis()
        collector = DataCollector(pool=pool, redis_client=redis, batch_size=100)

        upbit_data = {
            "code": "KRW-BTC",
            "interval": "1m",
            "opening_price": 50000000,
            "high_price": 51000000,
            "low_price": 49000000,
            "trade_price": 50500000,
            "candle_acc_trade_volume": 10.5,
        }
        await collector.receive(upbit_data)
        assert collector._buffer[0]["symbol"] == "KRW-BTC"
        assert collector._buffer[0]["open"] == 50000000.0

    @pytest.mark.asyncio
    async def test_receive_triggers_flush_on_batch_size(self):
        """諛곗튂 ?ш린 ?꾨떖 ???먮룞 ?뚮윭??""
        from pipeline.collector import DataCollector

        pool, conn = _make_pool()
        collector = DataCollector(pool=pool, redis_client=None, batch_size=3)

        for _ in range(3):
            await collector.receive(_candle())

        # ?뚮윭????踰꾪띁媛 鍮꾩썙吏?
        assert len(collector._buffer) == 0

    @pytest.mark.asyncio
    async def test_receive_callback_invoked(self):
        """on_candle 肄쒕갚???몄텧??""
        from pipeline.collector import DataCollector

        received = []

        async def cb(c):
            received.append(c)

        collector = DataCollector(pool=None, redis_client=None, batch_size=10)
        collector.set_candle_callback(cb)
        await collector.receive(_candle())
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_flush_returns_count(self):
        """flush()??泥섎━??罹붾뱾 ?섎? 諛섑솚"""
        from pipeline.collector import DataCollector

        collector = DataCollector(pool=None, redis_client=None, batch_size=100)
        for _ in range(5):
            await collector.receive(_candle())
        count = await collector.flush()
        assert count == 5

    @pytest.mark.asyncio
    async def test_normalize_aliases(self):
        """code/interval 蹂꾩묶 ?뺤긽 泥섎━"""
        from pipeline.collector import DataCollector

        collector = DataCollector(pool=None, redis_client=None)
        raw = {"code": "KRW-ETH", "interval": "5m", "trade_price": 2000000}
        norm = DataCollector._normalize(raw)
        assert norm["symbol"] == "KRW-ETH"
        assert norm["timeframe"] == "5m"
        assert norm["close"] == 2000000.0


# ---------------------------------------------------------------------------
# EventStore ?⑥쐞 ?뚯뒪??
# ---------------------------------------------------------------------------

class TestEventStore:
    @pytest.mark.asyncio
    async def test_append_calls_execute(self):
        """append()??conn.execute瑜??몄텧"""
        from postgres.event_store import EventStore

        pool, conn = _make_pool()
        store = EventStore(pool)
        await store.append("order-001", "OrderCreated", {"symbol": "KRW-BTC"})
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_append_returns_stored_event(self):
        """append()??StoredEvent瑜?諛섑솚"""
        from postgres.event_store import EventStore, StoredEvent

        pool, conn = _make_pool()
        store = EventStore(pool)
        result = await store.append("order-002", "OrderFilled", {"qty": 1.0})
        assert isinstance(result, StoredEvent)
        assert result.aggregate_id == "order-002"
        assert result.event_type == "OrderFilled"

    @pytest.mark.asyncio
    async def test_append_no_pool_raises(self):
        """pool=None?대㈃ RuntimeError"""
        from postgres.event_store import EventStore

        store = EventStore(None)
        with pytest.raises(RuntimeError):
            await store.append("x", "OrderCreated", {})

    @pytest.mark.asyncio
    async def test_load_no_pool_returns_empty(self):
        """pool=None?대㈃ 鍮?紐⑸줉 諛섑솚"""
        from postgres.event_store import EventStore

        store = EventStore(None)
        result = await store.load("order-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_load_by_type_no_pool(self):
        """pool=None?대㈃ 鍮?紐⑸줉 諛섑솚"""
        from postgres.event_store import EventStore

        store = EventStore(None)
        result = await store.load_by_type("OrderCreated")
        assert result == []

    @pytest.mark.asyncio
    async def test_append_batch(self):
        """append_batch()???щ윭 ?대깽?몃? ?쒖꽌?濡????""
        from postgres.event_store import EventStore

        pool, conn = _make_pool()
        store = EventStore(pool)
        events = [
            {"aggregate_id": f"order-{i}", "event_type": "OrderCreated", "event_data": {"i": i}}
            for i in range(3)
        ]
        results = await store.append_batch(events)
        assert len(results) == 3
        assert conn.execute.call_count == 3

    def test_event_types_coverage(self):
        """EVENT_TYPES???듭떖 ?대깽???좏삎 ?ы븿"""
        from postgres.event_store import EVENT_TYPES

        for et in ("OrderCreated", "OrderFilled", "TradeExecuted", "BalanceUpdated"):
            assert et in EVENT_TYPES


# ---------------------------------------------------------------------------
# GapFiller ?⑥쐞 ?뚯뒪??
# ---------------------------------------------------------------------------

class TestGapFiller:
    @pytest.mark.asyncio
    async def test_backfill_no_pool(self):
        """pool=None?대㈃ 0 諛섑솚"""
        from pipeline.gap_filler import GapFiller

        filler = GapFiller(pool=None, redis_client=None)
        from datetime import timedelta
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)
        count = await filler.backfill("KRW-BTC", "1m", start, end)
        assert count == 0

    @pytest.mark.asyncio
    async def test_process_one_empty_queue(self):
        """?먭? 鍮꾩뼱?덉쑝硫?False 諛섑솚"""
        from pipeline.gap_filler import GapFiller

        redis = _make_redis()
        filler = GapFiller(pool=None, redis_client=redis)
        result = await filler.process_one()
        assert result is False

    @pytest.mark.asyncio
    async def test_process_one_no_redis(self):
        """redis=None?대㈃ False 諛섑솚"""
        from pipeline.gap_filler import GapFiller

        filler = GapFiller(pool=None, redis_client=None)
        result = await filler.process_one()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """start/stop???덉쇅 ?놁씠 ?숈옉"""
        from pipeline.gap_filler import GapFiller

        filler = GapFiller()
        await filler.start()
        assert filler._running is True
        await filler.stop()
        assert filler._running is False

    def test_parse_upbit_candle(self):
        """_parse_upbit_candle()???쒖? ?뺤떇?쇰줈 蹂??""
        from pipeline.gap_filler import GapFiller

        item = {
            "candle_date_time_utc": "2024-01-01T00:00:00",
            "opening_price": 50000000,
            "high_price": 51000000,
            "low_price": 49000000,
            "trade_price": 50500000,
            "candle_acc_trade_volume": 10.5,
            "candle_acc_trade_price": 525000000,
        }
        result = GapFiller._parse_upbit_candle(item, "KRW-BTC", "1m")
        assert result["symbol"] == "KRW-BTC"
        assert result["open"] == 50000000.0
        assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# MetadataManager ?⑥쐞 ?뚯뒪??
# ---------------------------------------------------------------------------

class TestMetadataManager:
    def _make_db(self):
        db = MagicMock()
        col = MagicMock()
        col.update_one = AsyncMock(return_value=MagicMock())
        col.find_one = AsyncMock(return_value=None)
        cursor = AsyncMock()
        cursor.to_list = AsyncMock(return_value=[])
        cursor.limit = MagicMock(return_value=cursor)
        col.find = MagicMock(return_value=cursor)
        db.__getitem__ = MagicMock(return_value=col)
        return db, col

    @pytest.mark.asyncio
    async def test_upsert_symbol_calls_update_one(self):
        """upsert_symbol()? update_one???몄텧"""
        from mongodb.metadata_manager import MetadataManager

        db, col = self._make_db()
        mgr = MetadataManager(db)
        result = await mgr.upsert_symbol("KRW-BTC", korean_name="鍮꾪듃肄붿씤")
        assert result is True
        col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_symbol_no_db(self):
        """db=None?대㈃ False 諛섑솚"""
        from mongodb.metadata_manager import MetadataManager

        mgr = MetadataManager(None)
        result = await mgr.upsert_symbol("KRW-BTC")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_symbols_empty(self):
        """to_list媛 鍮?紐⑸줉?대㈃ [] 諛섑솚"""
        from mongodb.metadata_manager import MetadataManager

        db, _ = self._make_db()
        mgr = MetadataManager(db)
        result = await mgr.get_active_symbols()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_symbol_no_db(self):
        """db=None?대㈃ None 諛섑솚"""
        from mongodb.metadata_manager import MetadataManager

        mgr = MetadataManager(None)
        result = await mgr.get_symbol("KRW-BTC")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_snapshot(self):
        """update_snapshot()? update_one???몄텧"""
        from mongodb.metadata_manager import MetadataManager

        db, col = self._make_db()
        mgr = MetadataManager(db)
        now = datetime.now(timezone.utc)
        result = await mgr.update_snapshot("KRW-BTC", "1m", now)
        assert result is True
        col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_snapshot_none(self):
        """?ㅻ깄???놁쑝硫?None 諛섑솚"""
        from mongodb.metadata_manager import MetadataManager

        db, _ = self._make_db()
        mgr = MetadataManager(db)
        result = await mgr.get_snapshot("KRW-BTC", "1m")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_favorites(self):
        """set_favorites()??update_one ?몄텧"""
        from mongodb.metadata_manager import MetadataManager

        db, col = self._make_db()
        mgr = MetadataManager(db)
        result = await mgr.set_favorites(["KRW-BTC", "KRW-ETH"])
        assert result is True

    @pytest.mark.asyncio
    async def test_get_favorites_no_db(self):
        """db=None?대㈃ 鍮?紐⑸줉 諛섑솚"""
        from mongodb.metadata_manager import MetadataManager

        mgr = MetadataManager(None)
        result = await mgr.get_favorites()
        assert result == []


# ---------------------------------------------------------------------------
# EventToMongo ?⑥쐞 ?뚯뒪??
# ---------------------------------------------------------------------------

class TestEventToMongo:
    def _make_db(self):
        db = MagicMock()
        col = AsyncMock()
        col.update_one = AsyncMock(return_value=MagicMock())
        db.__getitem__ = MagicMock(return_value=col)
        return db, col

    @pytest.mark.asyncio
    async def test_project_order_created(self):
        """OrderCreated ??orders_view update_one ?몄텧"""
        from pipeline.event_to_mongo import EventToMongo

        db, col = self._make_db()
        builder = EventToMongo(db=db)
        result = await builder.project_event(
            "OrderCreated",
            {"order_id": "ord-1", "symbol": "KRW-BTC", "side": "buy", "quantity": 0.1},
        )
        assert result is True
        col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_project_order_filled(self):
        """OrderFilled ??orders_view update_one ?몄텧"""
        from pipeline.event_to_mongo import EventToMongo

        db, col = self._make_db()
        builder = EventToMongo(db=db)
        result = await builder.project_event(
            "OrderFilled",
            {"order_id": "ord-1", "filled_qty": 0.1},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_project_trade_executed(self):
        """TradeExecuted ??trades_view update_one ?몄텧"""
        from pipeline.event_to_mongo import EventToMongo

        db, col = self._make_db()
        builder = EventToMongo(db=db)
        result = await builder.project_event(
            "TradeExecuted",
            {"trade_id": "trd-1", "order_id": "ord-1", "symbol": "KRW-BTC"},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_project_unknown_event(self):
        """?????녿뒗 ?대깽?몃뒗 True 諛섑솚 (臾댁떆)"""
        from pipeline.event_to_mongo import EventToMongo

        db, col = self._make_db()
        builder = EventToMongo(db=db)
        result = await builder.project_event("UnknownEvent", {})
        assert result is True

    @pytest.mark.asyncio
    async def test_project_no_db(self):
        """db=None?대㈃ True 諛섑솚 (?몃뱾???대??먯꽌 ?ㅽ궢)"""
        from pipeline.event_to_mongo import EventToMongo

        builder = EventToMongo(db=None)
        result = await builder.project_event("OrderCreated", {"order_id": "x"})
        assert result is True

