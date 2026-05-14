# -*- coding: utf-8 -*-
"""백필 성능 설정 SSOT (Single Source of Truth) 모듈.

[책임]
    AutoBackfill / AutoBackfillManager 가 사용하는 성능 튜닝 파라미터를
    한 곳(`MongoDB ui_settings.backfill_scheduler.performance`)에서 읽어와
    호출자에게 제공한다. UI 다이얼로그(BackfillSchedulerSettingsDialog)와
    백필 실행 코드의 **단일 진실 공급원** 역할.

[키]
    backfill_scheduler.performance.max_concurrency      int  1~32   (기본 12)
    backfill_scheduler.performance.max_gaps_per_cycle   int  50~2000(기본 200)
    backfill_scheduler.performance.max_pages_per_gap    int  10~500 (기본 100)

[폴백 우선순위]
    1) MongoDB ui_settings.backfill_scheduler.performance.*  (60초 캐시)
    2) 환경변수 (AUTO_BACKFILL_MAX_CONCURRENCY 등 기존 호환)
    3) 정적 기본값

[설계 원칙]
    - import 시 부작용 없음 (DB 연결 X)
    - 모든 함수는 호출 시 캐시된 dict 반환 또는 새로 로드
    - DB 실패 시에도 항상 안전한 정수값 반환 (None 반환 금지)
    - 호출 빈도가 낮으므로(사이클당 1회) 성능 부담 미미
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# 정적 기본값 / 허용 범위 — UI 다이얼로그와 동기화 유지 필수
# ──────────────────────────────────────────────────────────────────────
_DEFAULTS: Dict[str, int] = {
    "max_concurrency": 12,
    "max_gaps_per_cycle": 200,
    "max_pages_per_gap": 100,
    # ── REST 수집기 / 글로벌 Rate Limiter SSOT ──
    "rest_max_concurrent": 8,        # RestCandleCollector 동시 요청 수
    "rest_rate_per_second": 9,       # AsyncRateLimiter 초당 한도 (Upbit 10 안전마진)
    "rest_rate_per_minute": 550,     # AsyncRateLimiter 분당 한도 (Upbit 600 안전마진)
    # ── GapFinder 인메모리 큐 용량 ──
    # Redis 미가용 시 폴백 deque 의 최대 크기. 256심볼 × 6TF × 평균 갭수를 감안하여
    # 200000 까지 수용. Redis 가용 시 무제한 ZSET 사용으로 이 값 미사용.
    "gap_queue_capacity": 200000,
}

_RANGES: Dict[str, tuple] = {
    "max_concurrency": (1, 32),
    "max_gaps_per_cycle": (50, 2000),
    "max_pages_per_gap": (10, 500),
    "rest_max_concurrent": (1, 32),
    "rest_rate_per_second": (1, 10),
    "rest_rate_per_minute": (10, 600),
    "gap_queue_capacity": (10000, 2000000),
}

# 환경변수 매핑 (하위 호환)
_ENV_KEYS: Dict[str, str] = {
    "max_concurrency": "AUTO_BACKFILL_MAX_CONCURRENCY",
    "max_gaps_per_cycle": "AUTO_BACKFILL_MAX_GAPS_PER_CYCLE",
    "max_pages_per_gap": "AUTO_BACKFILL_MAX_PAGES_PER_GAP",
    "rest_max_concurrent": "REST_COLLECTOR_MAX_CONCURRENT",
    "rest_rate_per_second": "UPBIT_REST_RATE_PER_SECOND",
    "rest_rate_per_minute": "UPBIT_REST_RATE_PER_MINUTE",
    "gap_queue_capacity": "GAP_QUEUE_MAX_SIZE",
}

_CACHE_TTL_SECONDS = 60.0  # MongoDB 재조회 주기

# 캐시 상태 (스레드 안전)
_cache_lock = threading.Lock()
_cache: Dict[str, int] = {}
_cache_loaded_at: float = 0.0


def _clamp(name: str, value: int) -> int:
    lo, hi = _RANGES.get(name, (1, 1 << 30))
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = _DEFAULTS[name]
    return max(lo, min(hi, v))


def _load_from_mongo() -> Optional[Dict[str, int]]:
    """MongoDB 에서 ``backfill_scheduler.performance`` 를 읽어온다.

    Returns:
        dict | None: 정규화된 설정. 실패 시 None.
    """
    try:
        from pymongo import MongoClient  # type: ignore

        mongo_uri = os.environ.get(
            "MONGO_URI", "mongodb://localhost:27017/upbit_trader"
        )
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=1500,
            directConnection=True,
        )
        try:
            db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
            doc = (
                client[db_name]["ui_settings"].find_one({"user_id": "default"})
                or {}
            )
            bf_sched = doc.get("backfill_scheduler", {}) or {}
            perf = bf_sched.get("performance", {}) or {}
            if not isinstance(perf, dict):
                return None
            out: Dict[str, int] = {}
            for k in _DEFAULTS:
                if k in perf and perf[k] is not None:
                    out[k] = _clamp(k, perf[k])
            return out or None
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as exc:
        logger.debug("[performance_settings] MongoDB 로드 실패: %s", exc)
        return None


def _resolve_value(name: str, mongo_values: Dict[str, int]) -> int:
    """우선순위에 따라 단일 키의 값을 결정한다."""
    if name in mongo_values:
        return mongo_values[name]
    env_key = _ENV_KEYS.get(name)
    if env_key:
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return _clamp(name, env_val)
    return _DEFAULTS[name]


def _refresh_cache_if_needed(force: bool = False) -> None:
    global _cache, _cache_loaded_at
    now = time.monotonic()
    with _cache_lock:
        if (
            not force
            and _cache
            and (now - _cache_loaded_at) < _CACHE_TTL_SECONDS
        ):
            return
        mongo_values = _load_from_mongo() or {}
        new_cache = {
            name: _resolve_value(name, mongo_values) for name in _DEFAULTS
        }
        _cache = new_cache
        _cache_loaded_at = now


def get_settings(force_refresh: bool = False) -> Dict[str, int]:
    """현재 유효한 모든 성능 설정을 dict 로 반환한다.

    Args:
        force_refresh: True 면 캐시 무시하고 즉시 MongoDB 재조회

    Returns:
        dict[str, int]: ``max_concurrency`` / ``max_gaps_per_cycle`` /
            ``max_pages_per_gap`` 키를 가진 dict. 항상 정수.
    """
    _refresh_cache_if_needed(force=force_refresh)
    with _cache_lock:
        return dict(_cache)


def get_max_concurrency() -> int:
    """동시 처리 Gap 수 (asyncio.Semaphore 크기)."""
    return get_settings()["max_concurrency"]


def get_max_gaps_per_cycle() -> int:
    """한 사이클에서 처리할 최대 Gap 수."""
    return get_settings()["max_gaps_per_cycle"]


def get_max_pages_per_gap() -> int:
    """Gap 1건당 REST 페이지 순회 최대 횟수."""
    return get_settings()["max_pages_per_gap"]


def get_rest_max_concurrent() -> int:
    """RestCandleCollector 가 동시에 띄우는 REST 태스크 수.

    Upbit 한도(10 req/s)는 글로벌 AsyncRateLimiter 가 강제하므로 큰 값도 안전.
    """
    return get_settings()["rest_max_concurrent"]


def get_rest_rate_per_second() -> int:
    """AsyncRateLimiter 초당 한도. 1~10 범위로 클램프."""
    return get_settings()["rest_rate_per_second"]


def get_rest_rate_per_minute() -> int:
    """AsyncRateLimiter 분당 한도. 10~600 범위로 클램프."""
    return get_settings()["rest_rate_per_minute"]


def get_gap_queue_capacity() -> int:
    """GapFinder 인메모리 백필 큐(deque)의 최대 크기.

    Redis 미가용 환경에서만 사용된다. Redis ZSET 사용 시 무제한이며
    이 값은 적용되지 않는다.
    """
    return get_settings()["gap_queue_capacity"]


def invalidate_cache() -> None:
    """다이얼로그 저장 직후처럼 즉시 새 값을 반영하고 싶을 때 호출."""
    global _cache, _cache_loaded_at
    with _cache_lock:
        _cache = {}
        _cache_loaded_at = 0.0


def get_defaults() -> Dict[str, int]:
    """UI 다이얼로그가 기본값을 표시할 때 사용."""
    return dict(_DEFAULTS)


def get_ranges() -> Dict[str, tuple]:
    """UI 다이얼로그가 SpinBox 범위를 설정할 때 사용."""
    return {k: tuple(v) for k, v in _RANGES.items()}


__all__ = [
    "get_settings",
    "get_max_concurrency",
    "get_max_gaps_per_cycle",
    "get_max_pages_per_gap",
    "get_rest_max_concurrent",
    "get_rest_rate_per_second",
    "get_rest_rate_per_minute",
    "get_gap_queue_capacity",
    "invalidate_cache",
    "get_defaults",
    "get_ranges",
]
