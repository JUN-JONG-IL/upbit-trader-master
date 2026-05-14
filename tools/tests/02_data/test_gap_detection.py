"""
Gap Detection ?⑥쐞 ?뚯뒪??

?뚯뒪??踰붿쐞:
    - GapDetector.detect() ??媛??덉쓬/?놁쓬 ?먯젙
    - GapDetector._calc_priority() ???곗꽑?쒖쐞 怨꾩궛
    - GapDetector.enqueue() ??Redis ???깅줉
    - GapDetector.get_queue_length() ????湲몄씠 議고쉶
    - GapRange.to_dict() ??吏곷젹??
    - pool/redis = None?????덉쟾 ?숈옉
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "data_01"))

from timescale.operations.gap_detector import GapDetector, GapRange, _GAP_FACTOR, _TF_SECONDS


# ---------------------------------------------------------------------------
# ?쎌뒪泥?
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_pool(last_time: Optional[datetime] = None):
    """asyncpg Mock ??latest_snapshot 荑쇰━ 諛섑솚媛??ㅼ젙"""
    pool = MagicMock()
    conn = AsyncMock()
    if last_time is not None:
        conn.fetchrow = AsyncMock(return_value={"last_candle_time": last_time})
    else:
        conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return pool


def _make_redis(queue_length: int = 0):
    """Redis Mock"""
    redis = AsyncMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.zcard = AsyncMock(return_value=queue_length)
    return redis


# ---------------------------------------------------------------------------
# GapRange ?뚯뒪??
# ---------------------------------------------------------------------------

class TestGapRange:
    def test_gap_seconds(self):
        """gap_seconds()??start~end 李⑥씠(珥?瑜?諛섑솚"""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, end)
        assert gap.gap_seconds == 300.0

    def test_to_dict_keys(self):
        """to_dict()???꾩닔 ?ㅻ? 紐⑤몢 ?ы븿"""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        gap = GapRange("KRW-ETH", "5m", start, end, priority=2)
        d = gap.to_dict()
        for key in ("symbol", "timeframe", "start", "end", "priority", "gap_seconds"):
            assert key in d

    def test_to_dict_values(self):
        """to_dict() 媛?寃利?""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1h", start, end, priority=3)
        d = gap.to_dict()
        assert d["symbol"] == "KRW-BTC"
        assert d["timeframe"] == "1h"
        assert d["priority"] == 3
        assert d["gap_seconds"] == 3600.0

    def test_default_priority(self):
        """priority 湲곕낯媛믪? 5"""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, start)
        assert gap.priority == 5


# ---------------------------------------------------------------------------
# GapDetector._calc_priority() ?뚯뒪??
# ---------------------------------------------------------------------------

class TestCalcPriority:
    def test_priority_1_over_one_day(self):
        """1???댁긽 媛????곗꽑?쒖쐞 1 (理쒓퀬)"""
        delta = timedelta(days=2)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 1

    def test_priority_2_over_5h(self):
        """5?쒓컙 ?댁긽 媛????곗꽑?쒖쐞 2"""
        delta = timedelta(hours=6)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 2

    def test_priority_3_over_1h(self):
        """1?쒓컙 ?댁긽 媛????곗꽑?쒖쐞 3"""
        delta = timedelta(hours=2)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 3

    def test_priority_4_over_12m(self):
        """12遺??댁긽 媛????곗꽑?쒖쐞 4"""
        delta = timedelta(minutes=15)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 4

    def test_priority_5_small_gap(self):
        """?뚭퇋紐?媛????곗꽑?쒖쐞 5 (理쒖?)"""
        delta = timedelta(minutes=3)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 5


# ---------------------------------------------------------------------------
# GapDetector.detect() ?뚯뒪??
# ---------------------------------------------------------------------------

class TestGapDetectorDetect:
    @pytest.mark.asyncio
    async def test_no_snapshot_returns_empty(self):
        """?ㅻ깄?룹씠 ?놁쑝硫?鍮?紐⑸줉 諛섑솚"""
        pool = _make_pool(last_time=None)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_gap_returns_empty(self):
        """媛?씠 ?놁쑝硫?鍮?紐⑸줉 諛섑솚 (理쒓렐 ?곗씠??"""
        recent = _now() - timedelta(seconds=30)  # 30珥?????1m ??꾪봽?덉엫, gap_factor=10 湲곗? 誘몃떖
        pool = _make_pool(last_time=recent)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []

    @pytest.mark.asyncio
    async def test_gap_detected(self):
        """?ㅻ옒???ㅻ깄?룹씠硫?媛?媛먯?"""
        old_time = _now() - timedelta(hours=2)  # 2?쒓컙 ??
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert len(result) == 1
        assert result[0].symbol == "KRW-BTC"
        assert result[0].timeframe == "1m"
        assert result[0].gap_seconds > 0

    @pytest.mark.asyncio
    async def test_gap_priority_set(self):
        """媛먯???媛?쓽 priority??1~5 踰붿쐞"""
        old_time = _now() - timedelta(days=3)
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert 1 <= result[0].priority <= 5

    @pytest.mark.asyncio
    async def test_detect_all(self):
        """detect_all() ???щ윭 ?щ낵/??꾪봽?덉엫 議고빀 泥섎━.

        1m ??꾪봽?덉엫 threshold: 10 * 60s = 10遺?
        1h ??꾪봽?덉엫 threshold: 10 * 3600s = 10?쒓컙
        ??2?????ㅻ깄?룹씠硫?????꾪봽?덉엫 紐⑤몢 媛?媛먯? ??4 議고빀
        """
        old_time = _now() - timedelta(days=2)
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect_all(
            symbols=["KRW-BTC", "KRW-ETH"],
            timeframes=["1m", "1h"],
        )
        # 4 議고빀 (2 ?щ낵 횞 2 ??꾪봽?덉엫), 媛?媛?1媛?
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_no_pool_returns_empty(self):
        """pool=None?대㈃ 鍮?紐⑸줉 諛섑솚"""
        detector = GapDetector(None, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []


# ---------------------------------------------------------------------------
# GapDetector.enqueue() / get_queue_length() ?뚯뒪??
# ---------------------------------------------------------------------------

class TestGapDetectorEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_calls_zadd(self):
        """enqueue()??Redis zadd瑜??몄텧"""
        redis = _make_redis()
        detector = GapDetector(None, redis)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, end, priority=2)
        result = await detector.enqueue(gap)
        assert result is True
        redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_no_redis_returns_false(self):
        """redis=None?대㈃ False 諛섑솚"""
        detector = GapDetector(None, None)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, start)
        result = await detector.enqueue(gap)
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_all_returns_count(self):
        """enqueue_all()? ?깃났 ?섎? 諛섑솚"""
        redis = _make_redis()
        detector = GapDetector(None, redis)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gaps = [GapRange("KRW-BTC", "1m", start, start) for _ in range(3)]
        count = await detector.enqueue_all(gaps)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_queue_length(self):
        """get_queue_length()??zcard 寃곌낵瑜?諛섑솚"""
        redis = _make_redis(queue_length=7)
        detector = GapDetector(None, redis)
        length = await detector.get_queue_length()
        assert length == 7

    @pytest.mark.asyncio
    async def test_get_queue_length_no_redis(self):
        """redis=None?대㈃ 0 諛섑솚"""
        detector = GapDetector(None, None)
        length = await detector.get_queue_length()
        assert length == 0

    @pytest.mark.asyncio
    async def test_zadd_score_is_priority(self):
        """zadd??score 媛믪? gap.priority? ?쇱튂"""
        redis = _make_redis()
        detector = GapDetector(None, redis)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, end, priority=3)
        await detector.enqueue(gap)
        call_args = redis.zadd.call_args
        # zadd("gap_fill_queue", {value: score})
        mapping = call_args[0][1]
        scores = list(mapping.values())
        assert scores[0] == 3.0

