# -*- coding: utf-8 -*-
"""
src/data_01/pipeline/finalizer.py
Stage 6: candles UPSERT (TimescaleDB)

?덉쟾 蹂닿컯:
- DB 硫붿꽌???몄텧 寃곌낵媛 coroutine/awaitable ?먮뒗 ?숆린媛?list ????寃쎌슦 紐⑤몢 ?덉쟾?섍쾶 泥섎━?섎뒗 ?ы띁瑜?異붽?.
- staging_candles ?뚮옒洹??낅뜲?댄듃 遺遺꾩쓣 ?щ윭 ?쒕씪?대쾭(pyscopg2, asyncpg ????留욊쾶 諛⑹뼱?곸쑝濡?泥섎━.
- SELECT->UPSERT 留ㅽ븨?먯꽌 ?쒗뵆 ?몃뜳??留ㅼ묶 ?ㅻ쪟瑜??뺤젙.
- 湲곗〈 濡쒖쭅怨??쒓렇?덉쿂??蹂寃쏀븯吏 ?딆쓬.
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
    """諛쏆? 媛믪씠 awaitable?대㈃ await?댁꽌 寃곌낵 諛섑솚, ?꾨땲硫?洹몃?濡?諛섑솚."""
    try:
        if inspect.isawaitable(result):
            return await result
    except Exception:
        # ?대뼡 ?쒕씪?대쾭?먯꽌 await???ㅽ뙣?섎㈃ ?덉쇅瑜??곸쐞?먯꽌 泥섎━?섎룄濡??щ컻??
        raise
    return result


async def _call_maybe_await(func, *args, **kwargs):
    """?⑥닔 ?몄텧 ??諛섑솚媛믪씠 awaitable?대㈃ await?댁꽌 諛섑솚, ?꾨땲硫?洹몃?濡?諛섑솚."""
    res = func(*args, **kwargs)
    return await _maybe_await(res)


class CandlesFinalizer:
    """寃利앸맂 罹붾뱾??TimescaleDB candles ?뚯씠釉붿뿉 UPSERT?⑸땲??"""

    def __init__(self, pool, flush_interval_seconds: int = 60) -> None:
        """
        Args:
            pool: asyncpg 而ㅻ꽖??? ?먮뒗 TimescaleConnector ?먮뒗 ?좎궗 媛앹껜
            flush_interval_seconds: 二쇨린??flush 媛꾧꺽 (湲곕낯 60珥?
        """
        self._pool = pool
        self._flush_interval = flush_interval_seconds
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_periodic_flush(self) -> None:
        """二쇨린??flush ?쒖옉 (諛깃렇?쇱슫???쒖뒪??"""
        if self._running:
            logger.warning("[CandlesFinalizer] ?대? 二쇨린??flush ?ㅽ뻾 以?)
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("[CandlesFinalizer] 二쇨린??flush ?쒖옉 (interval=%ds)", self._flush_interval)

    async def stop_periodic_flush(self) -> None:
        """二쇨린??flush 以묒? 諛??섎㉧吏 ?곗씠??理쒖쥌 flush"""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except (asyncio.CancelledError, Exception):
                pass
        # ?⑥? staging ?곗씠??理쒖쥌 flush
        try:
            await self.flush_all_staging()
        except Exception as exc:
            logger.warning("[CandlesFinalizer] 醫낅즺 ??理쒖쥌 flush ?ㅽ뙣: %s", exc)
        logger.info("[CandlesFinalizer] 二쇨린??flush 以묒?")

    async def _flush_loop(self) -> None:
        """二쇨린??flush 猷⑦봽 (諛깃렇?쇱슫??"""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                flushed = await self.flush_staging()
                if flushed > 0:
                    logger.info("[CandlesFinalizer] 二쇨린??flush ?꾨즺: %d嫄?, flushed)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[CandlesFinalizer] 二쇨린??flush ?ㅽ뙣: %s", exc, exc_info=True)

    async def upsert_candle(self, candle: dict) -> None:
        """?④굔 罹붾뱾??UPSERT?⑸땲??"""
        if self._pool is None:
            raise RuntimeError("No pool configured for CandlesFinalizer")
        exec_fn = getattr(self._pool, "execute", None)
        if exec_fn is None:
            raise RuntimeError("Pool has no execute() method")
        # _UPSERT_SQL + positional params: ?ㅼ뼇???쒕씪?대쾭瑜?connector媛 泥섎━?섎룄濡??꾩엫
        await _call_maybe_await(exec_fn, _UPSERT_SQL, *self._to_row(candle))

    async def upsert_candles(self, candles: Iterable[dict]) -> int:
        """
        罹붾뱾 諛곗튂瑜?UPSERT?⑸땲??
        ??λ맂 媛쒖닔瑜?諛섑솚?⑸땲??
        """
        rows = [self._to_row(c) for c in candles]
        if not rows:
            return 0
        em_fn = getattr(self._pool, "executemany", None)
        if em_fn is None:
            # ?대갚: ?щ윭媛쒕? 猷⑦봽 ?뚮ŉ 媛쒕퀎 upsert
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
            logger.debug("[CandlesFinalizer] candles UPSERT(媛쒕퀎 ?대갚): %d嫄?, count)
            return count
        # executemany 媛 ?덉쑝硫??덉쟾 ?몄텧
        await _call_maybe_await(em_fn, _UPSERT_SQL, rows)
        logger.debug("[CandlesFinalizer] candles UPSERT (executemany) : %d嫄?, len(rows))
        return len(rows)

    async def flush_staging(self, pool=None) -> int:
        """
        staging_candles ??candles UPSERT ??泥섎━ ?꾨즺 ?뚮옒洹몃? ?낅뜲?댄듃?⑸땲??
        ??λ맂 媛쒖닔瑜?諛섑솚?⑸땲?? (理쒕? 1000嫄댁뵫 泥섎━)
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
                    logger.error("[CandlesFinalizer] Pool??fetch/fetchall/execute 硫붿꽌???놁쓬")
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles 議고쉶 ?ㅽ뙣: %s", exc, exc_info=True)
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
                    logger.error("[CandlesFinalizer] 議고쉶 寃곌낵 ?뺤떇 泥섎━ 遺덇?: %s", type(rows))
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] 議고쉶 寃곌낵 蹂???ㅽ뙣: %s", exc, exc_info=True)
            return 0

        if not rows:
            return 0

        # prepare values for upsert
        candles: List[Sequence[Any]] = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    # dict-like: ?ъ슜 ??湲곗??쇰줈 ?덉쟾?섍쾶 異붿텧
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
                    # tuple-like: SELECT ?쒖꽌??留욎떠 ?몃뜳??留ㅽ븨 (二쇱쓽: SELECT?먯꽌 id媛 留??욎뿉 ?덉쓬)
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
            logger.error("[CandlesFinalizer] 議고쉶 ?덉퐫???뚯떛 ?ㅽ뙣: %s", exc, exc_info=True)
            return 0

        # 2) executemany / upsert
        try:
            em_fn = getattr(p, "executemany", None)
            if em_fn:
                await _call_maybe_await(em_fn, _UPSERT_SQL, candles)
            else:
                # ?대갚: 媛쒕퀎 upsert
                for row_vals in candles:
                    try:
                        exec_fn = getattr(p, "execute", None)
                        if exec_fn:
                            # exec_fn may accept query + params (psycopg2) or positional args (asyncpg)
                            await _call_maybe_await(exec_fn, _UPSERT_SQL, *row_vals)
                        else:
                            raise RuntimeError("Pool has no executemany/execute to perform upsert")
                    except Exception as exc_inner:
                        logger.debug("[CandlesFinalizer] 媛쒕퀎 upsert ?ㅽ뙣(臾댁떆): %s", exc_inner)
        except Exception as exc:
            logger.error("[CandlesFinalizer] candles UPSERT ?ㅽ뙣: %s", exc, exc_info=True)
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
                # ids 鍮꾩뼱?덉? ?딆쓣 ?뚮쭔 泥섎━
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
                        logger.debug("[CandlesFinalizer] staging processed ?낅뜲?댄듃 (psycopg2 ANY(%s) 諛⑹떇) ?깃났")
                    except Exception as e1:
                        last_exc = e1
                        logger.debug("[CandlesFinalizer] psycopg2 諛⑹떇?쇰줈 ?낅뜲?댄듃 ?ㅽ뙣: %s", e1, exc_info=True)

                    if not updated:
                        # 2) asyncpg / $1 style - try passing ids directly and as single-element tuple
                        try:
                            await _call_maybe_await(exec_fn, q_dollar, ids)  # many asyncpg variants accept list as direct param
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?낅뜲?댄듃 (asyncpg $1 with ids) ?깃났")
                        except Exception as e2:
                            last_exc = e2
                            logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, ids) ?ㅽ뙣: %s", e2, exc_info=True)
                            # try (ids,)
                            try:
                                await _call_maybe_await(exec_fn, q_dollar, (ids,))
                                updated = True
                                logger.debug("[CandlesFinalizer] staging processed ?낅뜲?댄듃 (asyncpg $1 with (ids,)) ?깃났")
                            except Exception as e2b:
                                last_exc = e2b
                                logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, (ids,)) ?ㅽ뙣: %s", e2b, exc_info=True)

                    if not updated:
                        # 3) Expand to IN(...) and pass flat params tuple
                        try:
                            placeholders = ",".join(["%s"] * len(ids))
                            q_in = f"UPDATE staging_candles SET processed = TRUE WHERE id IN ({placeholders})"
                            await _call_maybe_await(exec_fn, q_in, tuple(ids))
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?낅뜲?댄듃 (IN ?뺤옣) ?깃났")
                        except Exception as e3:
                            last_exc = e3
                            logger.debug("[CandlesFinalizer] IN ?뺤옣 ?낅뜲?댄듃 ?ㅽ뙣: %s", e3, exc_info=True)

                else:
                    # exec_fn ?놁쓬: try executemany or fallback per id update
                    upd_fn = getattr(p, "executemany", None)
                    if upd_fn:
                        try:
                            q_single = "UPDATE staging_candles SET processed = TRUE WHERE id = %s"
                            params = [(i,) for i in ids]
                            await _call_maybe_await(upd_fn, q_single, params)
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?낅뜲?댄듃 (executemany per-id) ?깃났")
                        except Exception as e_execmany:
                            last_exc = e_execmany
                            logger.debug("[CandlesFinalizer] executemany per-id ?ㅽ뙣: %s", e_execmany, exc_info=True)
                    if not updated:
                        # 留덉?留??섎떒: 媛쒕퀎 ?낅뜲?댄듃 ?몄텧
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
                    # 理쒖쥌 ?ㅽ뙣 濡쒓렇
                    logger.error("[CandlesFinalizer] staging_candles ?뚮옒洹??낅뜲?댄듃 理쒖쥌 ?ㅽ뙣: %s", last_exc, exc_info=True)

        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles ?뚮옒洹??낅뜲?댄듃 ?ㅽ뙣: %s", exc, exc_info=True)

        logger.info("[CandlesFinalizer] staging ??candles ?닿?: %d嫄?, len(rows))
        return len(rows)

    async def flush_all_staging(self, pool=None) -> int:
        """
        staging_candles 誘몄쿂由??곗씠???꾩껜瑜?candles濡??닿??⑸땲??
        ??λ맂 珥?媛쒖닔瑜?諛섑솚?⑸땲??
        """
        total = 0
        while True:
            flushed = await self.flush_staging(pool=pool)
            if not flushed:
                break
            total += flushed
        if total:
            logger.info("[CandlesFinalizer] ?꾩껜 staging flush ?꾨즺: %d嫄?, total)
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
