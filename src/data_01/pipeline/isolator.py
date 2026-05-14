# -*- coding: utf-8 -*-
"""
Stage 5: 이상 데이터 격리 & Gap 큐잉 (상대 import + 파일 폴백 적용)

- 변경 요지:
  * invalid_store 및 validator 의 import를 상대 import로 시도하고
    실패하면 파일경로로 동적 로드하는 폴백을 적용했습니다.
  * Redis 클라이언트는 레포의 동기 래퍼(redis-py 기반) 또는 redis.Redis 인스턴스가 올 수 있으므로,
    이벤트 루프 블로킹을 피하기 위해 run_in_executor로 동기 호출을 실행합니다.
  * ✅ 터미널 로그 정리 (DEBUG/INFO → 레벨 조정)
  * ✅ _enqueue_gap() 타입 힌트 수정 (Pylance 경고 해결)
  * ✅ _enqueue_gap() 안전성 강화 (속성 누락 방어)
  * 모든 주석은 한글입니다.
"""
from __future__ import annotations

import asyncio
import functools
import importlib
import importlib.util
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict
from pathlib import Path

# orjson optional
try:
    import orjson  # type: ignore
except Exception:
    orjson = None  # type: ignore

logger = logging.getLogger(__name__)

# 에러 로그 속도 제한 유틸리티 로드 (core 디렉터리명이 숫자로 시작하므로 파일 기반 로드)
_log_error_throttled = None
try:
    _et_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "utils", "error_throttler.py")
    )
    if os.path.isfile(_et_path):
        _et_spec = importlib.util.spec_from_file_location("_error_throttler_isolator", _et_path)
        if _et_spec and _et_spec.loader:
            _et_mod = importlib.util.module_from_spec(_et_spec)
            _et_spec.loader.exec_module(_et_mod)
            _log_error_throttled = getattr(_et_mod, "log_error_throttled", None)
except Exception:
    pass

# RateLimitedErrorFilter 폴백 (error_throttler 로드 실패 시)
_RateLimitedErrorFilter = None
try:
    _lc_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "config", "logging_config.py")
    )
    if os.path.isfile(_lc_path):
        _lc_spec = importlib.util.spec_from_file_location("_logging_config_isolator", _lc_path)
        if _lc_spec and _lc_spec.loader:
            _lc_mod = importlib.util.module_from_spec(_lc_spec)
            _lc_spec.loader.exec_module(_lc_mod)
            _RateLimitedErrorFilter = getattr(_lc_mod, "RateLimitedErrorFilter", None)
except Exception:
    pass

if _RateLimitedErrorFilter is not None:
    try:
        logger.addFilter(_RateLimitedErrorFilter(interval_seconds=300))
    except Exception:
        pass

# validator import (상대 import 시도, 실패 시 파일경로 폴백)
GapExceededException = None
ValidationError = None
try:
    from .validator import GapExceededException as _GapExc, ValidationError as _ValErr  # type: ignore
    GapExceededException = _GapExc
    ValidationError = _ValErr
except Exception:
    try:
        _vpath = Path(__file__).resolve().parents[1] / "validator.py"
        if _vpath.exists():
            spec = importlib.util.spec_from_file_location("pipeline_validator_fallback", str(_vpath))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                GapExceededException = getattr(mod, "GapExceededException", None)
                ValidationError = getattr(mod, "ValidationError", None)
    except Exception:
        logger.debug("validator 파일 로드 폴백 실패", exc_info=True)

# 폴백: 클래스가 로드되지 않으면 Exception 사용
if GapExceededException is None:
    GapExceededException = Exception
if ValidationError is None:
    ValidationError = Exception

# invalid_store import (상대 import 시도, 실패 시 파일경로 폴백)
try:
    from .invalid_store import store_invalid_candle  # type: ignore
except Exception:
    store_invalid_candle = None
    try:
        _is_path = Path(__file__).resolve().parents[1] / "invalid_store.py"
        if _is_path.exists():
            spec = importlib.util.spec_from_file_location("pipeline_invalid_store", str(_is_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                store_invalid_candle = getattr(mod, "store_invalid_candle", None)
    except Exception:
        logger.debug("invalid_store 파일 경로 로드 실패", exc_info=True)

if store_invalid_candle is None:
    def store_invalid_candle(*args, **kwargs):
        """fallback noop"""
        return None

# Gap 우선순위 상수
GAP_PRIORITY_HIGH = 10
GAP_PRIORITY_MEDIUM = 5
GAP_PRIORITY_LOW = 1

# 운영 시 설정에서 로드 권장
HOT_SYMBOLS: set[str] = {"KRW-BTC", "KRW-ETH", "KRW-XRP"}


def _serialize_json(obj: Any) -> str:
    """orjson 우선 사용, 없으면 json.dumps"""
    if orjson:
        try:
            return orjson.dumps(obj).decode()
        except Exception:
            pass
    import json as _json
    try:
        return _json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


class CandleIsolator:
    """유효하지 않은 캔들을 격리하고 Gap을 큐에 등록합니다."""

    def __init__(self, pool: Optional[Any] = None, redis_client: Optional[Any] = None, gap_job_ttl_seconds: int = 3600) -> None:
        """
        Args:
            pool: async DB pool (예: asyncpg pool) - execute(...) 지원 기대
            redis_client: 동기 Redis 클라이언트(레포의 RedisClient 래퍼 또는 redis.Redis)
            gap_job_ttl_seconds: 동일 gap job 재등록 차단 TTL (초)
        """
        self._pool = pool
        self._redis = redis_client
        self._gap_job_ttl = max(60, min(int(gap_job_ttl_seconds), 24 * 3600))

    async def handle(self, candle: dict, exc: Exception) -> None:
        """
        예외 종류에 따라 격리 또는 Gap 큐잉을 수행합니다.

        ValidationError가 "open 필드 누락" 또는 "time 필드 누락"인 경우,
        tick 데이터인지 먼저 체크하여 normalize 후 재처리 시도합니다.
        재처리 실패 시에만 격리합니다.
        """
        reason = str(exc)

        # ✅ tick 데이터 근본 원인 처리: 격리 전 정규화 재시도
        if self._should_try_tick_normalize(candle, exc):
            try:
                normalized = self._try_normalize_tick(candle)
                if normalized is not None:
                    # 정규화 성공 → 격리하지 않고 반환 (상위에서 정상 처리)
                    logger.debug(
                        "[CandleIsolator] tick 정규화 성공, 격리 건너뜀: symbol=%s",
                        normalized.get("symbol", ""),
                    )
                    candle.update(normalized)
                    return
            except Exception as norm_exc:
                logger.debug("[CandleIsolator] tick 정규화 실패, 격리 진행: %s", norm_exc)

        try:
            await self._save_isolated(candle, reason)
        except Exception as e:
            logger.debug("격리 저장 처리 중 예외(무시): %s", e, exc_info=True)

        if isinstance(exc, GapExceededException):
            try:
                await self._enqueue_gap(exc)
            except Exception as e:
                logger.error("Gap 큐 등록 중 예외: %s", e, exc_info=True)

    def _should_try_tick_normalize(self, candle: dict, exc: Exception) -> bool:
        """ValidationError가 tick 관련 오류이고 candle이 tick 데이터인지 판별."""
        if not isinstance(candle, dict):
            return False
        reason = str(exc)
        # tick 관련 오류 패턴 감지
        tick_error_patterns = (
            "open 필드 누락",
            "time 필드 누락",
            "symbol 누락",
        )
        is_tick_error = any(p in reason for p in tick_error_patterns)
        if not is_tick_error:
            return False
        # tick 데이터 여부 확인 (trade_price 또는 type == "trade")
        if candle.get("type") == "trade":
            return True
        if candle.get("trade_price") is not None:
            return True
        return False

    def _try_normalize_tick(self, candle: dict):
        """
        tick 데이터를 OHLCV 형식으로 정규화합니다.
        validator 모듈의 normalize_tick_to_candle 함수를 사용합니다.
        성공 시 정규화된 dict 반환, 실패 시 None 반환.
        """
        try:
            from .validator import normalize_tick_to_candle  # type: ignore
            normalized = normalize_tick_to_candle(candle)
            # 기본 유효성 확인: symbol, time, close 있어야 함
            if not normalized.get("symbol"):
                return None
            if normalized.get("close") is None:
                return None
            return normalized
        except Exception:
            return None

    async def _save_isolated(self, candle: dict, reason: str) -> None:
        """isolated_candles 테이블에 이상 데이터를 저장, 실패 시 fallback 저장"""
        # isolation_reason은 반드시 문자열이어야 합니다.
        # asyncio.Lock 등 비-문자열 객체가 전달되는 버그를 방어합니다.
        if not isinstance(reason, str):
            logger.error(
                "[CandleIsolator] isolation_reason이 문자열이 아닙니다: type=%s, value=%r",
                type(reason).__name__, reason,
            )
            reason = str(reason)

        payload_json = _serialize_json(candle)
        received_at = datetime.now(tz=timezone.utc)

        if self._pool is None:
            logger.warning("격리 저장: DB pool 없음, fallback으로 저장합니다. reason=%s", reason)
            try:
                store_invalid_candle({
                    "symbol": candle.get("symbol"),
                    "time": candle.get("time"),
                    "candle": candle,
                    "reason": reason,
                    "received_at": received_at.isoformat(),
                }, reason)
            except Exception:
                logger.debug("fallback invalid_store 저장 실패(무시)", exc_info=True)
            return

        try:
            _sql = """
                INSERT INTO isolated_candles
                    (time, symbol, timeframe, exchange,
                     open, high, low, close, volume, quote_volume,
                     raw_data, isolation_reason, received_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """
            _params = (
                candle.get("time", received_at),
                candle.get("symbol", ""),
                candle.get("timeframe", "1m"),
                candle.get("exchange", "upbit"),
                candle.get("open"),
                candle.get("high"),
                candle.get("low"),
                candle.get("close"),
                candle.get("volume"),
                candle.get("quote_volume"),
                payload_json,
                reason,
                received_at,
            )
            _loop = asyncio.get_running_loop()
            await _loop.run_in_executor(None, functools.partial(self._pool.execute, _sql, _params))
            logger.debug("isolated_candles 저장 완료: symbol=%s time=%s reason=%s", candle.get("symbol"), candle.get("time"), reason)
        except Exception as db_exc:
            if _log_error_throttled is not None:
                _log_error_throttled(logger, "isolated_candles_save_error",
                                     f"isolated_candles 저장 실패, fallback으로 저장합니다: {db_exc}")
            else:
                logger.error("isolated_candles 저장 실패, fallback으로 저장합니다: %s", db_exc, exc_info=True)
            try:
                store_invalid_candle({
                    "symbol": candle.get("symbol"),
                    "time": candle.get("time"),
                    "candle": candle,
                    "reason": reason,
                    "received_at": received_at.isoformat(),
                }, reason)
                logger.debug("fallback invalid_store 저장 완료: symbol=%s", candle.get("symbol"))
            except Exception:
                logger.exception("fallback invalid_store 저장 실패 (무시): symbol=%s", candle.get("symbol"))

    async def _enqueue_gap(self, exc: Exception) -> None:
        """
        Gap 백필 작업을 Redis gap_fill_queue에 등록합니다.
        - idempotency: gap_job:{symbol}:{timeframe} 키를 SET NX EX 로 잠금
        - redis 클라이언트가 동기 API이므로 run_in_executor로 호출하여 이벤트루프 블로킹을 피합니다.
        
        Args:
            exc: GapExceededException 인스턴스 (타입 힌트는 Exception으로 일반화)
        """
        if self._redis is None:
            logger.warning("Gap 큐잉 건너뜀 (redis 없음)")
            return

        # ✅ 안전한 속성 접근 (기본값 설정)
        symbol = getattr(exc, "symbol", "") or ""
        timeframe = getattr(exc, "timeframe", "1m") or "1m"
        gap_seconds = getattr(exc, "gap_seconds", 0.0)
        
        if not symbol:
            logger.warning("Gap 큐잉 건너뜀 (symbol 없음)")
            return

        priority = GAP_PRIORITY_HIGH if symbol in HOT_SYMBOLS else GAP_PRIORITY_MEDIUM

        # ✅ job_id 생성: GapWorker의 claim_and_process_once()에서 필수 필드
        now_utc = datetime.now(tz=timezone.utc)
        job_id = f"{symbol}:{timeframe}:{int(now_utc.timestamp())}"
        gap_start = (now_utc - timedelta(seconds=gap_seconds)).isoformat()
        gap_end = now_utc.isoformat()

        job_obj: Dict[str, Any] = {
            "job_id": job_id,  # ← GapWorker가 SETNX claim 시 필수
            "symbol": symbol,
            "timeframe": timeframe,
            "gap_seconds": gap_seconds,
            "start": gap_start,
            "end": gap_end,
            "enqueued_at": now_utc.isoformat(),
        }
        member = _serialize_json(job_obj)
        idemp_key = f"gap_job:{symbol}:{timeframe}"
        ttl = self._gap_job_ttl

        low = getattr(self._redis, "client", self._redis)
        loop = asyncio.get_running_loop()

        # 1) SET NX EX 시도
        try:
            if hasattr(low, "set"):
                def _sync_set():
                    try:
                        return low.set(idemp_key, "1", ex=ttl, nx=True)
                    except TypeError:
                        # 일부 래퍼는 (key, value, ttl) 시그니처
                        try:
                            return low.set(idemp_key, "1", ttl)
                        except Exception:
                            return None
                set_ok = await loop.run_in_executor(None, _sync_set)
            else:
                set_ok = None
        except Exception:
            logger.debug("idempotency set 시도 중 예외(무시)", exc_info=True)
            set_ok = None

        # 2) 이미 존재하면 스킵
        try:
            if not set_ok:
                def _sync_get():
                    try:
                        return low.get(idemp_key)
                    except Exception:
                        getter = getattr(self._redis, "get", None)
                        if getter:
                            return getter(idemp_key)
                        return None
                exists_val = await loop.run_in_executor(None, _sync_get)
                if exists_val:
                    logger.debug("Gap job 이미 큐에 존재하여 재등록 생략: %s/%s", symbol, timeframe)
                    return
        except Exception:
            logger.debug("idempotency 키 존재 확인 중 예외(무시)", exc_info=True)

        # 3) ZADD로 등록
        try:
            if hasattr(low, "zadd"):
                def _sync_zadd():
                    try:
                        return low.zadd("gap_fill_queue", {member: priority})
                    except TypeError:
                        try:
                            return low.zadd("gap_fill_queue", member, priority)
                        except Exception:
                            if hasattr(self._redis, "zadd"):
                                return self._redis.zadd("gap_fill_queue", {member: priority})
                            raise
                await loop.run_in_executor(None, _sync_zadd)
            else:
                if hasattr(self._redis, "zadd"):
                    await loop.run_in_executor(None, lambda: self._redis.zadd("gap_fill_queue", {member: priority}))
                else:
                    raise RuntimeError("Redis client에 zadd 메서드가 없습니다.")
            logger.info("Gap 큐 등록: %s/%s (%.0fs, priority=%d)", symbol, timeframe, gap_seconds, priority)
        except Exception as redis_exc:
            logger.error("Gap 큐 등록 실패: %s", redis_exc, exc_info=True)
            try:
                def _sync_del():
                    try:
                        if hasattr(low, "delete"):
                            return low.delete(idemp_key)
                        if hasattr(self._redis, "delete"):
                            return self._redis.delete(idemp_key)
                    except Exception:
                        return None
                await loop.run_in_executor(None, _sync_del)
            except Exception:
                logger.debug("idempotency 키 삭제 실패(무시)", exc_info=True)