# -*- coding: utf-8 -*-
"""
TimescaleDB 데이터 갭 탐지기(GapFinder)

Responsibilities
- 시계열 데이터의 누락 구간 탐지 (플레이스홀더 구현)
- 탐지된 갭을 Redis ZSET 영구 큐 또는 인메모리 큐에 등록
- sync/async 진입점 제공
"""
from __future__ import annotations

import logging
import math
import threading
import asyncio as aio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Any, Deque, Tuple
from collections import deque
import os
import time

# module-level logger (rename to avoid shadowing parameter name)
_module_logger = logging.getLogger("timescale.operations.gap_finder")

# checker.py의 GapInfo를 우선 사용하고, 없으면 로컬 정의 사용.
try:
    from .checker import GapInfo as _CheckerGapInfo  # type: ignore
    GapInfo = _CheckerGapInfo  # re-export
except Exception:
    @dataclass
    class GapInfo:
        symbol: str
        timeframe: str
        gap_start: datetime
        gap_end: datetime
        priority: str = 'MEDIUM'  # ✅ str 타입으로 통일 ('HIGH', 'MEDIUM', 'LOW')


# -----------------------
# Redis ZSET 기반 큐 설정 (영구 저장, 무제한 용량)
# -----------------------
_REDIS_QUEUE_KEY = "gap_fill_queue"
_PRIORITY_WEIGHTS: Dict[str, int] = {
    'HIGH': 1000,
    'MEDIUM': 500,
    'LOW': 100,
}
_redis_client: Optional[Any] = None  # sync redis.Redis 클라이언트 (선택)
_redis_lock = threading.Lock()


def set_redis_client(client: Any) -> None:
    """Redis 동기 클라이언트를 등록하여 Gap을 Redis ZSET에 저장합니다.

    Args:
        client: redis.Redis 인스턴스 (sync). None이면 인메모리 큐 사용.
    """
    global _redis_client
    with _redis_lock:
        _redis_client = client
    _module_logger.info("[GapFinder] Redis ZSET 큐 활성화 (key=%s)", _REDIS_QUEUE_KEY)


def _calculate_gap_score(gap: GapInfo) -> float:
    """Gap 우선순위 점수 계산.

    점수 = priority_weight * log1p(gap_seconds)
    높을수록 먼저 처리됩니다.
    """
    gap_seconds = 0.0
    if hasattr(gap, 'gap_start') and hasattr(gap, 'gap_end') and gap.gap_start and gap.gap_end:
        try:
            delta = gap.gap_end - gap.gap_start
            gap_seconds = max(0.0, delta.total_seconds())
        except Exception:
            gap_seconds = 0.0
    priority_str = getattr(gap, 'priority', 'MEDIUM')
    if isinstance(priority_str, str):
        weight = _PRIORITY_WEIGHTS.get(priority_str.upper(), 500)
    else:
        try:
            weight = int(priority_str) if priority_str else 500
        except Exception:
            weight = 500
    return weight * math.log1p(gap_seconds)


def _make_redis_member_key(gap: GapInfo) -> str:
    """Redis ZSET 멤버 키 생성 (symbol|timeframe|gap_start_iso)."""
    start_iso = ""
    if gap.gap_start:
        try:
            start_iso = gap.gap_start.isoformat() if hasattr(gap.gap_start, "isoformat") else str(gap.gap_start)
        except Exception:
            start_iso = str(gap.gap_start)
    return f"{gap.symbol}|{gap.timeframe}|{start_iso}"


def _enqueue_to_redis_batch(client: Any, gaps: List[GapInfo]) -> int:
    """Redis ZSET에 Gap 등록 (NX 중복 방지) — 배치 처리.

    Returns:
        등록된 수(중복 제외)
    """
    if not gaps:
        return 0
    added = 0
    try:
        # prepare mapping for zadd
        mapping = {}
        for g in gaps:
            member_key = _make_redis_member_key(g)
            score = _calculate_gap_score(g)
            mapping[member_key] = score
        # attempt batch zadd NX; some redis versions accept mapping and nx param.
        # Use pipeline for older clients if needed.
        try:
            res = client.zadd(_REDIS_QUEUE_KEY, mapping, nx=True)
            # res may be number added
            try:
                added = int(res)
            except Exception:
                # some clients return dict or None; fallback to counting by checking membership is expensive; skip
                added = len(mapping)  # optimistic
        except TypeError:
            # fallback: iterate
            for member, score in mapping.items():
                try:
                    r = client.zadd(_REDIS_QUEUE_KEY, {member: score}, nx=True)
                    if r:
                        added += 1
                except Exception:
                    continue
    except Exception as exc:
        _module_logger.warning("[GapFinder] Redis batch zadd failed: %s", exc, exc_info=True)
    return added


# -----------------------
# In-memory backfill queue (thread-safe) with capacity control
# -----------------------
_backfill_queue: Deque[GapInfo] = deque()
_queue_lock = threading.Lock()

# 인메모리 큐 최대 크기 결정 (SSOT -> env -> 기본)
def _load_default_queue_size() -> int:
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        import sys as _sys
        _ps_path = (
            _pl.Path(__file__).resolve().parents[3]
            / "orchestrator"
            / "backfill"
            / "performance_settings.py"
        )
        _mod_key = "_gap_finder_perf_settings"
        _mod = _sys.modules.get(_mod_key)
        if _mod is None and _ps_path.exists():
            _spec = _ilu.spec_from_file_location(_mod_key, str(_ps_path))
            if _spec and _spec.loader:
                _mod = _ilu.module_from_spec(_spec)
                _sys.modules[_mod_key] = _mod
                _spec.loader.exec_module(_mod)
        get_cap = getattr(_mod, "get_gap_queue_capacity", None) if _mod else None
        if callable(get_cap):
            return int(get_cap())
    except Exception:
        pass
    try:
        return int(os.getenv("GAP_QUEUE_MAX_SIZE", "200000"))
    except Exception:
        return 200000


DEFAULT_MAX_QUEUE_SIZE: int = _load_default_queue_size()
_MAX_QUEUE_SIZE: int = DEFAULT_MAX_QUEUE_SIZE


def set_max_queue_size(n: int) -> None:
    """Set maximum allowed size for backfill queue (thread-safe)."""
    global _MAX_QUEUE_SIZE
    try:
        if n is None or int(n) <= 0:
            raise ValueError("max queue size must be positive")
        _MAX_QUEUE_SIZE = int(n)
        _module_logger.info("[GapFinder] max queue size set to %d", _MAX_QUEUE_SIZE)
    except Exception:
        _module_logger.exception("[GapFinder] set_max_queue_size failed")


def get_max_queue_size() -> int:
    """Return current configured maximum queue size."""
    return _MAX_QUEUE_SIZE


# Enqueue tuning params (environment)
GAP_ENQUEUE_BATCH_SIZE = max(1, int(os.getenv("GAP_ENQUEUE_BATCH_SIZE", "1000")))
GAP_ENQUEUE_PAUSE_SECONDS = float(os.getenv("GAP_ENQUEUE_PAUSE_SECONDS", "0.05"))
GAP_ENQUEUE_MAX_RETRIES = max(1, int(os.getenv("GAP_ENQUEUE_MAX_RETRIES", "5")))


def _enqueue_gaps(gaps: Iterable[GapInfo]) -> int:
    """Synchronous enqueue for compatibility (used by some sync callers).

    Uses blocking sleep on contention (synchronous path). Returns number enqueued.
    """
    global _redis_client
    with _redis_lock:
        redis_available = _redis_client is not None

    enqueued = 0
    dropped = 0
    gaps_list = list(gaps)

    if redis_available:
        # Redis mode: batch in chunks to avoid giant commands
        try:
            client = _redis_client
            for i in range(0, len(gaps_list), GAP_ENQUEUE_BATCH_SIZE):
                batch = gaps_list[i:i + GAP_ENQUEUE_BATCH_SIZE]
                added = _enqueue_to_redis_batch(client, batch)
                enqueued += added
            if enqueued:
                _module_logger.info("[GapFinder] Redis ZSET에 %d개 Gap 등록", enqueued)
            return enqueued
        except Exception as exc:
            _module_logger.warning("[GapFinder] Redis registration failed, falling back to in-memory: %s", exc, exc_info=True)
            # fall through to in-memory

    # In-memory fallback with blocking retry/backoff
    for g in gaps_list:
        retries = 0
        while True:
            with _queue_lock:
                if len(_backfill_queue) < _MAX_QUEUE_SIZE:
                    _backfill_queue.append(g)
                    enqueued += 1
                    break
            # queue full - retry with exponential backoff (blocking)
            if retries >= GAP_ENQUEUE_MAX_RETRIES:
                dropped += 1
                break
            sleep_time = GAP_ENQUEUE_PAUSE_SECONDS * (2 ** retries)
            time.sleep(sleep_time)
            retries += 1

    if enqueued:
        _module_logger.info("[GapFinder] Enqueued %d gap(s) to backfill queue", enqueued)
    if dropped:
        _module_logger.warning("[GapFinder] Dropped %d gap(s) due to queue capacity (%d)", dropped, _MAX_QUEUE_SIZE)
    return enqueued


async def _enqueue_gaps_async(gaps: Iterable[GapInfo]) -> int:
    """Async-aware enqueue used in async detection path. Uses await asyncio.sleep for backoff."""
    global _redis_client
    with _redis_lock:
        redis_available = _redis_client is not None

    enqueued = 0
    dropped = 0
    gaps_list = list(gaps)

    if redis_available:
        try:
            client = _redis_client
            for i in range(0, len(gaps_list), GAP_ENQUEUE_BATCH_SIZE):
                batch = gaps_list[i:i + GAP_ENQUEUE_BATCH_SIZE]
                added = _enqueue_to_redis_batch(client, batch)
                enqueued += added
                # small yield to event loop to avoid hogging CPU
                await aio.sleep(0)
            if enqueued:
                _module_logger.info("[GapFinder] Redis ZSET에 %d개 Gap 등록 (async)", enqueued)
            return enqueued
        except Exception as exc:
            _module_logger.warning("[GapFinder] Redis registration failed in async path, falling back to in-memory: %s", exc, exc_info=True)
            # fall through to in-memory

    # In-memory: use non-blocking await sleep for backoff
    for g in gaps_list:
        retries = 0
        while True:
            with _queue_lock:
                if len(_backfill_queue) < _MAX_QUEUE_SIZE:
                    _backfill_queue.append(g)
                    enqueued += 1
                    break
            # full -> wait asynchronously and retry
            if retries >= GAP_ENQUEUE_MAX_RETRIES:
                dropped += 1
                break
            sleep_time = GAP_ENQUEUE_PAUSE_SECONDS * (2 ** retries)
            await aio.sleep(sleep_time)
            retries += 1

    if enqueued:
        _module_logger.info("[GapFinder] Enqueued %d gap(s) to backfill queue (async)", enqueued)
    if dropped:
        _module_logger.warning("[GapFinder] Dropped %d gap(s) due to queue capacity (%d) (async)", dropped, _MAX_QUEUE_SIZE)
    return enqueued


def enqueue_gap(gap: GapInfo) -> bool:
    """
    Thread-safe enqueue of a single GapInfo. Returns True if enqueued, False if dropped.
    Redis 클라이언트가 설정된 경우 Redis ZSET을 사용합니다.
    """
    global _redis_client
    with _redis_lock:
        redis_available = _redis_client is not None

    if redis_available:
        added = _enqueue_to_redis_batch(_redis_client, [gap])
        if added:
            _module_logger.info("[GapFinder] Redis ZSET에 Gap 등록 (symbol=%s)", getattr(gap, "symbol", "<unknown>"))
        return bool(added)

    # 인메모리 폴백
    with _queue_lock:
        if len(_backfill_queue) >= _MAX_QUEUE_SIZE:
            _module_logger.warning("[GapFinder] enqueue_gap dropped gap for %s (queue full %d/%d)", getattr(gap, "symbol", "<unknown>"), len(_backfill_queue), _MAX_QUEUE_SIZE)
            return False
        _backfill_queue.append(gap)
        _module_logger.info("[GapFinder] Enqueued 1 gap to backfill queue (symbol=%s)", getattr(gap, "symbol", "<unknown>"))
        return True


def get_queue_length() -> int:
    """현재 큐 길이 반환 (Redis ZSET 또는 인메모리)."""
    global _redis_client
    with _redis_lock:
        client = _redis_client
    if client is not None:
        try:
            return client.zcard(_REDIS_QUEUE_KEY)
        except Exception:
            pass
    with _queue_lock:
        return len(_backfill_queue)


def peek_queue(n: int = 1) -> List[GapInfo]:
    """Return up to n items from the queue without removing them."""
    with _queue_lock:
        items = list(_backfill_queue)[: max(0, int(n))]
    return items


def pop_next() -> Optional[GapInfo]:
    """Pop the next GapInfo from the queue or None if empty."""
    with _queue_lock:
        if _backfill_queue:
            return _backfill_queue.popleft()
    return None


def clear_queue() -> int:
    """Clear the backfill queue entirely. Returns number of items removed."""
    with _queue_lock:
        removed = len(_backfill_queue)
        _backfill_queue.clear()
    if removed:
        _module_logger.info("[GapFinder] Cleared backfill queue, removed %d items", removed)
    return removed


def drain_queue(max_items: Optional[int] = None) -> List[GapInfo]:
    """
    Remove up to max_items from the queue and return them as a list.
    If max_items is None, drain the whole queue.
    """
    drained: List[GapInfo] = []
    with _queue_lock:
        if max_items is None:
            while _backfill_queue:
                drained.append(_backfill_queue.popleft())
        else:
            count = int(max_items)
            while _backfill_queue and count > 0:
                drained.append(_backfill_queue.popleft())
                count -= 1
    if drained:
        _module_logger.info("[GapFinder] Drained %d items from backfill queue", len(drained))
    return drained


# -----------------------
# Grace Period / Gap 설정 상수
# -----------------------
GRACE_PERIOD_SECONDS: int = int(os.getenv("GAP_GRACE_PERIOD_SECONDS", "300"))
MIN_GAP_THRESHOLD_SECONDS: int = int(os.getenv("GAP_MIN_THRESHOLD_SECONDS", "600"))
_TF_MINUTES: Dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}
_DEFAULT_COLLECTION_POLICY: Dict[str, Any] = {
    "timeframes": ["1m", "5m", "1h"],
    "limit_1m": 150000,
    "limit_5m": 50000,
    "limit_15m": 30000,
    "limit_1h": 12000,
    "limit_4h": 5000,
    "limit_1d": 500,
}
_MAX_LOOKBACK_DAYS = 3650


def _load_collection_policy_from_mongo() -> Dict[str, Any]:
    policy = dict(_DEFAULT_COLLECTION_POLICY)
    try:
        from pymongo import MongoClient

        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000, directConnection=True)
        try:
            db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
            doc = client[db_name]["ui_settings"].find_one({"user_id": "default"}) or {}
            col = doc.get("collection_settings", {})
            if isinstance(col, dict):
                tfs = col.get("timeframes")
                if isinstance(tfs, list) and tfs:
                    policy["timeframes"] = [str(tf) for tf in tfs if str(tf) in _TF_MINUTES]
                for tf in _TF_MINUTES:
                    key = f"limit_{tf}"
                    if key in col:
                        try:
                            policy[key] = int(col.get(key))
                        except Exception:
                            pass
        finally:
            client.close()
    except Exception as exc:
        _module_logger.debug("[GapFinder] collection_settings 로드 실패(기본값 사용): %s", exc)
    return policy


def _lookback_days_from_policy(policy: Dict[str, Any], timeframe: str) -> int:
    key = f"limit_{timeframe}"
    try:
        candles = int(policy.get(key, _DEFAULT_COLLECTION_POLICY.get(key, 0)))
    except Exception:
        candles = int(_DEFAULT_COLLECTION_POLICY.get(key, 0))
    candles = max(1, candles)
    tf_minutes = _TF_MINUTES.get(timeframe, 1)
    days = int(math.ceil((candles * tf_minutes) / 1440.0))
    return max(1, min(days, _MAX_LOOKBACK_DAYS))


# -----------------------
# GapFinder implementation
# -----------------------
class GapFinder:
    MAX_GAPS_PER_SYMBOL: int = 100
    MAX_GAPS_BATCH: int = 10000

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        grace_period_seconds: int = GRACE_PERIOD_SECONDS,
        min_gap_threshold_seconds: int = MIN_GAP_THRESHOLD_SECONDS,
        max_lookback_days: int = 7,
    ) -> None:
        self.logger = logger if logger is not None else _module_logger
        self.grace_period_seconds = grace_period_seconds
        self.min_gap_threshold_seconds = min_gap_threshold_seconds
        self.max_lookback_days = max_lookback_days

    @staticmethod
    def _load_timescale_connector() -> Any:
        try:
            import importlib.util as _ilu
            import pathlib as _pl
            _base = _pl.Path(__file__).resolve().parents[1]
            _ts_db_path = _base / "timescale_db.py"
            _mod = None
            if "_timescale_db" in __import__("sys").modules:
                _mod = __import__("sys").modules["_timescale_db"]
            elif _ts_db_path.exists():
                _spec = _ilu.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = _ilu.module_from_spec(_spec)
                    __import__("sys").modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            return getattr(_mod, "TimescaleConnector", None) if _mod else None
        except Exception:
            return None

    def _load_gap_settings_from_mongo(self) -> None:
        try:
            from pymongo import MongoClient
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000, directConnection=True)
            try:
                db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
                db = client[db_name]
                doc = db["gap_settings"].find_one({"_id": "default"})
                if doc:
                    self.grace_period_seconds = int(doc.get("grace_period_seconds", self.grace_period_seconds))
                    self.min_gap_threshold_seconds = int(doc.get("min_gap_threshold_seconds", self.min_gap_threshold_seconds))
                    _module_logger.debug(
                        "[GapFinder] gap_settings 로드 완료 (grace=%ds, min_threshold=%ds)",
                        self.grace_period_seconds, self.min_gap_threshold_seconds,
                    )
            finally:
                client.close()
        except Exception as e:
            _module_logger.debug("[GapFinder] gap_settings 조회 실패 (기본값 사용): %s", e)

    def _get_symbol_metadata(self, client, db_name: str, symbol: str) -> Optional[dict]:
        try:
            db = client[db_name]
            return db["metadata"].find_one({"symbol": symbol})
        except Exception as e:
            _module_logger.debug("[GapFinder] %s 메타데이터 조회 실패: %s", symbol, e)
            return None

    def _is_in_grace_period(self, symbol: str, metadata: Optional[dict], now: datetime) -> bool:
        if not metadata:
            return False
        created_at = metadata.get("created_at")
        if not created_at:
            return False
        try:
            if isinstance(created_at, datetime):
                created_dt = created_at
            else:
                s = str(created_at)
                try:
                    created_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                except ValueError:
                    import re as _re
                    s_norm = _re.sub(r"(\.\d{6})\d+", r"\1", s).replace("Z", "+00:00")
                    created_dt = datetime.fromisoformat(s_norm)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            elapsed = (now - created_dt).total_seconds()
            if elapsed < self.grace_period_seconds:
                _module_logger.info(
                    "[GapFinder] %s Grace Period 중 (생성 후 %.0f초, 유예: %ds)",
                    symbol, elapsed, self.grace_period_seconds,
                )
                return True
        except Exception as e:
            _module_logger.debug("[GapFinder] Grace Period 계산 실패 (%s): %s", symbol, e)
        return False

    async def find_gaps(
        self,
        symbols: Optional[Iterable[str]],
        interval: str = "1m",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[GapInfo]:
        now = datetime.now(timezone.utc)

        syms: List[str] = []
        mongo_client = None
        db_name = "upbit_trader"

        try:
            from pymongo import MongoClient
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
            db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
            mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000, directConnection=True)
        except Exception as e:
            _module_logger.debug("[GapFinder] MongoDB 연결 실패 (Grace Period 스킵): %s", e)
            mongo_client = None

        try:
            if symbols is None:
                if mongo_client is not None:
                    try:
                        db = mongo_client[db_name]
                        if "metadata" in db.list_collection_names():
                            coll = db["metadata"]
                            syms = [doc.get("symbol") for doc in coll.find({}, {"symbol": 1}) if doc.get("symbol")]
                            syms = sorted(set(syms))
                            _module_logger.debug(
                                "[GapFinder] find_gaps: 전체 심볼 %d개 로드 (interval=%s)", len(syms), interval
                            )
                        else:
                            _module_logger.warning("[GapFinder] MongoDB metadata 컬렉션 없음; 심볼 로드 불가")
                    except Exception as e:
                        _module_logger.warning("[GapFinder] MongoDB 심볼 로드 실패: %s", e)
                else:
                    _module_logger.warning("[GapFinder] MongoDB 미연결; 전체 심볼 로드 불가 (pymongo 설치 확인)")
            else:
                try:
                    syms = list(symbols)
                    _module_logger.debug("[GapFinder] find_gaps: %d개 심볼 (interval=%s)", len(syms), interval)
                except Exception:
                    syms = []

            symbols_to_check: List[str] = []
            symbol_priorities: Dict[str, int] = {}

            for symbol in syms:
                if mongo_client is not None:
                    metadata = self._get_symbol_metadata(mongo_client, db_name, symbol)
                    if self._is_in_grace_period(symbol, metadata, now):
                        continue
                    priority = int((metadata or {}).get("priority", 3))
                else:
                    priority = 3
                symbols_to_check.append(symbol)
                symbol_priorities[symbol] = priority

            gaps: List[GapInfo] = []

            if not symbols_to_check:
                _module_logger.info("[GapFinder] Grace Period 필터링 후 검사 대상 심볼 없음")
            else:
                raw_gaps = self.detect_gaps_for_all_symbols(
                    symbols=symbols_to_check,
                    timeframe=interval,
                    start_time=start_time,
                    end_time=end_time,
                )
                for g in raw_gaps:
                    gap_seconds = int(g.get("gap_seconds") or 0)
                    if gap_seconds < self.min_gap_threshold_seconds:
                        continue
                    gap_start = g.get("gap_start")
                    gap_end = g.get("gap_end")
                    symbol = g.get("symbol")
                    if gap_start is None or gap_end is None or symbol is None:
                        continue
                    if not isinstance(gap_start, datetime):
                        gap_start = datetime.fromisoformat(str(gap_start))
                    if gap_start.tzinfo is None:
                        gap_start = gap_start.replace(tzinfo=timezone.utc)
                    if not isinstance(gap_end, datetime):
                        gap_end = datetime.fromisoformat(str(gap_end))
                    if gap_end.tzinfo is None:
                        gap_end = gap_end.replace(tzinfo=timezone.utc)
                    _int_priority = symbol_priorities.get(symbol, 3)
                    _str_priority = 'HIGH' if _int_priority <= 2 else ('MEDIUM' if _int_priority == 3 else 'LOW')
                    gaps.append(GapInfo(
                        symbol=symbol,
                        timeframe=interval,
                        gap_start=gap_start,
                        gap_end=gap_end,
                        priority=_str_priority,
                    ))

        finally:
            if mongo_client is not None:
                try:
                    mongo_client.close()
                except Exception:
                    pass

        _module_logger.info(
            "[GapFinder] 갭 검출 완료: %d건 발견 (grace=%ds, min_threshold=%ds)",
            len(gaps), self.grace_period_seconds, self.min_gap_threshold_seconds,
        )
        return gaps

    def detect_gaps_for_symbol(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict]:
        TimescaleConnector = self._load_timescale_connector()

        if TimescaleConnector is None:
            _module_logger.warning("[GapFinder] TimescaleConnector 로드 실패 - Gap 검출 불가")
            return []

        try:
            conn = TimescaleConnector()
            if not conn.connect():
                _module_logger.warning("[GapFinder] TimescaleDB 연결 실패 - Gap 검출 불가")
                return []
        except Exception as e:
            _module_logger.warning("[GapFinder] TimescaleDB 연결 실패: %s", e)
            return []

        if not conn.conn or conn.conn.closed:
            _module_logger.warning("[GapFinder] TimescaleDB 연결 없음 - Gap 검출 불가")
            return []

        try:
            import psycopg2.extras as _pg_extras
            _RealDict = _pg_extras.RealDictCursor
        except Exception:
            _RealDict = None

        try:
            if end_time is None:
                end_time = datetime.now(timezone.utc)

            with conn.conn.cursor() as cur:
                cur.execute(
                    "SELECT MIN(time) AS first_time, MAX(time) AS last_time "
                    "FROM candles WHERE symbol = %s AND timeframe = %s",
                    (symbol, timeframe),
                )
                row = cur.fetchone()

            if not row or not row[0]:
                _module_logger.debug("[GapFinder] %s (%s): 데이터 없음 - Gap 검출 불가", symbol, timeframe)
                return []

            first_time = row[0]

            if start_time is None:
                start_time = first_time

            max_range = datetime.now(timezone.utc) - timedelta(days=self.max_lookback_days)
            if hasattr(start_time, "tzinfo"):
                _st = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
            else:
                _st = start_time
            if _st < max_range:
                start_time = max_range

            gap_query = """
                WITH time_gaps AS (
                    SELECT
                        symbol,
                        timeframe,
                        time AS gap_end,
                        LAG(time) OVER w AS gap_start,
                        EXTRACT(EPOCH FROM (time - LAG(time) OVER w)) AS gap_seconds
                    FROM candles
                    WHERE symbol = %s
                      AND timeframe = %s
                      AND time >= %s
                      AND time <= %s
                    WINDOW w AS (PARTITION BY symbol, timeframe ORDER BY time)
                )
                SELECT
                    symbol,
                    timeframe,
                    gap_start,
                    gap_end,
                    gap_seconds,
                    FLOOR(gap_seconds / 60) AS expected_candles
                FROM time_gaps
                WHERE gap_seconds > %s
                  AND gap_start IS NOT NULL
                ORDER BY gap_seconds DESC
                LIMIT %s
            """
            with conn.conn.cursor() as cur:
                cur.execute(gap_query, (symbol, timeframe, start_time, end_time, self.min_gap_threshold_seconds, self.MAX_GAPS_PER_SYMBOL))
                rows = cur.fetchall()

            gaps = []
            for r in rows:
                gaps.append({
                    "symbol": r[0],
                    "timeframe": r[1],
                    "gap_start": r[2],
                    "gap_end": r[3],
                    "gap_seconds": float(r[4]) if r[4] is not None else 0,
                    "expected_candles": int(r[5]) if r[5] is not None else 0,
                })

            _module_logger.info(
                "[GapFinder] %s (%s): %d개 Gap 검출 (범위: %s ~ %s)",
                symbol, timeframe, len(gaps),
                start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
                end_time.isoformat() if hasattr(end_time, "isoformat") else str(end_time),
            )
            return gaps

        except Exception as e:
            _module_logger.error("[GapFinder] %s (%s) Gap 검출 실패: %s", symbol, timeframe, e, exc_info=True)
            return []

    def detect_gaps_for_all_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1m",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict]:
        if not symbols:
            return []

        TimescaleConnector = self._load_timescale_connector()

        if TimescaleConnector is None:
            _module_logger.warning("[GapFinder] TimescaleConnector 로드 실패 - Gap 검출 불가")
            return []

        try:
            conn = TimescaleConnector()
            if not conn.connect():
                _module_logger.warning("[GapFinder] TimescaleDB 연결 실패 - Gap 검출 불가")
                return []
        except Exception as e:
            _module_logger.warning("[GapFinder] TimescaleDB 연결 실패: %s", e)
            return []

        if not conn.conn or conn.conn.closed:
            _module_logger.warning("[GapFinder] TimescaleDB 연결 없음 - Gap 검출 불가")
            return []

        try:
            if end_time is None:
                end_time = datetime.now(timezone.utc)

            if start_time is None:
                start_time = datetime.now(timezone.utc) - timedelta(days=self.max_lookback_days)

            max_range = datetime.now(timezone.utc) - timedelta(days=self.max_lookback_days)
            if hasattr(start_time, "tzinfo"):
                _st = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
            else:
                _st = start_time
            if _st < max_range:
                start_time = max_range

            gap_query = """
                WITH time_gaps AS (
                    SELECT
                        symbol,
                        timeframe,
                        time AS gap_end,
                        LAG(time) OVER w AS gap_start,
                        EXTRACT(EPOCH FROM (time - LAG(time) OVER w)) AS gap_seconds
                    FROM candles
                    WHERE symbol = ANY(%s)
                      AND timeframe = %s
                      AND time >= %s
                      AND time <= %s
                    WINDOW w AS (PARTITION BY symbol, timeframe ORDER BY time)
                )
                SELECT
                    symbol,
                    timeframe,
                    gap_start,
                    gap_end,
                    gap_seconds,
                    FLOOR(gap_seconds / 60) AS expected_candles
                FROM time_gaps
                WHERE gap_seconds > %s
                  AND gap_start IS NOT NULL
                ORDER BY symbol, gap_seconds DESC
                LIMIT %s
            """

            with conn.conn.cursor() as cur:
                cur.execute(
                    gap_query,
                    (
                        symbols,
                        timeframe,
                        start_time,
                        end_time,
                        self.min_gap_threshold_seconds,
                        self.MAX_GAPS_BATCH,
                    )
                )
                rows = cur.fetchall()

            if len(rows) >= self.MAX_GAPS_BATCH:
                _module_logger.warning(
                    "[GapFinder] 전체 심볼 Gap 검출 결과가 최대 한도(%d건)에 도달했습니다. "
                    "일부Gap이 누락되었을 수 있습니다.",
                    self.MAX_GAPS_BATCH,
                )

            gaps = []
            for r in rows:
                gaps.append({
                    "symbol": r[0],
                    "timeframe": r[1],
                    "gap_start": r[2],
                    "gap_end": r[3],
                    "gap_seconds": float(r[4]) if r[4] is not None else 0,
                    "expected_candles": int(r[5]) if r[5] is not None else 0,
                })

            _module_logger.info(
                "[GapFinder] 전체 심볼 Gap 검출: %d개 심볼, %d건 Gap (범위: %s ~ %s)",
                len(symbols), len(gaps),
                start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
                end_time.isoformat() if hasattr(end_time, "isoformat") else str(end_time),
            )
            return gaps

        except Exception as e:
            _module_logger.error("[GapFinder] 전체 심볼 Gap 검출 실패: %s", e, exc_info=True)
            return []

    def enqueue_gap_to_db(self, gap: Dict) -> bool:
        TimescaleConnector = self._load_timescale_connector()

        if TimescaleConnector is None:
            return False

        try:
            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return False

            with conn.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gap_fill_queue
                        (symbol, timeframe, gap_start, gap_end, gap_seconds, expected_candles, priority, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
                    ON CONFLICT (symbol, timeframe, gap_start, gap_end) DO NOTHING
                    """,
                    (
                        gap["symbol"],
                        gap.get("timeframe", "1m"),
                        gap["gap_start"],
                        gap["gap_end"],
                        gap["gap_seconds"],
                        gap.get("expected_candles", 0),
                        int(gap["gap_seconds"]),
                    ),
                )
            conn.conn.commit()

            _module_logger.info(
                "[GapFinder] Gap 등록: %s (%s ~ %s, %d초)",
                gap["symbol"], gap["gap_start"], gap["gap_end"], int(gap["gap_seconds"]),
            )
            return True
        except Exception as e:
            _module_logger.error("[GapFinder] Gap DB 등록 실패: %s", e)
            return False

    async def _detect_and_enqueue_async(
        self,
        symbols: Optional[Iterable[str]] = None,
        interval: str = "1m",
    ) -> int:
        try:
            if symbols is None:
                self.logger.debug("[GapFinder] async detect_and_enqueue start (symbols=ALL / None)")
                symbols_iter = None
            else:
                symbols_iter = list(symbols)
                self.logger.debug("[GapFinder] async detect_and_enqueue start (symbols=%d)", len(symbols_iter))

            gaps = await self.find_gaps(symbols_iter, interval=interval)
            if not gaps:
                self.logger.debug("[GapFinder] no gaps detected")
                return 0

            # ENQUEUE - use async-aware enqueue to avoid event loop blocking
            count = await _enqueue_gaps_async(gaps)

            # TimescaleDB insertion for gap_fill_queue table
            db_inserted = 0
            for gap in gaps:
                try:
                    gap_start = getattr(gap, "gap_start", None)
                    gap_end = getattr(gap, "gap_end", None)
                    gap_secs = 0.0
                    if gap_start is not None and gap_end is not None:
                        try:
                            gap_secs = (gap_end - gap_start).total_seconds()
                        except (TypeError, AttributeError) as _te:
                            self.logger.debug(
                                "[GapFinder] gap 시간 계산 실패 (symbol=%s): %s",
                                getattr(gap, "symbol", "?"), _te,
                            )
                            gap_secs = 0.0
                    gap_dict = {
                        "symbol": getattr(gap, "symbol", ""),
                        "timeframe": getattr(gap, "timeframe", "1m"),
                        "gap_start": gap_start,
                        "gap_end": gap_end,
                        "gap_seconds": gap_secs,
                        "expected_candles": 0,
                    }
                    if self.enqueue_gap_to_db(gap_dict):
                        db_inserted += 1
                except Exception:
                    pass

            if db_inserted:
                self.logger.info("[GapFinder] TimescaleDB gap_fill_queue에 %d건 등록", db_inserted)

            return count
        except Exception:
            try:
                self.logger.exception("[GapFinder] _detect_and_enqueue_async failed")
            except Exception:
                _module_logger.exception("[GapFinder] _detect_and_enqueue_async failed (logger fallback)")
            return 0

    def detect_and_enqueue(
        self,
        symbols: Optional[Iterable[str]] = None,
        interval: str = "1m",
    ) -> bool:
        try:
            symbols_iter = list(symbols) if symbols is not None else None

            try:
                loop = aio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                try:
                    if symbols_iter is None:
                        self.logger.debug("[GapFinder] scheduling background detect task (non-blocking) for ALL symbols")
                    else:
                        self.logger.debug("[GapFinder] scheduling background detect task (non-blocking) (symbols=%d)", len(symbols_iter))
                except Exception:
                    _module_logger.debug("[GapFinder] scheduling background detect task (non-blocking) (logger fallback)")
                coro = self._detect_and_enqueue_async(symbols_iter, interval=interval)
                try:
                    loop.create_task(coro)
                except Exception:
                    aio.ensure_future(coro)
                return True
            else:
                try:
                    if symbols_iter is None:
                        self.logger.debug("[GapFinder] running detect_and_enqueue synchronously (blocking) for ALL symbols")
                    else:
                        self.logger.debug("[GapFinder] running detect_and_enqueue synchronously (blocking) (symbols=%d)", len(symbols_iter))
                except Exception:
                    _module_logger.debug("[GapFinder] running detect_and_enqueue synchronously (blocking) (logger fallback)")
                count = aio.run(self._detect_and_enqueue_async(symbols_iter, interval=interval))
                try:
                    self.logger.info("[GapFinder] 갭 검출 완료 (%d건 발견)", count)
                except Exception:
                    _module_logger.info("[GapFinder] 갭 검출 완료 (%d건 발견)", count)
                return True
        except Exception:
            try:
                self.logger.exception("[GapFinder] detect_and_enqueue failed")
            except Exception:
                _module_logger.exception("[GapFinder] detect_and_enqueue failed (logger fallback)")
            return False

    def init_snapshots(self, symbol_codes: Optional[Iterable[str]] = None) -> None:
        """
        초기 스냅샷/검출 진입점 — UI 시작 시 호출될 수 있으므로 블로킹을 피하기 위해
        항상 백그라운드 데몬 스레드에서 detect_and_enqueue를 실행하도록 함.
        """
        try:
            try:
                self.logger.debug("[GapFinder] init_snapshots called (symbols=%s)", None if symbol_codes is None else "provided")
            except Exception:
                _module_logger.debug("[GapFinder] init_snapshots called (symbols=%s)", None if symbol_codes is None else "provided")

            def _worker():
                try:
                    # reuse existing detect_and_enqueue API (it will schedule async if loop exists)
                    self.detect_and_enqueue(symbols=symbol_codes)
                except Exception:
                    try:
                        aio.run(self._detect_and_enqueue_async(symbol_codes))
                    except Exception:
                        try:
                            self.logger.exception("[GapFinder] init_snapshots background run failed")
                        except Exception:
                            _module_logger.exception("[GapFinder] init_snapshots background run failed (logger fallback)")

            t = threading.Thread(target=_worker, daemon=True, name="GapFinder.init_snapshots")
            t.start()
            try:
                self.logger.debug("[GapFinder] init_snapshots started background thread")
            except Exception:
                _module_logger.debug("[GapFinder] init_snapshots started background thread")
        except Exception:
            try:
                self.logger.exception("[GapFinder] init_snapshots unexpected failure")
            except Exception:
                _module_logger.exception("[GapFinder] init_snapshots unexpected failure (logger fallback)")


# Module-level detection guard to avoid concurrent detect_all_and_enqueue runs
_detect_lock = threading.Lock()


def detect_all_and_enqueue() -> bool:
    """
    모듈 수준 진입점: 모든 심볼에 대해 갭 탐지 후 큐에 등록합니다.
    즉시 반환하고 실제 무거운 작업은 데몬 스레드에서 수행합니다.
    """
    log = logging.getLogger(__name__)
    log.info("[GapFinder] detect_all_and_enqueue called")

    # try to acquire without blocking; if already running, skip to avoid duplicate work
    acquired = _detect_lock.acquire(blocking=False)
    if not acquired:
        log.info("[GapFinder] detect_all_and_enqueue skipped because another run is in progress")
        return False

    def _run():
        try:
            finder = GapFinder(logger=log)
            finder._load_gap_settings_from_mongo()
            policy = _load_collection_policy_from_mongo()
            timeframes = policy.get("timeframes", ["1m", "5m", "1h"])
            if not isinstance(timeframes, list) or not timeframes:
                timeframes = ["1m", "5m", "1h"]

            all_ok = True
            for tf in timeframes:
                tf_key = str(tf)
                if tf_key not in _TF_MINUTES:
                    continue
                finder.max_lookback_days = _lookback_days_from_policy(policy, tf_key)
                log.info(
                    "[GapFinder] 설정 기반 점검: timeframe=%s, lookback_days=%d",
                    tf_key,
                    finder.max_lookback_days,
                )
                try:
                    ok = finder.detect_and_enqueue(symbols=None, interval=tf_key)
                    all_ok = all_ok and bool(ok)
                except Exception:
                    log.exception("[GapFinder] detect and enqueue failed for timeframe %s", tf_key)
                    all_ok = False
            log.info("[GapFinder] detect_all_and_enqueue worker finished (ok=%s)", all_ok)
        except Exception:
            log.exception("[GapFinder] detect_all_and_enqueue worker raised exception")
        finally:
            try:
                _detect_lock.release()
            except Exception:
                pass

    # 백그라운드 시작(데몬). 호출자는 즉시 반환.
    thread = threading.Thread(target=_run, name="GapFinder.detect_all_and_enqueue", daemon=True)
    thread.start()
    log.info("[GapFinder] detect_all_and_enqueue dispatched to background thread")
    return True


__all__ = [
    "GapFinder",
    "GapInfo",
    "detect_all_and_enqueue",
    "get_queue_length",
    "peek_queue",
    "pop_next",
    "enqueue_gap",
    "clear_queue",
    "drain_queue",
    "set_max_queue_size",
    "get_max_queue_size",
]