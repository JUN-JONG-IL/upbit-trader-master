"""
Gap Detection 단위 테스트

테스트 범위:
    - GapDetector.detect() — 갭 있음/없음 판정
    - GapDetector._calc_priority() — 우선순위 계산
    - GapDetector.enqueue() — Redis 큐 등록
    - GapDetector.get_queue_length() — 큐 길이 조회
    - GapRange.to_dict() — 직렬화
    - pool/redis = None일 때 안전 동작
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "02_data"))

from timescale.operations.gap_detector import GapDetector, GapRange, _GAP_FACTOR, _TF_SECONDS


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_pool(last_time: Optional[datetime] = None):
    """asyncpg Mock — latest_snapshot 쿼리 반환값 설정"""
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
# GapRange 테스트
# ---------------------------------------------------------------------------

class TestGapRange:
    def test_gap_seconds(self):
        """gap_seconds()는 start~end 차이(초)를 반환"""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, end)
        assert gap.gap_seconds == 300.0

    def test_to_dict_keys(self):
        """to_dict()는 필수 키를 모두 포함"""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        gap = GapRange("KRW-ETH", "5m", start, end, priority=2)
        d = gap.to_dict()
        for key in ("symbol", "timeframe", "start", "end", "priority", "gap_seconds"):
            assert key in d

    def test_to_dict_values(self):
        """to_dict() 값 검증"""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1h", start, end, priority=3)
        d = gap.to_dict()
        assert d["symbol"] == "KRW-BTC"
        assert d["timeframe"] == "1h"
        assert d["priority"] == 3
        assert d["gap_seconds"] == 3600.0

    def test_default_priority(self):
        """priority 기본값은 5"""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, start)
        assert gap.priority == 5


# ---------------------------------------------------------------------------
# GapDetector._calc_priority() 테스트
# ---------------------------------------------------------------------------

class TestCalcPriority:
    def test_priority_1_over_one_day(self):
        """1일 이상 갭 → 우선순위 1 (최고)"""
        delta = timedelta(days=2)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 1

    def test_priority_2_over_5h(self):
        """5시간 이상 갭 → 우선순위 2"""
        delta = timedelta(hours=6)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 2

    def test_priority_3_over_1h(self):
        """1시간 이상 갭 → 우선순위 3"""
        delta = timedelta(hours=2)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 3

    def test_priority_4_over_12m(self):
        """12분 이상 갭 → 우선순위 4"""
        delta = timedelta(minutes=15)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 4

    def test_priority_5_small_gap(self):
        """소규모 갭 → 우선순위 5 (최저)"""
        delta = timedelta(minutes=3)
        p = GapDetector._calc_priority(delta, interval_sec=60)
        assert p == 5


# ---------------------------------------------------------------------------
# GapDetector.detect() 테스트
# ---------------------------------------------------------------------------

class TestGapDetectorDetect:
    @pytest.mark.asyncio
    async def test_no_snapshot_returns_empty(self):
        """스냅샷이 없으면 빈 목록 반환"""
        pool = _make_pool(last_time=None)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_gap_returns_empty(self):
        """갭이 없으면 빈 목록 반환 (최근 데이터)"""
        recent = _now() - timedelta(seconds=30)  # 30초 전 — 1m 타임프레임, gap_factor=10 기준 미달
        pool = _make_pool(last_time=recent)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []

    @pytest.mark.asyncio
    async def test_gap_detected(self):
        """오래된 스냅샷이면 갭 감지"""
        old_time = _now() - timedelta(hours=2)  # 2시간 전
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert len(result) == 1
        assert result[0].symbol == "KRW-BTC"
        assert result[0].timeframe == "1m"
        assert result[0].gap_seconds > 0

    @pytest.mark.asyncio
    async def test_gap_priority_set(self):
        """감지된 갭의 priority는 1~5 범위"""
        old_time = _now() - timedelta(days=3)
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert 1 <= result[0].priority <= 5

    @pytest.mark.asyncio
    async def test_detect_all(self):
        """detect_all() — 여러 심볼/타임프레임 조합 처리.

        1m 타임프레임 threshold: 10 * 60s = 10분
        1h 타임프레임 threshold: 10 * 3600s = 10시간
        → 2일 전 스냅샷이면 두 타임프레임 모두 갭 감지 → 4 조합
        """
        old_time = _now() - timedelta(days=2)
        pool = _make_pool(last_time=old_time)
        detector = GapDetector(pool, None)
        result = await detector.detect_all(
            symbols=["KRW-BTC", "KRW-ETH"],
            timeframes=["1m", "1h"],
        )
        # 4 조합 (2 심볼 × 2 타임프레임), 각 갭 1개
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_no_pool_returns_empty(self):
        """pool=None이면 빈 목록 반환"""
        detector = GapDetector(None, None)
        result = await detector.detect("KRW-BTC", "1m")
        assert result == []


# ---------------------------------------------------------------------------
# GapDetector.enqueue() / get_queue_length() 테스트
# ---------------------------------------------------------------------------

class TestGapDetectorEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_calls_zadd(self):
        """enqueue()는 Redis zadd를 호출"""
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
        """redis=None이면 False 반환"""
        detector = GapDetector(None, None)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gap = GapRange("KRW-BTC", "1m", start, start)
        result = await detector.enqueue(gap)
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_all_returns_count(self):
        """enqueue_all()은 성공 수를 반환"""
        redis = _make_redis()
        detector = GapDetector(None, redis)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gaps = [GapRange("KRW-BTC", "1m", start, start) for _ in range(3)]
        count = await detector.enqueue_all(gaps)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_queue_length(self):
        """get_queue_length()는 zcard 결과를 반환"""
        redis = _make_redis(queue_length=7)
        detector = GapDetector(None, redis)
        length = await detector.get_queue_length()
        assert length == 7

    @pytest.mark.asyncio
    async def test_get_queue_length_no_redis(self):
        """redis=None이면 0 반환"""
        detector = GapDetector(None, None)
        length = await detector.get_queue_length()
        assert length == 0

    @pytest.mark.asyncio
    async def test_zadd_score_is_priority(self):
        """zadd의 score 값은 gap.priority와 일치"""
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
