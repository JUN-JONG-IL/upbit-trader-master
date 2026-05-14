#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis L1 캐시 통합 관리자 (개선판)

설계 요지:
- 전달된 client(wrapper 또는 low-level)를 허용하고, 없으면 레포의 get_redis_client 팩토리로 생성
- 블로킹(redis-py) 호출은 asyncio의 run_in_executor로 실행하여 비동기 환경에서도 안전하게 사용
- 캔들(정렬집합), 호가(해시+TTL), 체결(리스트+TTL) 관리 및 배치 작업 제공
- 한글 주석/로깅 포함
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import partial
from typing import Any, Dict, List, Optional, Callable
import importlib.util
from pathlib import Path

logger = logging.getLogger("cache_manager")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] [cache_manager] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# 기본 설정값
_CANDLE_MAX = 500
_ORDERBOOK_TTL = 5
_TRADE_MAX = 100
_TRADE_TTL = 300
_CANDLE_TTL = 7 * 24 * 3600
_PIPELINE_BATCH = 100

# 직렬화: orjson 우선, 없으면 json
try:
    import orjson as _orjson  # type: ignore

    def _dumps(obj: Any) -> str:
        return _orjson.dumps(obj).decode("utf-8")

    def _loads(data: Any) -> Any:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return _orjson.loads(data)
except Exception:
    import json as _json  # type: ignore

    def _dumps(obj: Any) -> str:
        return _json.dumps(obj, default=str, ensure_ascii=False)

    def _loads(data: Any) -> Any:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return _json.loads(data)


def _candle_key(symbol: str, tf: str) -> str:
    return f"candles:{symbol}:{tf}"


def _orderbook_key(symbol: str) -> str:
    return f"orderbook:{symbol}"


def _trade_key(symbol: str) -> str:
    return f"trade:{symbol}"


def _ts(t: Any) -> float:
    """datetime 또는 숫자를 Unix timestamp로 변환"""
    if isinstance(t, datetime):
        return t.timestamp()
    try:
        return float(t)
    except Exception:
        return 0.0


# -------------------------
# get_redis_client 팩토리 동적 로드 (상대 import 실패 회피)
# -------------------------
def _load_get_redis_client() -> Optional[Callable[..., Any]]:
    try:
        # 상대 임포트 시도
        from .redis_client import get_redis_client  # type: ignore
        return get_redis_client
    except Exception:
        # 파일 경로에서 동적 로드 (개발환경에서 상대 import가 실패할 수 있음)
        try:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "src" / "data_01" / "redis" / "redis_client.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("redis_client_dynamic", str(candidate))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    return getattr(mod, "get_redis_client", None)
        except Exception:
            logger.debug("dynamic load of redis_client failed", exc_info=True)
    return None


_get_redis_client = _load_get_redis_client()


def _get_raw_client(client: Any) -> Any:
    """
    wrapper에서 low-level client 추출:
    - 흔한 속성: _client, client, redis
    - 없으면 client 자체 반환
    """
    if client is None:
        return None
    for attr in ("_client", "client", "redis"):
        try:
            raw = getattr(client, attr, None)
            if raw:
                return raw
        except Exception:
            continue
    return client


async def _run_blocking(func: Callable, *args, **kwargs):
    """블로킹 함수를 기본 스레드풀에서 실행"""
    loop = asyncio.get_running_loop()
    p = partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, p)


class CacheManager:
    """
    Redis L1 캐시 관리자

    Args:
        client: 동기 wrapper 또는 low-level client 또는 None.
                None이면 get_redis_client(use_cached=True)를 사용 시도.
        pipeline_batch: 파이프라인 배치 크기
    """

    def __init__(self, client: Any = None, pipeline_batch: int = _PIPELINE_BATCH) -> None:
        self._provided = client
        self._raw = _get_raw_client(client)
        self._pipeline_batch = pipeline_batch

    def _ensure_raw(self) -> Any:
        """raw client 확보: 이미 있으면 재사용, 없으면 get_redis_client 팩토리로 생성"""
        if self._raw:
            return self._raw
        if _get_redis_client:
            try:
                wrapper = _get_redis_client(use_cached=True)
                self._raw = _get_raw_client(wrapper)
                return self._raw
            except Exception:
                logger.debug("get_redis_client 생성 실패", exc_info=True)
        logger.error("Redis 클라이언트가 제공되지 않았습니다")
        return None

    # ---------------------------
    # 체결 (List)
    # ---------------------------
    async def push_trade(self, symbol: str, trade: Dict[str, Any]) -> bool:
        """체결을 LPUSH로 추가하고 LTRIM/EXPIRE 처리"""
        raw = self._ensure_raw()
        if raw is None:
            return False
        key = _trade_key(symbol)
        member = _dumps(trade)

        def _op():
            pipe = raw.pipeline()
            pipe.lpush(key, member)
            pipe.ltrim(key, 0, _TRADE_MAX - 1)
            pipe.expire(key, _TRADE_TTL)
            pipe.execute()
            return True

        try:
            return await _run_blocking(_op)
        except Exception:
            logger.exception("push_trade 실패 (%s)", symbol)
            return False

    async def get_trades(self, symbol: str, limit: int = _TRADE_MAX) -> List[Dict[str, Any]]:
        """최근 체결 조회 (최신 순)"""
        raw = self._ensure_raw()
        if raw is None:
            return []
        def _op():
            return raw.lrange(_trade_key(symbol), 0, limit - 1)
        try:
            lst = await _run_blocking(_op)
            out: List[Dict[str, Any]] = []
            for r in lst or []:
                try:
                    out.append(_loads(r))
                except Exception:
                    out.append(r)
            return out
        except Exception:
            logger.exception("get_trades 실패 (%s)", symbol)
            return []

    # ---------------------------
    # 호가 (Hash, TTL)
    # ---------------------------
    async def set_orderbook(self, symbol: str, orderbook: Dict[str, Any]) -> bool:
        """호가를 해시로 저장하고 TTL 적용"""
        raw = self._ensure_raw()
        if raw is None:
            return False
        key = _orderbook_key(symbol)
        mapping = {k: str(v) for k, v in (orderbook or {}).items()}

        def _op():
            pipe = raw.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, _ORDERBOOK_TTL)
            pipe.execute()
            return True

        try:
            return await _run_blocking(_op)
        except Exception:
            logger.exception("set_orderbook 실패 (%s)", symbol)
            return False

    async def get_orderbook(self, symbol: str) -> Optional[Dict[str, str]]:
        """호가 조회 (만료되면 None)"""
        raw = self._ensure_raw()
        if raw is None:
            return None
        def _op():
            return raw.hgetall(_orderbook_key(symbol))
        try:
            data = await _run_blocking(_op)
            return data if data else None
        except Exception:
            logger.exception("get_orderbook 실패 (%s)", symbol)
            return None

    # ---------------------------
    # 캔들 (Sorted Set)
    # ---------------------------
    async def push_candle(self, symbol: str, timeframe: str, candle: Dict[str, Any]) -> bool:
        """단일 캔들을 Sorted Set에 추가하고 보관 정책 적용"""
        raw = self._ensure_raw()
        if raw is None:
            return False
        key = _candle_key(symbol, timeframe)
        score = _ts(candle.get("time") or candle.get("timestamp", 0))
        member = _dumps(candle)

        def _op():
            raw.zadd(key, {member: score})
            raw.zremrangebyrank(key, 0, -(_CANDLE_MAX + 1))
            raw.expire(key, _CANDLE_TTL)
            return True

        try:
            return await _run_blocking(_op)
        except Exception:
            logger.exception("push_candle 실패 (%s %s)", symbol, timeframe)
            return False

    async def push_candle_batch(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> int:
        """캔들을 파이프라인으로 배치 저장 (리턴: 저장한 캔들 수)"""
        raw = self._ensure_raw()
        if raw is None or not candles:
            return 0
        key = _candle_key(symbol, timeframe)

        def _op_batch():
            pipe = raw.pipeline()
            members = []
            for c in candles:
                member = _dumps(c)
                members.append((member, _ts(c.get("time") or c.get("timestamp", 0))))
            for i in range(0, len(members), self._pipeline_batch):
                chunk = dict(members[i : i + self._pipeline_batch])
                pipe.zadd(key, chunk)
            pipe.zremrangebyrank(key, 0, -(_CANDLE_MAX + 1))
            pipe.expire(key, _CANDLE_TTL)
            pipe.execute()
            return len(candles)

        try:
            return await _run_blocking(_op_batch)
        except Exception:
            logger.exception("push_candle_batch 실패 (%s %s)", symbol, timeframe)
            return 0

    async def get_candles(self, symbol: str, timeframe: str, limit: int = _CANDLE_MAX) -> List[Dict[str, Any]]:
        """최신 N개 캔들 조회 (정렬: 최신->오래된)"""
        raw = self._ensure_raw()
        if raw is None:
            return []
        def _op():
            return raw.zrevrange(_candle_key(symbol, timeframe), 0, limit - 1)
        try:
            vals = await _run_blocking(_op)
            out: List[Dict[str, Any]] = []
            for r in vals or []:
                try:
                    out.append(_loads(r))
                except Exception:
                    out.append(r)
            return out
        except Exception:
            logger.exception("get_candles 실패 (%s %s)", symbol, timeframe)
            return []

    # ---------------------------
    # 유틸
    # ---------------------------
    async def invalidate(self, symbol: str, timeframe: Optional[str] = None) -> None:
        """심볼의 캐시 키를 삭제합니다 (timeframe 지정 시 candles만 삭제)"""
        raw = self._ensure_raw()
        if raw is None:
            return
        keys = []
        if timeframe:
            keys.append(_candle_key(symbol, timeframe))
        else:
            keys += [_orderbook_key(symbol), _trade_key(symbol)]
        def _op_del():
            raw.delete(*keys)
            return True
        try:
            await _run_blocking(_op_del)
        except Exception:
            logger.exception("invalidate 실패 (%s)", symbol)
