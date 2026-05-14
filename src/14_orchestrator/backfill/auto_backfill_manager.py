#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
자동 백필 관리기 (Gap 처리 전담)

Gap 검출 → REST API 백필 → candles 테이블 저장 → gap_fill_queue 상태 갱신
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("auto_backfill_manager")

# ──────────────────────────────────────────────────────────────────────
# Upbit 시간대 상수 — pyupbit get_ohlcv 가 `to` 인자를 naive 문자열로
# 변환하면서 TZ 정보를 떼고 보내므로, 서버는 항상 KST 로 해석한다.
# UTC datetime → KST naive 문자열 변환 시 사용.
# ──────────────────────────────────────────────────────────────────────
_KST = timezone(timedelta(hours=9))

__all__ = ["AutoBackfillManager"]


class AutoBackfillManager:
    """Gap 1건을 처리하는 백필 관리자."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.log = logger or logging.getLogger("auto_backfill_manager")
        # 분류 카운터 — 사이클 처리 중 분기별 결과 집계용 (UI 메시지 명확화).
        # 호출자가 사이클 시작 시 reset_classification() 으로 초기화한다.
        self.classification: Dict[str, int] = {
            "rate_limit_requeued": 0,  # 레이트리밋 추정 → pending 유지(재시도 대기)
            "empty_no_data": 0,        # 데이터 없음 (일시 장애 추정) → failed (retry 가능)
            "no_listing": 0,           # 30일 초과 갭 + 빈 DF → 상장 전 분류 (do_not_retry)
            "exception": 0,            # 처리 중 예외 발생 → failed
            "success": 0,              # 정상 저장 → resolved
        }

    def reset_classification(self) -> None:
        """다음 사이클 시작 전 카운터를 0으로 초기화."""
        for k in self.classification:
            self.classification[k] = 0

    def classification_summary(self) -> str:
        """사용자에게 노출할 한 줄 요약 메시지 (수치 0인 항목 생략)."""
        c = self.classification
        parts: List[str] = []
        if c.get("success", 0) > 0:
            parts.append(f"성공 {c['success']}건")
        if c.get("rate_limit_requeued", 0) > 0:
            parts.append(f"재시도 대기 {c['rate_limit_requeued']}건(레이트리밋)")
        if c.get("empty_no_data", 0) > 0:
            parts.append(f"데이터 없음 {c['empty_no_data']}건")
        if c.get("no_listing", 0) > 0:
            parts.append(f"상장 전 {c['no_listing']}건(do_not_retry)")
        if c.get("exception", 0) > 0:
            parts.append(f"예외 {c['exception']}건")
        return ", ".join(parts) if parts else "처리 결과 없음"

    @staticmethod
    def _gap_age_days(start: Any) -> Optional[float]:
        """gap_start 시각이 현재(UTC)로부터 몇 일 전인지 계산. 실패 시 None."""
        try:
            dt = AutoBackfillManager._to_utc_datetime(start)
            if dt is None:
                return None
            now = datetime.now(timezone.utc)
            return (now - dt).total_seconds() / 86400.0
        except Exception:
            return None

    @staticmethod
    def _to_utc_datetime(value: Any) -> Optional[datetime]:
        """입력 시간을 UTC aware datetime으로 정규화합니다."""
        try:
            if value is None:
                return None
            if isinstance(value, datetime):
                dt = value
            elif isinstance(value, (int, float)):
                ts = float(value)
                if ts > 1e12:
                    ts = ts / 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(value, str):
                s = value.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                try:
                    dt = datetime.fromisoformat(s)
                except Exception:
                    dt = datetime.fromtimestamp(float(s), tz=timezone.utc)
            elif hasattr(value, "to_pydatetime"):
                dt = value.to_pydatetime()
            else:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            return None

    async def _process_one_gap(self, gap: Dict) -> bool:
        """
        Gap 1건 처리 (백필 → 검증 → candles 저장)

        Args:
            gap: Gap 정보 (symbol, gap_start, gap_end, gap_seconds)

        Returns:
            bool: 처리 성공 여부
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")

        try:
            self.log.info("[AutoBackfill] Gap 처리 시작: %s (%s ~ %s)", symbol, start, end)

            # 1단계: Upbit REST API로 캔들 조회
            fetch_result = await self._fetch_candles(symbol=symbol, start=start, end=end, interval=timeframe)
            if isinstance(fetch_result, tuple):
                candles, last_error_kind = fetch_result
            else:  # 호환성: 과거 형태(list만 반환) 대비
                candles, last_error_kind = fetch_result, None

            if not candles:
                # 레이트리밋/네트워크 추정 시 'pending' 유지 + retry_count 증가 (재큐)
                if last_error_kind == "rate_limit":
                    self.log.warning(
                        "[AutoBackfill] %s/%s: 레이트리밋 추정 — 재시도 큐로 유지", symbol, timeframe,
                    )
                    await self._requeue_pending(gap, "rate_limit")
                    self.classification["rate_limit_requeued"] = (
                        self.classification.get("rate_limit_requeued", 0) + 1
                    )
                    return False
                # 빈 결과 — 갭 연령에 따라 분류:
                #  • 30일 초과 갭 + 빈 DF: 상장 전(또는 상장 폐지) 가능성 높음
                #    → do_not_retry=true 로 마킹하여 재큐잉 차단
                #  • 30일 이내 갭 + 빈 DF: 일시 장애 가능성 → 일반 failed (retry_count 누적)
                gap_age_days = self._gap_age_days(start)
                if gap_age_days is not None and gap_age_days > 30:
                    self.log.warning(
                        "[AutoBackfill] %s/%s: 30일 초과 갭에서 데이터 없음 — 상장 전으로 분류(do_not_retry)",
                        symbol, timeframe,
                    )
                    await self._update_queue_status(
                        gap, "failed", "백필 데이터 없음 (30일 초과 — 상장 전 추정)", 0,
                        do_not_retry=True,
                    )
                    self.classification["no_listing"] = (
                        self.classification.get("no_listing", 0) + 1
                    )
                else:
                    self.log.warning("[AutoBackfill] %s: 백필 데이터 없음", symbol)
                    await self._update_queue_status(gap, "failed", "백필 데이터 없음", 0)
                    self.classification["empty_no_data"] = (
                        self.classification.get("empty_no_data", 0) + 1
                    )
                return False

            # 2단계: candles 테이블 저장
            success_count = await self._write_candles(candles)

            # 3단계: gap_fill_queue 상태 업데이트
            await self._update_queue_status(gap, "resolved", None, success_count)

            self.log.info(
                "[AutoBackfill] Gap 처리 완료: %s (%d개 캔들 저장)", symbol, success_count
            )
            self.classification["success"] = (
                self.classification.get("success", 0) + 1
            )
            return True

        except Exception as e:
            self.log.error(
                "[AutoBackfill] Gap 처리 실패: %s - %s", symbol, e, exc_info=True
            )
            try:
                await self._update_queue_status(gap, "failed", str(e)[:500], 0)
            except Exception:
                pass
            self.classification["exception"] = (
                self.classification.get("exception", 0) + 1
            )
            return False

    async def _fetch_candles(
        self,
        symbol: str,
        start: Any,
        end: Any,
        interval: str = "1m",
        count: int = 200,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Upbit REST API에서 캔들 데이터 조회

        Returns:
            (candles, last_error_kind):
              - candles: 캔들 데이터 목록
              - last_error_kind: None | "rate_limit" | "network" — 빈 결과의 원인 분류
                (호출부에서 재큐 vs failed 구분에 사용)
        """
        # 글로벌 limiter / 백오프 유틸 — 공통 모듈에서 로드 (실패 시 무시)
        try:
            import importlib.util
            import pathlib
            import sys
            _arl_base = pathlib.Path(__file__).resolve().parents[2]
            _arl_path = _arl_base / "02_data" / "collectors" / "async_rate_limiter.py"
            _arl_mod = sys.modules.get("_async_rate_limiter")
            if _arl_mod is None and _arl_path.exists():
                _spec = importlib.util.spec_from_file_location("_async_rate_limiter", str(_arl_path))
                if _spec and _spec.loader:
                    _arl_mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_async_rate_limiter"] = _arl_mod
                    _spec.loader.exec_module(_arl_mod)
            get_limiter = getattr(_arl_mod, "get_global_upbit_rate_limiter", None) if _arl_mod else None
            is_rl_error = getattr(_arl_mod, "is_rate_limit_error", None) if _arl_mod else None
            backoff_seq = getattr(_arl_mod, "rate_limit_backoff_delays", None) if _arl_mod else None
        except Exception:
            get_limiter = is_rl_error = backoff_seq = None

        last_error_kind: Optional[str] = None

        try:
            try:
                import aiopyupbit  # type: ignore
            except Exception:
                self.log.warning("[AutoBackfill] aiopyupbit 없음 - 캔들 조회 불가")
                return [], "network"

            start_dt = self._to_utc_datetime(start)
            end_dt = self._to_utc_datetime(end)
            if start_dt is None or end_dt is None:
                self.log.warning("[AutoBackfill] 비정상 gap 시간값: start=%s end=%s", start, end)
                return [], None
            if start_dt > end_dt:
                start_dt, end_dt = end_dt, start_dt

            interval_to_upbit = {
                "1m": "minute1",
                "5m": "minute5",
                "15m": "minute15",
                "1h": "minute60",
                "4h": "minute240",
                "1d": "day",
            }
            upbit_interval = interval_to_upbit.get(str(interval), "minute1")
            max_count = max(1, min(int(count), 200))

            limiter = get_limiter() if callable(get_limiter) else None
            backoffs = tuple(backoff_seq()) if callable(backoff_seq) else (0.5, 1.0, 2.0, 4.0)

            candles: List[Dict[str, Any]] = []
            seen_times = set()
            cursor = end_dt + timedelta(seconds=1)
            # ──────────────────────────────────────────────────────────────
            # 🔧 [근본 원인 수정 — 5번의 시도가 모두 실패한 이유]
            # pyupbit `get_ohlcv` 는 `to` 인자를 받으면 내부에서
            #   pd.to_datetime(to).to_pydatetime() → strftime("%Y-%m-%d %H:%M:%S")
            # 로 **TZ 정보를 떼고 naive 문자열**로 Upbit 서버에 전송한다.
            # Upbit 서버는 naive 시각을 **KST 로 해석**하므로, UTC `cursor` 를
            # 그대로 보내면 서버가 +9 시간 미래로 인식하여 모든 심볼에서
            # 빈 DataFrame 이 반환된다.
            # → 따라서 cursor 를 KST 로 변환한 뒤 naive 형식으로 전달해야 한다.
            # 모듈 상수 `_KST` 사용 (파일 상단 정의).
            # 참조: pyupbit/quotation_api.py get_ohlcv() 의 to 처리 로직
            # ──────────────────────────────────────────────────────────────
            # max_pages: SSOT(`backfill_scheduler.performance.max_pages_per_gap`)
            # → 환경변수 → 기본 100. UI 다이얼로그에서 10~500 범위 내 조정 가능.
            try:
                from .performance_settings import get_max_pages_per_gap
                max_pages = int(get_max_pages_per_gap())
            except Exception:
                max_pages = 100
            max_pages = max(10, min(max_pages, 500))

            for _ in range(max_pages):
                # cursor(UTC) → KST 변환 후 naive 문자열로 전달 (Upbit 서버는 KST 해석)
                cursor_kst = cursor.astimezone(_KST)
                to_str = cursor_kst.strftime("%Y-%m-%d %H:%M:%S")

                # 글로벌 레이트리밋 + 지수 백오프 재시도
                df = None
                page_error_kind: Optional[str] = None
                for attempt in range(len(backoffs) + 1):
                    if limiter is not None:
                        await limiter.acquire()
                    try:
                        df = await aiopyupbit.get_ohlcv(
                            symbol,
                            interval=upbit_interval,
                            to=to_str,
                            count=max_count,
                        )
                        page_error_kind = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        if callable(is_rl_error) and is_rl_error(exc) and attempt < len(backoffs):
                            delay = backoffs[attempt]
                            self.log.info(
                                "[AutoBackfill] %s/%s 레이트리밋 감지 — %.1fs 후 재시도(%d/%d)",
                                symbol, interval, delay, attempt + 1, len(backoffs),
                            )
                            await asyncio.sleep(delay)
                            page_error_kind = "rate_limit"
                            continue
                        self.log.debug(
                            "[AutoBackfill] %s/%s get_ohlcv 예외: %s", symbol, interval, exc
                        )
                        page_error_kind = "rate_limit" if (callable(is_rl_error) and is_rl_error(exc)) else "network"
                        df = None
                        break

                if df is None or getattr(df, "empty", True):
                    if page_error_kind is not None:
                        last_error_kind = page_error_kind
                    break

                earliest: Optional[datetime] = None
                for idx, row in df.iterrows():
                    candle_time = self._to_utc_datetime(idx)
                    if candle_time is None:
                        continue
                    if candle_time < start_dt or candle_time > end_dt:
                        continue
                    key = candle_time.isoformat()
                    if key in seen_times:
                        continue
                    seen_times.add(key)
                    candles.append(
                        {
                            "symbol": symbol,
                            "timeframe": str(interval),
                            "time": candle_time,
                            "open": float(row.get("open", 0.0)),
                            "high": float(row.get("high", 0.0)),
                            "low": float(row.get("low", 0.0)),
                            "close": float(row.get("close", 0.0)),
                            "volume": float(row.get("volume", 0.0)),
                            "quote_volume": float(row.get("value", 0.0)),
                            "trade_count": int(row.get("trade_count", 0) or 0),
                            "is_complete": True,
                            "exchange": "upbit",
                        }
                    )
                    if earliest is None or candle_time < earliest:
                        earliest = candle_time

                if earliest is None or earliest <= start_dt:
                    break
                cursor = earliest - timedelta(seconds=1)

            candles.sort(key=lambda x: x.get("time"))
            return candles, last_error_kind
        except Exception as e:
            self.log.error("[AutoBackfill] 캔들 조회 실패: %s", e)
            kind = "rate_limit" if (callable(is_rl_error) and is_rl_error(e)) else "network"
            return [], kind

    async def _write_candles(self, candles: List[Dict[str, Any]]) -> int:
        """
        candles 테이블에 직접 저장 (CandleWriter 사용)

        Returns:
            int: 저장 성공 건수
        """
        if not candles:
            return 0
        try:
            import importlib.util
            import pathlib
            import sys

            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "02_data" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None
            if TimescaleConnector is None:
                self.log.warning("[AutoBackfill] TimescaleConnector 없음 - 캔들 저장 불가")
                return 0

            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                self.log.warning("[AutoBackfill] TimescaleDB 연결 실패 - 캔들 저장 불가")
                return 0

            grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for candle in candles:
                sym = str(candle.get("symbol", ""))
                tf = str(candle.get("timeframe", "1m"))
                if not sym:
                    continue
                grouped.setdefault((sym, tf), []).append(candle)

            success_count = 0
            for (sym, tf), items in grouped.items():
                try:
                    inserted = conn.write_candles(sym, tf, items, exchange="upbit")
                    success_count += int(inserted or 0)
                except Exception as e:
                    self.log.debug("[AutoBackfill] write_candles 실패 (%s/%s): %s", sym, tf, e)
            return success_count
        except Exception as e:
            self.log.error("[AutoBackfill] 캔들 쓰기 실패: %s", e)
            return 0

    async def _update_queue_status(
        self,
        gap: Dict,
        status: str,
        error_message: Optional[str],
        filled_candles: int,
        do_not_retry: bool = False,
    ) -> None:
        """gap_fill_queue 테이블 상태 업데이트.

        Args:
            do_not_retry: True 면 do_not_retry=true 로 마킹하여 GapFinder 가
                동일 (symbol, timeframe, gap_start) 갭을 다시 큐에 넣지 못하게 한다.
                (상장 전/폐지 추정 시 사용)
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")

        try:
            import importlib.util, pathlib, sys
            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "02_data" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None

            if TimescaleConnector is None:
                return

            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return

            if status == "resolved":
                sql = (
                    "UPDATE gap_fill_queue "
                    "SET status = 'resolved', resolved_at = NOW(), filled_candles = %s "
                    "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                )
                params = (filled_candles, symbol, timeframe, start, end)
            else:
                # do_not_retry=true 인 경우 컬럼이 존재하면 함께 업데이트.
                # (구 스키마에서 컬럼 부재 시 예외 → 폴백으로 컬럼 없이 재시도)
                if do_not_retry:
                    sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s, do_not_retry = TRUE "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                else:
                    sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                params = (error_message, symbol, timeframe, start, end)

            try:
                with conn.conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.conn.commit()
            except Exception as ie:
                # do_not_retry 컬럼이 없는 구 스키마 폴백 (psycopg2 UndefinedColumn 우선 검사,
                # 라이브러리 가용성 차이를 고려해 문자열 매칭도 보조 신호로 사용)
                _is_undefined_column = False
                try:
                    import psycopg2.errors as _pgerr  # type: ignore
                    if isinstance(ie, _pgerr.UndefinedColumn):  # type: ignore[attr-defined]
                        _is_undefined_column = True
                except Exception:
                    pass
                if not _is_undefined_column:
                    # 폴백 신호: pgcode '42703' 또는 메시지에 컬럼명 포함
                    pgcode = getattr(ie, "pgcode", None)
                    if pgcode == "42703" or "do_not_retry" in str(ie):
                        _is_undefined_column = True
                if do_not_retry and _is_undefined_column:
                    try:
                        conn.conn.rollback()
                    except Exception:
                        pass
                    fb_sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                    with conn.conn.cursor() as cur:
                        cur.execute(fb_sql, params)
                    conn.conn.commit()
                    self.log.debug(
                        "[AutoBackfill] do_not_retry 컬럼 미존재 — 일반 failed 폴백 (00_schema.sql 마이그레이션 필요)"
                    )
                else:
                    raise
        except Exception as e:
            self.log.debug("[AutoBackfill] 큐 상태 업데이트 실패: %s", e)

    async def _requeue_pending(self, gap: Dict, reason: str) -> None:
        """레이트리밋/일시 장애로 빈 결과가 나온 gap 을 'pending' 으로 유지하고
        ``retry_count`` 를 1 증가시킨다. 다음 스케줄러 사이클에서 재시도된다.

        Args:
            gap: gap 정보
            reason: 재큐 사유 (error_message 에 기록)
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")
        try:
            import importlib.util
            import pathlib
            import sys
            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "02_data" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None
            if TimescaleConnector is None:
                return
            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return

            sql = (
                "UPDATE gap_fill_queue "
                "SET status = 'pending', "
                "    retry_count = COALESCE(retry_count, 0) + 1, "
                "    error_message = %s "
                "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
            )
            params = (f"requeued: {reason}", symbol, timeframe, start, end)
            with conn.conn.cursor() as cur:
                cur.execute(sql, params)
            conn.conn.commit()
        except Exception as e:
            self.log.debug("[AutoBackfill] 큐 재큐 실패: %s", e)
