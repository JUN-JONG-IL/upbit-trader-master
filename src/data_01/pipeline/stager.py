# -*- coding: utf-8 -*-
"""
Stage: staging_candles 임시 저장기 (세마포어 동시쓰기 제어 포함)

주요 변경점 요약:
- rows 생성 시 dict/list 등 복합 타입은 JSON 문자열(json.dumps)로 안전하게 직렬화
- DB 삽입을 asyncio.BoundedSemaphore로 감싸 프로세스 내부 동시 DB 쓰기 수를 제한
- 세마포어 획득 타임아웃(STAGER_SEM_TIMEOUT_SEC) 추가로 무한 대기 방지
- 일시적 연결 오류에 대해 1회 재시도, 실패 시 isolator로 이관 (기본 isolator 구현 포함)
- BATCH_SIZE는 환경변수로 오버라이드 가능 (기본 100)
- 방어 추가: pool에 executemany가 없으면 DB 호출을 시도하지 않고 즉시 isolator로 이관
- 디버그: flush 시 현재 pool 객체 타입/속성 정보를 DEBUG로 출력
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import threading
import time
from typing import Optional, List, Any

logger = logging.getLogger(__name__)

# 에러 로그 속도 제한 유틸리티 로드 (optional)
_log_error_throttled = None
try:
    _et_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "utils", "error_throttler.py")
    )
    if os.path.isfile(_et_path):
        _et_spec = importlib.util.spec_from_file_location("_error_throttler_stager", _et_path)
        if _et_spec and _et_spec.loader:
            _et_mod = importlib.util.module_from_spec(_et_spec)
            _et_spec.loader.exec_module(_et_mod)
            _log_error_throttled = getattr(_et_mod, "log_error_throttled", None)
except Exception:
    pass

# RateLimitedErrorFilter 폴백 (optional)
_RateLimitedErrorFilter = None
try:
    _lc_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "config", "logging_config.py")
    )
    if os.path.isfile(_lc_path):
        _lc_spec = importlib.util.spec_from_file_location("_logging_config_stager", _lc_path)
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

# BATCH_SIZE는 환경변수로 제어 가능 (기본 100)
BATCH_SIZE = int(os.getenv("STAGER_BATCH_SIZE", os.getenv("BATCH_SIZE", "100")))

# --------------------------
# 동시 DB 쓰기 제한 (프로세스 내부)
# - 환경변수 STAGER_MAX_CONCURRENT_WRITES로 제어 (기본 5)
# - 획득 타임아웃: STAGER_SEM_TIMEOUT_SEC (초, 기본 10s)
# --------------------------
_STAGER_MAX_CONCURRENT_WRITES = int(os.getenv("STAGER_MAX_CONCURRENT_WRITES", "5"))
_STAGER_SEM_TIMEOUT_SEC = float(os.getenv("STAGER_SEM_TIMEOUT_SEC", "10.0"))
# asyncio.BoundedSemaphore는 async context manager 로 사용
_db_write_semaphore = asyncio.BoundedSemaphore(_STAGER_MAX_CONCURRENT_WRITES)


class CandleStager:
    """캔들 데이터를 staging_candles 테이블에 임시 저장합니다."""

    def __init__(self, pool) -> None:
        # pool: TimescaleConnector 인스턴스 또는 유사 객체 (executemany 메서드 보유)
        self._pool = pool
        self._buffer: List[dict] = []
        # 스레드 안전 락: asyncio 이벤트 루프 경계에서 안전하게 사용
        self._lock = threading.Lock()

        # 주기적 flush 관리
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

        # 기본 isolator 설정 (DB 실패 시 rows를 안전하게 보관)
        # 필요 시 외부에서 self.isolator = custom_isolator 로 교체 가능
        self.isolator = getattr(self, "isolator", None) or self._default_isolator

    async def add_candle(self, candle: dict) -> None:
        """버퍼에 캔들을 추가하고 버퍼가 BATCH_SIZE 이상이면 flush를 트리거합니다."""
        should_flush = False
        with self._lock:
            self._buffer.append(candle)
            if len(self._buffer) >= BATCH_SIZE:
                should_flush = True
        if should_flush:
            await self._flush()

    async def flush(self) -> int:
        """버퍼에 남아있는 캔들을 강제로 DB에 저장합니다. 저장된 개수를 반환합니다."""
        return await self._flush()

    async def _flush(self) -> int:
        """실제 배치 INSERT를 수행합니다."""
        # 1) 버퍼에서 rows를 취득 (락 내에서) -> 락 해제 후 DB I/O 수행
        with self._lock:
            if not self._buffer:
                return 0
            # copy buffer -> rows, clear buffer
            buffered = self._buffer[:]
            self._buffer.clear()

        rows = [self._to_row(c) for c in buffered]
        count = len(rows)
        if count == 0:
            return 0

        # 디버그: 현재 pool 객체 타입과 executemany 존재 여부 출력 (문제 추적용)
        try:
            logger.debug(
                "[CandleStager] DEBUG pool type=%s has_executemany=%s repr=%s",
                type(self._pool).__name__ if self._pool is not None else "None",
                hasattr(self._pool, "executemany"),
                repr(self._pool)[:200],
            )
        except Exception:
            logger.debug("[CandleStager] DEBUG pool introspect failed")

        # 방어: pool 객체가 DB 배치 API를 제공하는지 확인 (없으면 isolator로 바로 이관)
        if not hasattr(self._pool, "executemany") or not callable(getattr(self._pool, "executemany")):
            try:
                logger.warning(
                    "[CandleStager] pool executemany 미존재 — isolator로 rows 이관 (count=%d) pool=%s",
                    count,
                    type(self._pool).__name__ if self._pool is not None else "None",
                )
            except Exception:
                logger.warning("[CandleStager] pool executemany 미존재 — isolator로 rows 이관 (count=%d)", count)
            isolator = getattr(self, "isolator", None) or getattr(self, "_move_rows_to_isolator", None)
            if callable(isolator):
                if asyncio.iscoroutinefunction(isolator):
                    await isolator(buffered)
                else:
                    await asyncio.to_thread(isolator, buffered)
                return 0
            else:
                # isolator도 없으면 예외로 끝내서 호출자에게 알림
                raise RuntimeError("CandleStager: no valid DB executemany on pool and no isolator available")

        # 2) SQL 문 (컬럼 개수와 _to_row 반환 튜플 길이 일치해야 함)
        _sql = (
            "INSERT INTO staging_candles"
            " (symbol, timeframe, exchange, time,"
            " open, high, low, close,"
            " volume, quote_volume, trade_count,"
            " is_complete, seq)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )

        # 3) DB 삽입: to_thread로 실행 (동기 DB 드라이버 사용)
        #    - 세마포어로 동시 쓰기 수 제어, 타임아웃 적용
        last_exc = None
        for attempt in (1, 2):  # attempt 1, then 2 (한 번 재시도)
            try:
                # 세마포어 획득 with timeout to avoid indefinite blocking
                try:
                    await asyncio.wait_for(_db_write_semaphore.acquire(), timeout=_STAGER_SEM_TIMEOUT_SEC)
                except asyncio.TimeoutError:
                    raise RuntimeError(f"[CandleStager] DB write semaphore 획득 타임아웃({_STAGER_SEM_TIMEOUT_SEC}s)")

                try:
                    # run blocking executemany in thread pool
                    await asyncio.to_thread(self._pool.executemany, _sql, rows)
                    logger.info("[CandleStager] ✅ staging_candles 삽입 성공: %d건 (attempt=%d)", count, attempt)
                    return count
                finally:
                    try:
                        _db_write_semaphore.release()
                    except Exception:
                        logger.debug("[CandleStager] 세마포어 해제 실패", exc_info=True)

            except Exception as exc:
                last_exc = exc
                # 간단한 유형 판별: 연결 관련 오류는 재시도 가능
                msg = str(exc).lower()
                is_conn_err = any(
                    k in msg
                    for k in (
                        "connection pointer is null",
                        "connection already closed",
                        "cursor already closed",
                        "could not connect",
                        "connection reset",
                        "broken pipe",
                        "server closed the connection",
                        "connection pool exhausted",
                        "semaphore",
                    )
                )
                logger.warning("[CandleStager] staging_candles 삽입 실패 (attempt=%d): %s", attempt, exc)
                # 에러 스로틀링/로깅
                if _log_error_throttled is not None:
                    _log_error_throttled(logger, "staging_candles_insert_error", f"attempt={attempt} error={exc}")
                else:
                    logger.debug("[CandleStager] exception detail", exc_info=True)

                # 연결 계열 오류면 짧게 대기 후 재시도
                if is_conn_err and attempt < 2:
                    await asyncio.sleep(0.5 * attempt)
                    # try to trigger connector reconnection if possible (best-effort)
                    try:
                        if hasattr(self._pool, "close_all"):
                            try:
                                self._pool.close_all()
                            except Exception:
                                pass
                        if hasattr(self._pool, "connect"):
                            try:
                                await asyncio.to_thread(getattr(self._pool, "connect"))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    continue

                # JSON / 데이터 형식 오류 등은 재시도 의미 없음 -> 즉시 fallback
                break

        # 4) 모든 재시도 실패: isolator로 이관(가능하면) 또는 예외 발생
        try:
            isolator = getattr(self, "isolator", None) or getattr(self, "_move_rows_to_isolator", None)
            if callable(isolator):
                try:
                    if asyncio.iscoroutinefunction(isolator):
                        await isolator(buffered)
                    else:
                        # isolator가 동기 함수인 경우 쓰레드에서 실행하여 이벤트 루프 차이를 피함
                        await asyncio.to_thread(isolator, buffered)
                    logger.info("[CandleStager] rows moved to isolator (count=%d) after failure", count)
                    return 0
                except Exception as e_iso:
                    logger.exception("[CandleStager] isolator move failed: %s", e_iso)
            else:
                logger.error("[CandleStager] No isolator available; rows lost (count=%d)", count)
        except Exception:
            logger.exception("[CandleStager] isolator dispatch unexpected error")

        # 5) 최종적으로 실패를 호출자에게 전달
        if last_exc is not None:
            raise last_exc
        return 0

    async def start_periodic_flush(self, interval_seconds: int = 30):
        """주기적 flush 시작 (기본 30초마다)"""
        if self._running:
            logger.warning("[CandleStager] 주기적 flush가 이미 실행 중입니다")
            return

        self._running = True
        logger.info("[CandleStager] 🚀 주기적 flush 시작 (%d초마다)", interval_seconds)

        try:
            while self._running:
                try:
                    await asyncio.sleep(interval_seconds)
                    with self._lock:
                        buffer_size = len(self._buffer)
                    if buffer_size > 0:
                        logger.info("[CandleStager] 📊 주기적 flush 실행 (버퍼: %d개)", buffer_size)
                        count = await self.flush()
                        logger.info("[CandleStager] ✅ %d개 flush 완료", count)
                    else:
                        logger.debug("[CandleStager] 버퍼 비어있음 - flush 스킵")
                except asyncio.CancelledError:
                    logger.info("[CandleStager] 주기적 flush 취소됨")
                    break
                except Exception as exc:
                    logger.error("[CandleStager] 주기적 flush 에러: %s", exc, exc_info=True)
        finally:
            self._flush_task = None
            logger.info("[CandleStager] 주기적 flush 루프 종료")

    async def stop_periodic_flush(self):
        """주기적 flush 중지 및 마지막 flush 시도"""
        logger.info("[CandleStager] 주기적 flush 중지 시작...")
        self._running = False

        if self._flush_task:
            try:
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.debug("[CandleStager] _flush_task cancel/await failed", exc_info=True)
            finally:
                self._flush_task = None

        # 마지막 flush
        with self._lock:
            buffer_size = len(self._buffer)
        if buffer_size > 0:
            logger.info("[CandleStager] 종료 전 마지막 flush (%d개)", buffer_size)
            try:
                count = await self.flush()
                logger.info("[CandleStager] ✅ 마지막 flush 완료: %d개", count)
            except Exception:
                logger.exception("[CandleStager] 종료 전 마지막 flush 실패", exc_info=True)

        logger.info("[CandleStager] 주기적 flush 중지 완료")

    @staticmethod
    def _to_row(c: dict) -> tuple:
        """
        입력 candle dict를 DB 파라미터 튜플로 변환합니다.
        - dict/list 등 복합 타입은 json.dumps로 안전 직렬화합니다.
        - None 값은 그대로 전달하여 파라미터 바인딩에서 NULL로 처리되도록 합니다.
        """
        def _safe(v: Any) -> Any:
            if v is None:
                return None
            if isinstance(v, (str, int, float, bool)):
                return v
            try:
                return json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)
            except Exception:
                try:
                    return str(v)
                except Exception:
                    return None

        return (
            _safe(c.get("symbol")),
            _safe(c.get("timeframe", "1m")),
            _safe(c.get("exchange", "upbit")),
            _safe(c.get("time")),
            _safe(c.get("open")),
            _safe(c.get("high")),
            _safe(c.get("low")),
            _safe(c.get("close")),
            _safe(c.get("volume", 0)),
            _safe(c.get("quote_volume", 0)),
            _safe(c.get("trade_count", 0)),
            _safe(c.get("is_complete", False)),
            _safe(c.get("seq")),
        )

    def pending_count(self) -> int:
        """버퍼에 대기 중인 캔들 수를 반환합니다."""
        with self._lock:
            return len(self._buffer)

    # --------------------------
    # 기본 isolator 구현
    # --------------------------
    def _default_isolator(self, rows: list) -> None:
        """
        기본 isolator (동기).
        DB 삽입 실패 시 rows를 로컬 JSONL 파일에 append 저장합니다.
        - 동기 함수로 구현되어 asyncio.to_thread나 직접 호출 모두 안전.
        - 파일 경로: ./data/isolated_candles/YYYYMMDD_isolated.jsonl
        """
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "isolated_candles"))
            os.makedirs(base_dir, exist_ok=True)

            fname = time.strftime("%Y%m%d") + "_isolated.jsonl"
            path = os.path.join(base_dir, fname)

            with open(path, "a", encoding="utf-8") as fh:
                for r in rows:
                    try:
                        # r may be tuple/list of primitives / json strings
                        if isinstance(r, (tuple, list)):
                            serializable = []
                            for v in r:
                                # 이미 문자열(직렬화된 JSON)인 경우는 그대로 사용
                                if isinstance(v, str):
                                    serializable.append(v)
                                else:
                                    try:
                                        # ensure it's JSON serializable; use json.dumps then json.loads to normalize
                                        serializable.append(json.loads(json.dumps(v, ensure_ascii=False, default=str)))
                                    except Exception:
                                        serializable.append(str(v))
                        else:
                            # dict or other object
                            try:
                                serializable = json.loads(json.dumps(r, ensure_ascii=False, default=str))
                            except Exception:
                                serializable = str(r)
                        fh.write(json.dumps(serializable, ensure_ascii=False) + "\n")
                    except Exception:
                        logger.exception("[CandleStager] isolator write row failed")
            logger.info("[CandleStager] 기본 isolator에 rows 저장 (count=%d) path=%s", len(rows), path)
        except Exception as e:
            logger.exception("[CandleStager] 기본 isolator 실패: %s", e)

    def _move_rows_to_isolator(self, rows: list) -> None:
        """
        구버전 호출호환용 래퍼 — 내부적으로 기본 isolator를 호출.
        """
        try:
            self._default_isolator(rows)
        except Exception:
            logger.exception("[CandleStager] _move_rows_to_isolator 실패")