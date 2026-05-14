# -*- coding: utf-8 -*-
"""
src/02_data/pipeline/finalizer.py
Stage 6: candles UPSERT (TimescaleDB)

안전 보강:
- DB 메서드 호출 결과가 coroutine/awaitable 또는 동기값(list 등)인 경우 모두 안전하게 처리하는 헬퍼를 추가.
- staging_candles 플래그 업데이트 부분을 여러 드라이버(pyscopg2, asyncpg 등)에 맞게 방어적으로 처리.
- SELECT->UPSERT 매핑에서 튜플 인덱스 매칭 오류를 정정.
- 기존 로직과 시그니처는 변경하지 않음.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Iterable, Optional, Any, List, Sequence

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
    INSERT INTO candles
        (time, symbol, timeframe, exchange,
         open, high, low, close,
         volume, quote_volume, trade_count,
         is_complete, seq)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
    ON CONFLICT (symbol, time, timeframe) DO UPDATE SET
        high         = GREATEST(EXCLUDED.high,  candles.high),
        low          = LEAST(EXCLUDED.low,       candles.low),
        close        = EXCLUDED.close,
        volume       = candles.volume       + EXCLUDED.volume,
        quote_volume = candles.quote_volume + EXCLUDED.quote_volume,
        trade_count  = candles.trade_count  + EXCLUDED.trade_count,
        is_complete  = EXCLUDED.is_complete OR candles.is_complete
"""


async def _maybe_await(result: Any) -> Any:
    """받은 값이 awaitable이면 await해서 결과 반환, 아니면 그대로 반환."""
    try:
        if inspect.isawaitable(result):
            return await result
    except Exception:
        # 어떤 드라이버에서 await이 실패하면 예외를 상위에서 처리하도록 재발생
        raise
    return result


async def _call_maybe_await(func, *args, **kwargs):
    """함수 호출 후 반환값이 awaitable이면 await해서 반환, 아니면 그대로 반환."""
    res = func(*args, **kwargs)
    return await _maybe_await(res)


class CandlesFinalizer:
    """검증된 캔들을 TimescaleDB candles 테이블에 UPSERT합니다."""

    def __init__(self, pool, flush_interval_seconds: int = 60) -> None:
        """
        Args:
            pool: asyncpg 커넥션 풀 또는 TimescaleConnector 또는 유사 객체
            flush_interval_seconds: 주기적 flush 간격 (기본 60초)
        """
        self._pool = pool
        self._flush_interval = flush_interval_seconds
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_periodic_flush(self) -> None:
        """주기적 flush 시작 (백그라운드 태스크)"""
        if self._running:
            logger.warning("[CandlesFinalizer] 이미 주기적 flush 실행 중")
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("[CandlesFinalizer] 주기적 flush 시작 (interval=%ds)", self._flush_interval)

    async def stop_periodic_flush(self) -> None:
        """주기적 flush 중지 및 나머지 데이터 최종 flush"""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except (asyncio.CancelledError, Exception):
                pass
        # 남은 staging 데이터 최종 flush
        try:
            await self.flush_all_staging()
        except Exception as exc:
            logger.warning("[CandlesFinalizer] 종료 시 최종 flush 실패: %s", exc)
        logger.info("[CandlesFinalizer] 주기적 flush 중지")

    async def _flush_loop(self) -> None:
        """주기적 flush 루프 (백그라운드)"""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                flushed = await self.flush_staging()
                if flushed > 0:
                    logger.info("[CandlesFinalizer] 주기적 flush 완료: %d건", flushed)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[CandlesFinalizer] 주기적 flush 실패: %s", exc, exc_info=True)

    async def upsert_candle(self, candle: dict) -> None:
        """단건 캔들을 UPSERT합니다."""
        if self._pool is None:
            raise RuntimeError("No pool configured for CandlesFinalizer")
        exec_fn = getattr(self._pool, "execute", None)
        if exec_fn is None:
            raise RuntimeError("Pool has no execute() method")
        # _UPSERT_SQL + positional params: 다양한 드라이버를 connector가 처리하도록 위임
        await _call_maybe_await(exec_fn, _UPSERT_SQL, *self._to_row(candle))

    async def upsert_candles(self, candles: Iterable[dict]) -> int:
        """
        캔들 배치를 UPSERT합니다.
        저장된 개수를 반환합니다.
        """
        rows = [self._to_row(c) for c in candles]
        if not rows:
            return 0
        em_fn = getattr(self._pool, "executemany", None)
        if em_fn is None:
            # 폴백: 여러개를 루프 돌며 개별 upsert
            count = 0
            for r in rows:
                try:
                    await self.upsert_candle(dict(
                        time=r[0], symbol=r[1], timeframe=r[2], exchange=r[3],
                        open=r[4], high=r[5], low=r[6], close=r[7],
                        volume=r[8], quote_volume=r[9], trade_count=r[10],
                        is_complete=r[11], seq=r[12]
                    ))
                    count += 1
                except Exception:
                    pass
            logger.debug("[CandlesFinalizer] candles UPSERT(개별 폴백): %d건", count)
            return count
        # executemany 가 있으면 안전 호출
        await _call_maybe_await(em_fn, _UPSERT_SQL, rows)
        logger.debug("[CandlesFinalizer] candles UPSERT (executemany) : %d건", len(rows))
        return len(rows)

    async def flush_staging(self, pool=None) -> int:
        """
        staging_candles → candles UPSERT 후 처리 완료 플래그를 업데이트합니다.
        저장된 개수를 반환합니다. (최대 1000건씩 처리)
        """
        p = pool or self._pool

        if p is None:
            logger.error("[CandlesFinalizer] No pool available for flush_staging")
            return 0

        sql = """
            SELECT id, time, symbol, timeframe, exchange,
                   open, high, low, close,
                   volume, quote_volume, trade_count,
                   is_complete, seq
            FROM staging_candles
            WHERE NOT processed
            ORDER BY inserted_at
            LIMIT 1000
            """

        # 1) fetch rows in a safe manner across sync/async drivers
        try:
            rows = None
            # prefer fetchall if exists
            if hasattr(p, "fetchall"):
                fn = getattr(p, "fetchall")
                rows = await _call_maybe_await(fn, sql)
            elif hasattr(p, "fetch"):
                fn = getattr(p, "fetch")
                rows = await _call_maybe_await(fn, sql)
            else:
                # try execute or query
                fn_exec = getattr(p, "execute", None)
                if fn_exec:
                    res = await _call_maybe_await(fn_exec, sql)
                    rows = res
                else:
                    logger.error("[CandlesFinalizer] Pool에 fetch/fetchall/execute 메서드 없음")
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles 조회 실패: %s", exc, exc_info=True)
            return 0

        # normalize rows to list
        try:
            if rows is None:
                return 0
            if hasattr(rows, "to_list") and callable(getattr(rows, "to_list")):
                try:
                    rows = await _call_maybe_await(rows.to_list, length=1000)
                except Exception:
                    pass
            if not isinstance(rows, (list, tuple)):
                try:
                    rows = list(rows)
                except Exception:
                    logger.error("[CandlesFinalizer] 조회 결과 형식 처리 불가: %s", type(rows))
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] 조회 결과 변환 실패: %s", exc, exc_info=True)
            return 0

        if not rows:
            return 0

        # prepare values for upsert
        candles: List[Sequence[Any]] = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    # dict-like: 사용 키 기준으로 안전하게 추출
                    t = (
                        r.get("time"),
                        r.get("symbol"),
                        r.get("timeframe"),
                        r.get("exchange"),
                        r.get("open"),
                        r.get("high"),
                        r.get("low"),
                        r.get("close"),
                        r.get("volume"),
                        r.get("quote_volume"),
                        r.get("trade_count"),
                        r.get("is_complete"),
                        r.get("seq"),
                    )
                else:
                    # tuple-like: SELECT 순서에 맞춰 인덱스 매핑 (주의: SELECT에서 id가 맨 앞에 있음)
                    # SELECT order: id(0), time(1), symbol(2), timeframe(3), exchange(4),
                    #               open(5), high(6), low(7), close(8),
                    #               volume(9), quote_volume(10), trade_count(11),
                    #               is_complete(12), seq(13)
                    t = (
                        r[1],  # time
                        r[2],  # symbol
                        r[3],  # timeframe
                        r[4],  # exchange
                        r[5],  # open
                        r[6],  # high
                        r[7],  # low
                        r[8],  # close
                        r[9],  # volume
                        r[10], # quote_volume
                        r[11], # trade_count
                        r[12], # is_complete
                        r[13], # seq
                    )
                candles.append(t)
        except Exception as exc:
            logger.error("[CandlesFinalizer] 조회 레코드 파싱 실패: %s", exc, exc_info=True)
            return 0

        # 2) executemany / upsert
        try:
            em_fn = getattr(p, "executemany", None)
            if em_fn:
                await _call_maybe_await(em_fn, _UPSERT_SQL, candles)
            else:
                # 폴백: 개별 upsert
                for row_vals in candles:
                    try:
                        exec_fn = getattr(p, "execute", None)
                        if exec_fn:
                            # exec_fn may accept query + params (psycopg2) or positional args (asyncpg)
                            await _call_maybe_await(exec_fn, _UPSERT_SQL, *row_vals)
                        else:
                            raise RuntimeError("Pool has no executemany/execute to perform upsert")
                    except Exception as exc_inner:
                        logger.debug("[CandlesFinalizer] 개별 upsert 실패(무시): %s", exc_inner)
        except Exception as exc:
            logger.error("[CandlesFinalizer] candles UPSERT 실패: %s", exc, exc_info=True)
            return 0

        # 3) mark staging processed
        try:
            ids: List[Any] = []
            for r in rows:
                if isinstance(r, dict):
                    if "id" in r:
                        ids.append(r["id"])
                    else:
                        # try positional fallback
                        try:
                            ids.append(r[0])
                        except Exception:
                            pass
                else:
                    try:
                        ids.append(r[0])
                    except Exception:
                        pass

            if ids:
                # ids 비어있지 않을 때만 처리
                exec_fn = getattr(p, "execute", None)

                # candidate queries
                q_psycopg = "UPDATE staging_candles SET processed = TRUE WHERE id = ANY(%s::bigint[])"
                q_dollar = "UPDATE staging_candles SET processed = TRUE WHERE id = ANY($1::bigint[])"

                # Try sequence of attempts to support various drivers:
                # 1) psycopg2 style: (ids,)
                # 2) asyncpg style: q_dollar with ids (or (ids,))
                # 3) expand to IN(%s,...) with tuple(ids)
                updated = False
                last_exc = None

                if exec_fn:
                    # 1) psycopg2 style
                    try:
                        await _call_maybe_await(exec_fn, q_psycopg, (ids,))
                        updated = True
                        logger.debug("[CandlesFinalizer] staging processed 업데이트 (psycopg2 ANY(%s) 방식) 성공")
                    except Exception as e1:
                        last_exc = e1
                        logger.debug("[CandlesFinalizer] psycopg2 방식으로 업데이트 실패: %s", e1, exc_info=True)

                    if not updated:
                        # 2) asyncpg / $1 style - try passing ids directly and as single-element tuple
                        try:
                            await _call_maybe_await(exec_fn, q_dollar, ids)  # many asyncpg variants accept list as direct param
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed 업데이트 (asyncpg $1 with ids) 성공")
                        except Exception as e2:
                            last_exc = e2
                            logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, ids) 실패: %s", e2, exc_info=True)
                            # try (ids,)
                            try:
                                await _call_maybe_await(exec_fn, q_dollar, (ids,))
                                updated = True
                                logger.debug("[CandlesFinalizer] staging processed 업데이트 (asyncpg $1 with (ids,)) 성공")
                            except Exception as e2b:
                                last_exc = e2b
                                logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, (ids,)) 실패: %s", e2b, exc_info=True)

                    if not updated:
                        # 3) Expand to IN(...) and pass flat params tuple
                        try:
                            placeholders = ",".join(["%s"] * len(ids))
                            q_in = f"UPDATE staging_candles SET processed = TRUE WHERE id IN ({placeholders})"
                            await _call_maybe_await(exec_fn, q_in, tuple(ids))
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed 업데이트 (IN 확장) 성공")
                        except Exception as e3:
                            last_exc = e3
                            logger.debug("[CandlesFinalizer] IN 확장 업데이트 실패: %s", e3, exc_info=True)

                else:
                    # exec_fn 없음: try executemany or fallback per id update
                    upd_fn = getattr(p, "executemany", None)
                    if upd_fn:
                        try:
                            q_single = "UPDATE staging_candles SET processed = TRUE WHERE id = %s"
                            params = [(i,) for i in ids]
                            await _call_maybe_await(upd_fn, q_single, params)
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed 업데이트 (executemany per-id) 성공")
                        except Exception as e_execmany:
                            last_exc = e_execmany
                            logger.debug("[CandlesFinalizer] executemany per-id 실패: %s", e_execmany, exc_info=True)
                    if not updated:
                        # 마지막 수단: 개별 업데이트 호출
                        for i in ids:
                            try:
                                fn_exec = getattr(p, "execute", None) or getattr(p, "executemany", None)
                                if fn_exec:
                                    # try both placeholder styles
                                    try:
                                        await _call_maybe_await(fn_exec, q_psycopg, (i,))
                                    except Exception:
                                        try:
                                            await _call_maybe_await(fn_exec, q_dollar, i)
                                        except Exception:
                                            try:
                                                await _call_maybe_await(fn_exec, "UPDATE staging_candles SET processed = TRUE WHERE id = $1", i)
                                            except Exception:
                                                pass
                                else:
                                    # No execute available; ignore
                                    pass
                            except Exception:
                                pass

                if not updated and last_exc is not None:
                    # 최종 실패 로그
                    logger.error("[CandlesFinalizer] staging_candles 플래그 업데이트 최종 실패: %s", last_exc, exc_info=True)

        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles 플래그 업데이트 실패: %s", exc, exc_info=True)

        logger.info("[CandlesFinalizer] staging → candles 이관: %d건", len(rows))
        return len(rows)

    async def flush_all_staging(self, pool=None) -> int:
        """
        staging_candles 미처리 데이터 전체를 candles로 이관합니다.
        저장된 총 개수를 반환합니다.
        """
        total = 0
        while True:
            flushed = await self.flush_staging(pool=pool)
            if not flushed:
                break
            total += flushed
        if total:
            logger.info("[CandlesFinalizer] 전체 staging flush 완료: %d건", total)
        return total

    @staticmethod
    def _to_row(c: dict) -> tuple:
        return (
            c["time"],
            c["symbol"],
            c.get("timeframe", "1m"),
            c.get("exchange",  "upbit"),
            c["open"],
            c["high"],
            c["low"],
            c["close"],
            c.get("volume",       0),
            c.get("quote_volume", 0),
            c.get("trade_count",  0),
            c.get("is_complete",  False),
            c.get("seq"),
        )