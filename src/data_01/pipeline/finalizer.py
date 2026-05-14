# -*- coding: utf-8 -*-
"""
src/data_01/pipeline/finalizer.py
Stage 6: candles UPSERT (TimescaleDB)

?ˆì „ ë³´ê°•:
- DB ë©”ì„œ???¸ì¶œ ê²°ê³¼ê°€ coroutine/awaitable ?ëŠ” ?™ê¸°ê°?list ????ê²½ìš° ëª¨ë‘ ?ˆì „?˜ê²Œ ì²˜ë¦¬?˜ëŠ” ?¬í¼ë¥?ì¶”ê?.
- staging_candles ?Œëž˜ê·??…ë°?´íŠ¸ ë¶€ë¶„ì„ ?¬ëŸ¬ ?œë¼?´ë²„(pyscopg2, asyncpg ????ë§žê²Œ ë°©ì–´?ìœ¼ë¡?ì²˜ë¦¬.
- SELECT->UPSERT ë§¤í•‘?ì„œ ?œí”Œ ?¸ë±??ë§¤ì¹­ ?¤ë¥˜ë¥??•ì •.
- ê¸°ì¡´ ë¡œì§ê³??œê·¸?ˆì²˜??ë³€ê²½í•˜ì§€ ?ŠìŒ.
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
    """ë°›ì? ê°’ì´ awaitable?´ë©´ await?´ì„œ ê²°ê³¼ ë°˜í™˜, ?„ë‹ˆë©?ê·¸ë?ë¡?ë°˜í™˜."""
    try:
        if inspect.isawaitable(result):
            return await result
    except Exception:
        # ?´ë–¤ ?œë¼?´ë²„?ì„œ await???¤íŒ¨?˜ë©´ ?ˆì™¸ë¥??ìœ„?ì„œ ì²˜ë¦¬?˜ë„ë¡??¬ë°œ??
        raise
    return result


async def _call_maybe_await(func, *args, **kwargs):
    """?¨ìˆ˜ ?¸ì¶œ ??ë°˜í™˜ê°’ì´ awaitable?´ë©´ await?´ì„œ ë°˜í™˜, ?„ë‹ˆë©?ê·¸ë?ë¡?ë°˜í™˜."""
    res = func(*args, **kwargs)
    return await _maybe_await(res)


class CandlesFinalizer:
    """ê²€ì¦ëœ ìº”ë“¤??TimescaleDB candles ?Œì´ë¸”ì— UPSERT?©ë‹ˆ??"""

    def __init__(self, pool, flush_interval_seconds: int = 60) -> None:
        """
        Args:
            pool: asyncpg ì»¤ë„¥???€ ?ëŠ” TimescaleConnector ?ëŠ” ? ì‚¬ ê°ì²´
            flush_interval_seconds: ì£¼ê¸°??flush ê°„ê²© (ê¸°ë³¸ 60ì´?
        """
        self._pool = pool
        self._flush_interval = flush_interval_seconds
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_periodic_flush(self) -> None:
        """ì£¼ê¸°??flush ?œìž‘ (ë°±ê·¸?¼ìš´???œìŠ¤??"""
        if self._running:
            logger.warning("[CandlesFinalizer] ?´ë? ì£¼ê¸°??flush ?¤í–‰ ì¤?)
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("[CandlesFinalizer] ì£¼ê¸°??flush ?œìž‘ (interval=%ds)", self._flush_interval)

    async def stop_periodic_flush(self) -> None:
        """ì£¼ê¸°??flush ì¤‘ì? ë°??˜ë¨¸ì§€ ?°ì´??ìµœì¢… flush"""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except (asyncio.CancelledError, Exception):
                pass
        # ?¨ì? staging ?°ì´??ìµœì¢… flush
        try:
            await self.flush_all_staging()
        except Exception as exc:
            logger.warning("[CandlesFinalizer] ì¢…ë£Œ ??ìµœì¢… flush ?¤íŒ¨: %s", exc)
        logger.info("[CandlesFinalizer] ì£¼ê¸°??flush ì¤‘ì?")

    async def _flush_loop(self) -> None:
        """ì£¼ê¸°??flush ë£¨í”„ (ë°±ê·¸?¼ìš´??"""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                flushed = await self.flush_staging()
                if flushed > 0:
                    logger.info("[CandlesFinalizer] ì£¼ê¸°??flush ?„ë£Œ: %dê±?, flushed)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[CandlesFinalizer] ì£¼ê¸°??flush ?¤íŒ¨: %s", exc, exc_info=True)

    async def upsert_candle(self, candle: dict) -> None:
        """?¨ê±´ ìº”ë“¤??UPSERT?©ë‹ˆ??"""
        if self._pool is None:
            raise RuntimeError("No pool configured for CandlesFinalizer")
        exec_fn = getattr(self._pool, "execute", None)
        if exec_fn is None:
            raise RuntimeError("Pool has no execute() method")
        # _UPSERT_SQL + positional params: ?¤ì–‘???œë¼?´ë²„ë¥?connectorê°€ ì²˜ë¦¬?˜ë„ë¡??„ìž„
        await _call_maybe_await(exec_fn, _UPSERT_SQL, *self._to_row(candle))

    async def upsert_candles(self, candles: Iterable[dict]) -> int:
        """
        ìº”ë“¤ ë°°ì¹˜ë¥?UPSERT?©ë‹ˆ??
        ?€?¥ëœ ê°œìˆ˜ë¥?ë°˜í™˜?©ë‹ˆ??
        """
        rows = [self._to_row(c) for c in candles]
        if not rows:
            return 0
        em_fn = getattr(self._pool, "executemany", None)
        if em_fn is None:
            # ?´ë°±: ?¬ëŸ¬ê°œë? ë£¨í”„ ?Œë©° ê°œë³„ upsert
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
            logger.debug("[CandlesFinalizer] candles UPSERT(ê°œë³„ ?´ë°±): %dê±?, count)
            return count
        # executemany ê°€ ?ˆìœ¼ë©??ˆì „ ?¸ì¶œ
        await _call_maybe_await(em_fn, _UPSERT_SQL, rows)
        logger.debug("[CandlesFinalizer] candles UPSERT (executemany) : %dê±?, len(rows))
        return len(rows)

    async def flush_staging(self, pool=None) -> int:
        """
        staging_candles ??candles UPSERT ??ì²˜ë¦¬ ?„ë£Œ ?Œëž˜ê·¸ë? ?…ë°?´íŠ¸?©ë‹ˆ??
        ?€?¥ëœ ê°œìˆ˜ë¥?ë°˜í™˜?©ë‹ˆ?? (ìµœë? 1000ê±´ì”© ì²˜ë¦¬)
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
                    logger.error("[CandlesFinalizer] Pool??fetch/fetchall/execute ë©”ì„œ???†ìŒ")
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles ì¡°íšŒ ?¤íŒ¨: %s", exc, exc_info=True)
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
                    logger.error("[CandlesFinalizer] ì¡°íšŒ ê²°ê³¼ ?•ì‹ ì²˜ë¦¬ ë¶ˆê?: %s", type(rows))
                    return 0
        except Exception as exc:
            logger.error("[CandlesFinalizer] ì¡°íšŒ ê²°ê³¼ ë³€???¤íŒ¨: %s", exc, exc_info=True)
            return 0

        if not rows:
            return 0

        # prepare values for upsert
        candles: List[Sequence[Any]] = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    # dict-like: ?¬ìš© ??ê¸°ì??¼ë¡œ ?ˆì „?˜ê²Œ ì¶”ì¶œ
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
                    # tuple-like: SELECT ?œì„œ??ë§žì¶° ?¸ë±??ë§¤í•‘ (ì£¼ì˜: SELECT?ì„œ idê°€ ë§??žì— ?ˆìŒ)
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
            logger.error("[CandlesFinalizer] ì¡°íšŒ ?ˆì½”???Œì‹± ?¤íŒ¨: %s", exc, exc_info=True)
            return 0

        # 2) executemany / upsert
        try:
            em_fn = getattr(p, "executemany", None)
            if em_fn:
                await _call_maybe_await(em_fn, _UPSERT_SQL, candles)
            else:
                # ?´ë°±: ê°œë³„ upsert
                for row_vals in candles:
                    try:
                        exec_fn = getattr(p, "execute", None)
                        if exec_fn:
                            # exec_fn may accept query + params (psycopg2) or positional args (asyncpg)
                            await _call_maybe_await(exec_fn, _UPSERT_SQL, *row_vals)
                        else:
                            raise RuntimeError("Pool has no executemany/execute to perform upsert")
                    except Exception as exc_inner:
                        logger.debug("[CandlesFinalizer] ê°œë³„ upsert ?¤íŒ¨(ë¬´ì‹œ): %s", exc_inner)
        except Exception as exc:
            logger.error("[CandlesFinalizer] candles UPSERT ?¤íŒ¨: %s", exc, exc_info=True)
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
                # ids ë¹„ì–´?ˆì? ?Šì„ ?Œë§Œ ì²˜ë¦¬
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
                        logger.debug("[CandlesFinalizer] staging processed ?…ë°?´íŠ¸ (psycopg2 ANY(%s) ë°©ì‹) ?±ê³µ")
                    except Exception as e1:
                        last_exc = e1
                        logger.debug("[CandlesFinalizer] psycopg2 ë°©ì‹?¼ë¡œ ?…ë°?´íŠ¸ ?¤íŒ¨: %s", e1, exc_info=True)

                    if not updated:
                        # 2) asyncpg / $1 style - try passing ids directly and as single-element tuple
                        try:
                            await _call_maybe_await(exec_fn, q_dollar, ids)  # many asyncpg variants accept list as direct param
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?…ë°?´íŠ¸ (asyncpg $1 with ids) ?±ê³µ")
                        except Exception as e2:
                            last_exc = e2
                            logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, ids) ?¤íŒ¨: %s", e2, exc_info=True)
                            # try (ids,)
                            try:
                                await _call_maybe_await(exec_fn, q_dollar, (ids,))
                                updated = True
                                logger.debug("[CandlesFinalizer] staging processed ?…ë°?´íŠ¸ (asyncpg $1 with (ids,)) ?±ê³µ")
                            except Exception as e2b:
                                last_exc = e2b
                                logger.debug("[CandlesFinalizer] asyncpg-style (q_dollar, (ids,)) ?¤íŒ¨: %s", e2b, exc_info=True)

                    if not updated:
                        # 3) Expand to IN(...) and pass flat params tuple
                        try:
                            placeholders = ",".join(["%s"] * len(ids))
                            q_in = f"UPDATE staging_candles SET processed = TRUE WHERE id IN ({placeholders})"
                            await _call_maybe_await(exec_fn, q_in, tuple(ids))
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?…ë°?´íŠ¸ (IN ?•ìž¥) ?±ê³µ")
                        except Exception as e3:
                            last_exc = e3
                            logger.debug("[CandlesFinalizer] IN ?•ìž¥ ?…ë°?´íŠ¸ ?¤íŒ¨: %s", e3, exc_info=True)

                else:
                    # exec_fn ?†ìŒ: try executemany or fallback per id update
                    upd_fn = getattr(p, "executemany", None)
                    if upd_fn:
                        try:
                            q_single = "UPDATE staging_candles SET processed = TRUE WHERE id = %s"
                            params = [(i,) for i in ids]
                            await _call_maybe_await(upd_fn, q_single, params)
                            updated = True
                            logger.debug("[CandlesFinalizer] staging processed ?…ë°?´íŠ¸ (executemany per-id) ?±ê³µ")
                        except Exception as e_execmany:
                            last_exc = e_execmany
                            logger.debug("[CandlesFinalizer] executemany per-id ?¤íŒ¨: %s", e_execmany, exc_info=True)
                    if not updated:
                        # ë§ˆì?ë§??˜ë‹¨: ê°œë³„ ?…ë°?´íŠ¸ ?¸ì¶œ
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
                    # ìµœì¢… ?¤íŒ¨ ë¡œê·¸
                    logger.error("[CandlesFinalizer] staging_candles ?Œëž˜ê·??…ë°?´íŠ¸ ìµœì¢… ?¤íŒ¨: %s", last_exc, exc_info=True)

        except Exception as exc:
            logger.error("[CandlesFinalizer] staging_candles ?Œëž˜ê·??…ë°?´íŠ¸ ?¤íŒ¨: %s", exc, exc_info=True)

        logger.info("[CandlesFinalizer] staging ??candles ?´ê?: %dê±?, len(rows))
        return len(rows)

    async def flush_all_staging(self, pool=None) -> int:
        """
        staging_candles ë¯¸ì²˜ë¦??°ì´???„ì²´ë¥?candlesë¡??´ê??©ë‹ˆ??
        ?€?¥ëœ ì´?ê°œìˆ˜ë¥?ë°˜í™˜?©ë‹ˆ??
        """
        total = 0
        while True:
            flushed = await self.flush_staging(pool=pool)
            if not flushed:
                break
            total += flushed
        if total:
            logger.info("[CandlesFinalizer] ?„ì²´ staging flush ?„ë£Œ: %dê±?, total)
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
