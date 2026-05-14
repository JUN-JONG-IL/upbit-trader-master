"""
Redis CacheManager 단위 테스트

테스트 범위:
    - CacheManager.push_candle() / get_candles()
    - CacheManager.set_orderbook() / get_orderbook()
    - CacheManager.push_trade() / get_trades()
    - client=None일 때 안전 동작
    - Pipeline 배치 전송 (push_candle_batch)
    - invalidate()
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "02_data"))

from redis.cache_manager import (
    CacheManager,
    _candle_key,
    _orderbook_key,
    _trade_key,
    _dumps,
    _loads,
    _CANDLE_MAX,
    _ORDERBOOK_TTL,
    _TRADE_TTL,
    _CANDLE_TTL,
)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def _candle(symbol: str = "KRW-BTC", tf: str = "1m", ts: float = 1700000000.0) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": tf,
        "time": ts,
        "open": 50000000.0,
        "high": 51000000.0,
        "low": 49000000.0,
        "close": 50500000.0,
        "volume": 5.0,
    }


def _make_redis_mock():
    """Redis Pipeline 포함 asyncio Mock"""
    client = AsyncMock()
    pipe = AsyncMock()
    pipe.zadd = AsyncMock()
    pipe.zremrangebyrank = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.lpush = AsyncMock()
    pipe.ltrim = AsyncMock()
    pipe.hset = AsyncMock()
    pipe.execute = AsyncMock(return_value=[1, 0, 1])
    client.pipeline = MagicMock(return_value=pipe)
    client.zrevrange = AsyncMock(return_value=[])
    client.hgetall = AsyncMock(return_value={})
    client.lrange = AsyncMock(return_value=[])
    client.delete = AsyncMock(return_value=1)
    client.zcard = AsyncMock(return_value=0)
    return client, pipe


# ---------------------------------------------------------------------------
# 키 패턴 테스트
# ---------------------------------------------------------------------------

class TestKeyPatterns:
    def test_candle_key(self):
        assert _candle_key("KRW-BTC", "1m") == "candles:KRW-BTC:1m"

    def test_orderbook_key(self):
        assert _orderbook_key("KRW-ETH") == "orderbook:KRW-ETH"

    def test_trade_key(self):
        assert _trade_key("KRW-XRP") == "trade:KRW-XRP"


# ---------------------------------------------------------------------------
# 직렬화 테스트
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_dumps_loads_roundtrip(self):
        obj = {"symbol": "KRW-BTC", "close": 50000000.0, "nested": {"a": 1}}
        assert _loads(_dumps(obj)) == obj

    def test_dumps_returns_bytes(self):
        result = _dumps({"key": "value"})
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# CacheManager — None client
# ---------------------------------------------------------------------------

class TestCacheManagerNullClient:
    @pytest.mark.asyncio
    async def test_push_candle_no_client(self):
        cm = CacheManager(None)
        result = await cm.push_candle("KRW-BTC", "1m", _candle())
        assert result is False

    @pytest.mark.asyncio
    async def test_get_candles_no_client(self):
        cm = CacheManager(None)
        result = await cm.get_candles("KRW-BTC", "1m")
        assert result == []

    @pytest.mark.asyncio
    async def test_set_orderbook_no_client(self):
        cm = CacheManager(None)
        result = await cm.set_orderbook("KRW-BTC", {"bid": "50000000"})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_orderbook_no_client(self):
        cm = CacheManager(None)
        result = await cm.get_orderbook("KRW-BTC")
        assert result is None

    @pytest.mark.asyncio
    async def test_push_trade_no_client(self):
        cm = CacheManager(None)
        result = await cm.push_trade("KRW-BTC", {"price": 50000000})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_trades_no_client(self):
        cm = CacheManager(None)
        result = await cm.get_trades("KRW-BTC")
        assert result == []


# ---------------------------------------------------------------------------
# CacheManager — 캔들 캐시
# ---------------------------------------------------------------------------

class TestCandleCache:
    @pytest.mark.asyncio
    async def test_push_candle_uses_pipeline(self):
        """push_candle()은 pipeline zadd + zremrangebyrank + expire 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        result = await cm.push_candle("KRW-BTC", "1m", _candle())
        assert result is True
        pipe.zadd.assert_called_once()
        pipe.zremrangebyrank.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_candle_expire_value(self):
        """expire는 _CANDLE_TTL 값으로 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        await cm.push_candle("KRW-BTC", "1m", _candle())
        args, kwargs = pipe.expire.call_args
        assert _CANDLE_TTL in args or _CANDLE_TTL in kwargs.values()

    @pytest.mark.asyncio
    async def test_push_candle_batch(self):
        """push_candle_batch()는 여러 캔들을 파이프라인으로 처리"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        candles = [_candle(ts=float(i)) for i in range(5)]
        count = await cm.push_candle_batch("KRW-BTC", "1m", candles)
        assert count == 5
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_candle_batch_empty(self):
        """빈 목록은 0 반환"""
        client, _ = _make_redis_mock()
        cm = CacheManager(client)
        count = await cm.push_candle_batch("KRW-BTC", "1m", [])
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_candles_deserializes(self):
        """get_candles()는 zrevrange 결과를 역직렬화"""
        client, _ = _make_redis_mock()
        serialized = [_dumps(_candle())]
        client.zrevrange = AsyncMock(return_value=serialized)
        cm = CacheManager(client)
        result = await cm.get_candles("KRW-BTC", "1m")
        assert len(result) == 1
        assert result[0]["symbol"] == "KRW-BTC"

    @pytest.mark.asyncio
    async def test_get_candles_limit(self):
        """limit 파라미터가 zrevrange stop에 반영됨"""
        client, _ = _make_redis_mock()
        cm = CacheManager(client)
        await cm.get_candles("KRW-BTC", "1m", limit=50)
        client.zrevrange.assert_called_once_with("candles:KRW-BTC:1m", 0, 49)


# ---------------------------------------------------------------------------
# CacheManager — 호가 캐시
# ---------------------------------------------------------------------------

class TestOrderbookCache:
    @pytest.mark.asyncio
    async def test_set_orderbook_uses_pipeline(self):
        """set_orderbook()은 pipeline hset + expire 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        result = await cm.set_orderbook("KRW-BTC", {"bid": "50000000", "ask": "50100000"})
        assert result is True
        pipe.hset.assert_called_once()
        pipe.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_orderbook_ttl(self):
        """expire는 _ORDERBOOK_TTL(5초)로 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        await cm.set_orderbook("KRW-BTC", {"bid": "1"})
        args, _ = pipe.expire.call_args
        assert _ORDERBOOK_TTL in args

    @pytest.mark.asyncio
    async def test_get_orderbook_returns_dict(self):
        """get_orderbook()은 hgetall 결과 반환"""
        client, _ = _make_redis_mock()
        client.hgetall = AsyncMock(return_value={"bid": "50000000"})
        cm = CacheManager(client)
        result = await cm.get_orderbook("KRW-BTC")
        assert result == {"bid": "50000000"}

    @pytest.mark.asyncio
    async def test_get_orderbook_empty_returns_none(self):
        """hgetall이 빈 dict 반환하면 None"""
        client, _ = _make_redis_mock()
        client.hgetall = AsyncMock(return_value={})
        cm = CacheManager(client)
        result = await cm.get_orderbook("KRW-BTC")
        assert result is None


# ---------------------------------------------------------------------------
# CacheManager — 체결 캐시
# ---------------------------------------------------------------------------

class TestTradeCache:
    @pytest.mark.asyncio
    async def test_push_trade_uses_pipeline(self):
        """push_trade()는 lpush + ltrim + expire 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        result = await cm.push_trade("KRW-BTC", {"price": 50000000, "volume": 0.1})
        assert result is True
        pipe.lpush.assert_called_once()
        pipe.ltrim.assert_called_once()
        pipe.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_trade_ttl(self):
        """expire는 _TRADE_TTL(300초)로 호출"""
        client, pipe = _make_redis_mock()
        cm = CacheManager(client)
        await cm.push_trade("KRW-BTC", {"price": 1})
        args, _ = pipe.expire.call_args
        assert _TRADE_TTL in args

    @pytest.mark.asyncio
    async def test_get_trades_deserializes(self):
        """get_trades()는 lrange 결과를 역직렬화"""
        client, _ = _make_redis_mock()
        trade = {"price": 50000000, "volume": 0.5}
        client.lrange = AsyncMock(return_value=[_dumps(trade)])
        cm = CacheManager(client)
        result = await cm.get_trades("KRW-BTC")
        assert len(result) == 1
        assert result[0]["price"] == 50000000


# ---------------------------------------------------------------------------
# CacheManager — invalidate
# ---------------------------------------------------------------------------

class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_orderbook_and_trade(self):
        """timeframe 없이 호출하면 orderbook + trade 키 삭제"""
        client, _ = _make_redis_mock()
        cm = CacheManager(client)
        await cm.invalidate("KRW-BTC")
        client.delete.assert_called_once()
        args = client.delete.call_args[0]
        assert "orderbook:KRW-BTC" in args
        assert "trade:KRW-BTC" in args

    @pytest.mark.asyncio
    async def test_invalidate_candle_key(self):
        """timeframe 지정 시 캔들 키만 삭제"""
        client, _ = _make_redis_mock()
        cm = CacheManager(client)
        await cm.invalidate("KRW-BTC", "1m")
        client.delete.assert_called_once_with("candles:KRW-BTC:1m")

    @pytest.mark.asyncio
    async def test_invalidate_no_client(self):
        """client=None이면 아무 동작 없음"""
        cm = CacheManager(None)
        await cm.invalidate("KRW-BTC")  # 예외 없이 통과
