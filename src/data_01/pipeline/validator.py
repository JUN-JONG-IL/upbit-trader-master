# -*- coding: utf-8 -*-
"""
Stage 4: OHLC / Gap / 이상치 검증 (Invalid-store 비동기 큐 처리 추가)

변경 요약:
- invalid_store.store_invalid_candle 호출을 즉시 실행하지 않고 내부 큐에 적재하여
  단일 백그라운드 워커가 직렬/배치로 처리하도록 변경했습니다.
- 큐는 바운디드이며, 가득 찼을 경우 드롭(로그 샘플링)하여 DB 연결 폭발 위험을 줄입니다.
- store 함수가 코루틴인 경우에도 대응합니다 (워커에서 asyncio.run 사용).
- 모듈 수준에서 시작되는 워커는 데몬 스레드로 앱 종료 시 자동 종료되며,
  필요한 경우 shutdown_invalid_store()를 호출해 안전하게 플러시할 수 있습니다.

이 파일만 바꿔도 invalid_store에 의한 동시 DB 연결 폭주 문제를 크게 완화할 수 있습니다.
"""
from __future__ import annotations

import logging
import os
import inspect
import asyncio
import threading
import queue
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Any, Dict, Callable, Sequence
from pathlib import Path
import importlib.util

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# invalid_store import (안전 폴백: 상대 import, 파일 경로, 없으면 noop)
# ---------------------------------------------------------------------
store_invalid_candle: Optional[Callable[..., Any]] = None
try:
    from .invalid_store import store_invalid_candle  # type: ignore
    logger.debug("invalid_store imported via package-relative import")
except Exception:
    store_invalid_candle = None
    try:
        _path = Path(__file__).resolve().parent / "invalid_store.py"
        if _path.exists():
            spec = importlib.util.spec_from_file_location("pipeline_invalid_store", str(_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                store_invalid_candle = getattr(mod, "store_invalid_candle", None)
                logger.debug("invalid_store loaded from file fallback")
    except Exception:
        logger.debug("invalid_store file load failed (ignored)", exc_info=True)

if store_invalid_candle is None:
    def store_invalid_candle(*args, **kwargs):
        """fallback noop - invalid_store를 사용할 수 없을 때 동작"""
        return None

# ---------------------------------------------------------------------
# InvalidStoreManager: 큐 + 백그라운드 워커
# - ENV:
#     INVALID_STORE_QUEUE_MAX (default 2000)
#     INVALID_STORE_BATCH_SIZE (default 50)
#     INVALID_STORE_FLUSH_INTERVAL (default 1.0 seconds)
# ---------------------------------------------------------------------
_INVALID_STORE_QUEUE_MAX = int(os.getenv("INVALID_STORE_QUEUE_MAX", "2000"))
_INVALID_STORE_BATCH_SIZE = int(os.getenv("INVALID_STORE_BATCH_SIZE", "50"))
_INVALID_STORE_FLUSH_INTERVAL = float(os.getenv("INVALID_STORE_FLUSH_INTERVAL", "1.0"))
_INVALID_STORE_DROP_LOG_SAMPLE = int(os.getenv("INVALID_STORE_DROP_LOG_SAMPLE", "100"))  # drop 로깅 샘플 주기

class InvalidStoreManager:
    """invalid_store 호출을 비동기 배치 처리하는 싱글톤 매니저."""
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._q: "queue.Queue[dict]" = queue.Queue(maxsize=_INVALID_STORE_QUEUE_MAX)
        self._thread: Optional[threading.Thread] = None
        self._stop_ev = threading.Event()
        self._dropped = 0
        self._processed = 0
        self._start_worker()

    @classmethod
    def instance(cls) -> "InvalidStoreManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = InvalidStoreManager()
        return cls._instance

    def _start_worker(self):
        if self._thread and self._thread.is_alive():
            return
        t = threading.Thread(target=self._worker_loop, name="invalid-store-wkr", daemon=True)
        self._thread = t
        t.start()
        logger.debug("InvalidStoreManager worker started (queue_max=%d batch=%d)", _INVALID_STORE_QUEUE_MAX, _INVALID_STORE_BATCH_SIZE)

    def enqueue(self, payload: dict) -> bool:
        """큐에 항목을 넣습니다. 큐가 가득하면 드롭 후 False 반환."""
        try:
            self._q.put_nowait(payload)
            return True
        except queue.Full:
            self._dropped += 1
            if self._dropped % max(1, _INVALID_STORE_DROP_LOG_SAMPLE) == 0:
                logger.warning("[InvalidStore] 큐 가득 참 - %d 건 드롭", self._dropped)
            return False

    def _call_store(self, item: dict):
        """store_invalid_candle 호출을 안전하게 수행 (동기/비동기 모두 지원)."""
        try:
            if inspect.iscoroutinefunction(store_invalid_candle):
                # store_invalid_candle은 코루틴 함수
                try:
                    asyncio.run(store_invalid_candle(item))
                except Exception as e:
                    logger.debug("[InvalidStore] async store failed: %s", e, exc_info=True)
            else:
                # 호출이 코루틴 객체를 반환할 수도 있음
                res = store_invalid_candle(item)
                if asyncio.iscoroutine(res):
                    try:
                        asyncio.run(res)
                    except Exception as e:
                        logger.debug("[InvalidStore] async returned coroutine failed: %s", e, exc_info=True)
        except Exception as exc:
            logger.debug("[InvalidStore] store_invalid_candle() 호출 실패 (무시): %s", exc, exc_info=True)

    def _worker_loop(self):
        """백그라운드에서 큐를 배치로 꺼내 store를 호출합니다."""
        batch: list[dict] = []
        while not self._stop_ev.is_set():
            try:
                try:
                    item = self._q.get(timeout=_INVALID_STORE_FLUSH_INTERVAL)
                    batch.append(item)
                except queue.Empty:
                    # flush 주기
                    pass

                # 배치가 충분하거나 시간이 되었으면 처리
                if batch and (len(batch) >= _INVALID_STORE_BATCH_SIZE or self._stop_ev.is_set()):
                    # 순차 처리: 각 항목마다 호출하되, 필요시 execute_values 등으로 최적화 가능
                    for it in batch:
                        try:
                            self._call_store(it)
                            self._processed += 1
                        except Exception:
                            logger.debug("[InvalidStore] 개별 store 처리 실패 (무시)", exc_info=True)
                    batch.clear()
                # 주기적으로 루프 돌아가며 신규 아이템 수집
            except Exception:
                logger.exception("[InvalidStore] 워커 루프 예외")

        # 종료 시 남은 배치를 처리(최대 몇 차례)
        if batch:
            for it in batch:
                try:
                    self._call_store(it)
                    self._processed += 1
                except Exception:
                    logger.debug("[InvalidStore] 종료시 개별 store 처리 실패 (무시)", exc_info=True)
            batch.clear()
        # drain remaining queue
        while True:
            try:
                it = self._q.get_nowait()
                try:
                    self._call_store(it)
                    self._processed += 1
                except Exception:
                    logger.debug("[InvalidStore] 종료시 드레인 실패 (무시)", exc_info=True)
            except queue.Empty:
                break
        logger.debug("[InvalidStore] worker stopped (processed=%d dropped=%d)", self._processed, self._dropped)

    def shutdown(self, timeout: float = 5.0):
        """워커 종료: 플러시 후 스레드 종료 대기."""
        self._stop_ev.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)
        logger.debug("[InvalidStore] shutdown complete (processed=%d dropped=%d)", self._processed, self._dropped)


# 모듈 레벨 싱글톤 생성
_invalid_store_mgr = InvalidStoreManager.instance()

def enqueue_invalid_candle(entry: dict) -> bool:
    """외부에서 사용: 검증 실패 항목을 비동기 큐에 적재합니다."""
    return _invalid_store_mgr.enqueue(entry)


def shutdown_invalid_store(timeout: float = 5.0):
    """앱 종료 시 호출하면 invalid-store 워커를 안전히 종료합니다."""
    try:
        _invalid_store_mgr.shutdown(timeout=timeout)
    except Exception:
        logger.debug("shutdown_invalid_store 중 예외", exc_info=True)

# ---------------------------------------------------------------------
# 예외 타입 정의
# ---------------------------------------------------------------------
class ValidationError(Exception):
    """OHLC 또는 거래량, 필드 타입 검증 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"검증오류: {self.message}"


class GapExceededException(Exception):
    """Gap이 허용치를 초과했을 때 발생합니다."""

    def __init__(self, gap_seconds: float, symbol: str = "", timeframe: str = "") -> None:
        self.gap_seconds = gap_seconds
        self.symbol = symbol
        self.timeframe = timeframe
        super().__init__(f"Gap {gap_seconds:.0f}s 감지 (symbol={symbol}, tf={timeframe})")

    def __str__(self) -> str:
        return f"GapExceeded: symbol={self.symbol}, timeframe={self.timeframe}, gap={self.gap_seconds}s"


# 타임프레임별 초 단위 (필요시 확장)
_TF_SECONDS: dict[str, int] = {
    "1s": 1,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# ========================================
# Timezone 정규화 헬퍼 함수
# ========================================
def _ensure_timezone_aware(dt: datetime) -> datetime:
    """
    datetime이 timezone-naive면 UTC로 변환.
    이미 timezone-aware면 그대로 반환.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# =====================================================================
# tick 데이터 → OHLCV 캔들 정규화 (WebSocket 실시간 tick 처리)
# =====================================================================
def normalize_tick_to_candle(tick: dict) -> dict:
    """
    업비트 WebSocket tick 데이터를 OHLCV 캔들 형식으로 변환합니다.
    """
    # 가격
    price_raw = tick.get("trade_price") or tick.get("close") or tick.get("price") or 0
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        price = 0.0

    # 거래량
    vol_raw = tick.get("trade_volume") or tick.get("volume") or 0
    try:
        volume = float(vol_raw)
    except (TypeError, ValueError):
        volume = 0.0

    # 심볼
    symbol = tick.get("code") or tick.get("symbol") or tick.get("market") or ""

    # 시간: timestamp(ms) 또는 trade_timestamp(ms)
    ts_raw = tick.get("timestamp") or tick.get("trade_timestamp") or tick.get("ts")
    if ts_raw is not None:
        try:
            ts_ms = int(ts_raw)
            time_val = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            time_val = datetime.now(timezone.utc)
    else:
        time_val = tick.get("time")
        if isinstance(time_val, str):
            try:
                time_val = datetime.fromisoformat(time_val)
            except Exception:
                time_val = datetime.now(timezone.utc)
        elif not isinstance(time_val, datetime):
            time_val = datetime.now(timezone.utc)

    time_val = _ensure_timezone_aware(time_val)

    return {
        "symbol": symbol,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
        "time": time_val,
        "exchange": tick.get("exchange", "upbit"),
        "timeframe": tick.get("timeframe", "tick"),
        "_is_tick": True,
        "_original_tick": tick,
    }


def _is_tick_data(candle: dict) -> bool:
    if not isinstance(candle, dict):
        return False
    if candle.get("type") == "trade":
        return True
    if candle.get("trade_price") is not None and "open" not in candle:
        return True
    if candle.get("_is_tick"):
        return True
    return False


# ---------------------------------------------------------------------
# 검증기 본문
# ---------------------------------------------------------------------
class CandleValidator:
    """
    캔들 데이터 검증 클래스 (타입/범위/Gap 검사 포함).
    """

    _GAP_MULTIPLIER = 50

    def __init__(self, max_gap_seconds: int = 3600) -> None:
        self.max_gap_seconds = max_gap_seconds

    def _to_float(self, v: Any) -> float:
        try:
            return float(v)
        except Exception:
            raise ValidationError(f"숫자 변환 실패: {v}")

    def validate_ohlc(self, candle: Dict[str, Any]) -> None:
        high  = self._to_float(candle.get("high",  0))
        low   = self._to_float(candle.get("low",   0))
        open_ = self._to_float(candle.get("open",  0))
        close = self._to_float(candle.get("close", 0))

        if high < low:
            raise ValidationError("high 값이 low 보다 작습니다")
        if high < open_:
            raise ValidationError("high 값이 open 보다 작습니다")
        if high < close:
            raise ValidationError("high 값이 close 보다 작습니다")
        if low > open_:
            raise ValidationError("low 값이 open 보다 큽니다")
        if low > close:
            raise ValidationError("low 값이 close 보다 큽니다")

    def validate_volume(self, candle: Dict[str, Any]) -> None:
        volume = candle.get("volume")
        if volume is not None:
            v = self._to_float(volume)
            if v < 0:
                raise ValidationError(f"volume 음수 불가: {v}")

        quote_volume = candle.get("quote_volume")
        if quote_volume is not None:
            qv = self._to_float(quote_volume)
            if qv < 0:
                raise ValidationError(f"quote_volume 음수 불가: {qv}")

    def validate_gap(self, candle: Dict[str, Any], last_time: datetime, timeframe: str) -> None:
        t = candle.get("time")
        if isinstance(t, str):
            try:
                t = datetime.fromisoformat(t)
            except Exception:
                raise ValidationError("time 문자열 파싱 실패")
        if not isinstance(t, datetime):
            raise ValidationError("time 타입 오류")

        t = _ensure_timezone_aware(t)
        last_time = _ensure_timezone_aware(last_time)

        tf_secs = _TF_SECONDS.get(timeframe, 60)
        threshold = tf_secs * self._GAP_MULTIPLIER
        delta = (t - last_time).total_seconds()
        if delta > threshold:
            sym = candle.get("symbol", "")
            raise GapExceededException(delta, symbol=sym, timeframe=timeframe)

    def validate(self, candle: Dict[str, Any], last_time: Optional[datetime] = None) -> None:
        if not isinstance(candle, dict):
            raise ValidationError("캔들 데이터 형식 오류 (dict 기대)")

        # tick 데이터 자동 정규화
        if _is_tick_data(candle):
            normalized = normalize_tick_to_candle(candle)
            candle.update(normalized)
            logger.debug("tick 데이터 정규화 완료: symbol=%s price=%s", candle.get("symbol"), candle.get("close"))

        # time 필드 검증 및 정규화
        t = candle.get("time")
        if t is None:
            raise ValidationError("time 필드 누락")
        if isinstance(t, str):
            try:
                t = datetime.fromisoformat(t)
            except Exception:
                raise ValidationError("time 문자열 파싱 실패")
        if not isinstance(t, datetime):
            raise ValidationError("time 타입 오류")

        t = _ensure_timezone_aware(t)
        candle["time"] = t

        # symbol 검증
        sym = candle.get("symbol")
        if not sym:
            raise ValidationError("symbol 누락")

        # numeric 필드 체크
        for fld in ("open", "high", "low", "close"):
            if fld not in candle:
                raise ValidationError(f"{fld} 필드 누락")
            try:
                candle[fld] = self._to_float(candle[fld])
            except ValidationError:
                # invalid 저장은 즉시 호출 대신 큐에 적재 (비동기)
                try:
                    enqueue_invalid_candle({"symbol": sym, "time": t.isoformat(), "candle": candle.copy(), "reason": f"{fld} 숫자 변환 실패"})
                except Exception:
                    logger.debug("enqueue_invalid_candle 실패", exc_info=True)
                raise

        # OHLC 논리 검증
        if not (candle["low"] <= candle["high"]):
            try:
                enqueue_invalid_candle({"symbol": sym, "time": t.isoformat(), "candle": candle.copy(), "reason": "low > high"})
            except Exception:
                logger.debug("enqueue_invalid_candle 실패", exc_info=True)
            raise ValidationError("low 값이 high 보다 큽니다")

        # Gap 검사: 경고만 출력 (데이터 손실 방지)
        if last_time and isinstance(last_time, datetime):
            last_time = _ensure_timezone_aware(last_time)
            delta = (t - last_time).total_seconds()
            if delta > self.max_gap_seconds:
                logger.warning(
                    "Gap 감지 (계속 저장): symbol=%s gap=%.0f초 (약 %.1f일) - 격리하지 않고 정상 저장합니다",
                    sym, delta, delta / 86400,
                )

    def validate_tick(self, tick: Dict[str, Any]) -> None:
        if not isinstance(tick, dict):
            raise ValidationError("tick 데이터 형식 오류 (dict 기대)")
        price_raw = tick.get("trade_price") or tick.get("close")
        if price_raw is None:
            raise ValidationError("trade_price 또는 close 필드 누락")
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            raise ValidationError(f"trade_price 숫자 변환 실패: {price_raw}")
        if price < 0:
            raise ValidationError(f"trade_price 음수 불가: {price}")

    def is_valid(self, candle: Dict[str, Any], last_time: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
        try:
            self.validate(candle, last_time=last_time)
            return True, None
        except Exception as e:
            return False, str(e)