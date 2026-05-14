# -*- coding: utf-8 -*-
"""
Timescale DB ?묎렐 ?좏떥 (?명솚??媛뺥솕 v3.2)

蹂寃쎌궗??v3.2 (2026-04-26):
- ??flush_staging_to_candles() ??symbol_full 而щ읆 ?쒓굅 (議댁옱?섏? ?딅뒗 而щ읆 李몄“ ?먮윭 ?섏젙)
- ???ㅼ젣 ?ㅽ궎留?湲곗??쇰줈 而щ읆 紐⑸줉 ?낅뜲?댄듃 (quote_volume, is_complete, seq 異붽?)
- ??DISTINCT ON 湲곗? 而щ읆 ?쒖꽌 ?섏젙: (symbol, timeframe, time) ??PRIMARY KEY ?쒖꽌 ?쇱튂

異붽? 蹂寃?(?대쾲 ?⑥튂):
- fetch_conn_status, _safe_fetch_query: 吏곸젒 psycopg2.connect() ???
  媛?ν븯硫?TimescaleConnector(?먮뒗 ?꾩뿭 ?)瑜??곗꽑 ?ъ슜?섎룄濡?蹂寃쏀븯??
  UI/?대쭅?먯꽌 鍮덈쾲???④린 ?곌껐 ?앹꽦??諛⑹??⑸땲??
"""
from __future__ import annotations

import logging
import sys
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("timescale.db")
if logger.level == 0:
    logger.setLevel(logging.INFO)


def _connect_db(cfg: Dict[str, Any], timeout: int = 3) -> Tuple[Optional[Any], Optional[str]]:
    """
    psycopg2濡??숆린 ?곌껐???쒕룄.
    諛섑솚: (connection, None) ?먮뒗 (None, ?먮윭硫붿떆吏(?쒓?))
    """
    try:
        import psycopg2  # type: ignore
    except Exception:
        logger.error("[timescale_db] psycopg2 誘몄꽕移?- DB ?곌껐 遺덇?")
        return None, "psycopg2 誘몄꽕移?(pip install psycopg2-binary 沅뚯옣)"

    # DSN ?곗꽑: cfg??dsn ?먮뒗 ?섍꼍蹂??TIMESCALE_DSN/DATABASE_URL ?ъ슜 媛??
    dsn = cfg.get("dsn") or os.getenv("TIMESCALE_DSN") or os.getenv("DATABASE_URL")
    if dsn:
        try:
            conn = psycopg2.connect(dsn, connect_timeout=timeout)
            logger.debug("[timescale_db] DB ?곌껐 ?깃났 via DSN")
            return conn, None
        except Exception as e:
            logger.warning("[timescale_db] DSN ?곌껐 ?ㅽ뙣: %s", e)

    host = cfg.get("host", "localhost")
    port = int(cfg.get("port", 5432))
    dbname = cfg.get("dbname") or cfg.get("db") or cfg.get("database") or ""
    user = cfg.get("user") or ""
    password = cfg.get("password") or ""
    logger.debug("[timescale_db] DB ?묒냽 ?쒕룄 -> host=%s port=%s dbname=%s user=%s", host, port, dbname, user)

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=timeout,
        )
        logger.debug("[timescale_db] DB ?곌껐 ?깃났: %s:%s/%s", host, port, dbname)
        return conn, None
    except Exception as e:
        msg = str(e)
        lmsg = msg.lower()
        logger.warning("[timescale_db] DB ?곌껐 ?ㅽ뙣: %s", msg)
        if "authentication failed" in lmsg or "password authentication" in lmsg:
            return None, "?몄쬆 ?ㅽ뙣: DB ?ъ슜??鍮꾨?踰덊샇瑜??뺤씤?섏꽭??"
        if "role" in lmsg and "does not exist" in lmsg:
            return None, "DB ?ъ슜??role)媛 ?놁뒿?덈떎. 怨꾩젙 ?ㅼ젙???뺤씤?섏꽭??"
        if "connection refused" in lmsg or "could not connect to server" in lmsg:
            return None, "?몄뒪???ы듃 ?묒냽 遺덇?: DB ?쒕쾭 ?ㅽ뻾/?ㅽ듃?뚰겕瑜??뺤씤?섏꽭??"
        return None, f"DB ?묒냽 ?ㅽ뙣: {msg}"


def _get_timescale_connector():
    """
    TimescaleConnector瑜??숈쟻?쇰줈 濡쒕뱶?⑸땲??

    ?먯깋 ?쒖꽌:
    1. sys.modules?먯꽌 ?대? 濡쒕뱶??紐⑤뱢 李얘린
    2. ?꾨낫 紐⑤뱢紐낆쓣 import?대낫湲?
    3. ?뚯씪 寃쎈줈 湲곕컲 ?숈쟻 濡쒕뱶

    Returns:
        get_timescale_connector ?⑥닔 ?먮뒗 None
    """
    # 1. sys.modules?먯꽌 李얘린 (?щ윭 ?꾨낫紐?
    candidates_in_sys = [
        "src.data_01.timescale.timescale_pool",
        "data_01.timescale.timescale_pool",
        "data_01.timescale.timescale_pool",
        "timescale.timescale_pool",
        "timescale_pool",
        "src.app.timescale.timescale_pool",
    ]
    for mod_name in candidates_in_sys:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            func = getattr(mod, "get_timescale_connector", None)
            if func is not None:
                logger.debug("[timescale_db] ??get_timescale_connector found in sys.modules: %s", mod_name)
                return func

    # 2. importlib濡??щ윭 ?꾨낫 寃쎈줈 ?쒕룄
    import importlib
    import importlib.util
    module_candidates = [
        "data_01.timescale.timescale_pool",
        "src.data_01.timescale.timescale_pool",
        "src.app.data_01.timescale.timescale_pool",
        "timescale.timescale_pool",
        "timescale_pool",
    ]
    for candidate in module_candidates:
        try:
            mod = importlib.import_module(candidate)
            func = getattr(mod, "get_timescale_connector", None)
            if func is not None:
                logger.info("[timescale_db] ??timescale_pool import ?깃났: %s", candidate)
                return func
        except Exception:
            continue

    # 3. ?뚯씪 寃쎈줈 湲곕컲 ?숈쟻 濡쒕뱶 (?꾩옱 ?뚯씪 湲곗?)
    try:
        import pathlib
        current_file = pathlib.Path(__file__).resolve()
        pool_path = current_file.parent / "timescale_pool.py"
        if pool_path.exists():
            spec = importlib.util.spec_from_file_location("_timescale_pool_dynamic", str(pool_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_timescale_pool_dynamic"] = mod
                spec.loader.exec_module(mod)
                func = getattr(mod, "get_timescale_connector", None)
                if func is not None:
                    logger.info("[timescale_db] ??timescale_pool ?숈쟻 濡쒕뱶 ?깃났: %s", pool_path)
                    return func
    except Exception as exc:
        logger.debug("[timescale_db] timescale_pool ?숈쟻 濡쒕뱶 ?ㅽ뙣: %s", exc, exc_info=True)

    logger.warning("[timescale_db] ?좑툘 get_timescale_connector瑜?李얠쓣 ???놁쓬")
    return None


def _safe_fetch_query(cfg: Dict[str, Any], query: str, params: Optional[tuple] = None, fetch_all: bool = True) -> Tuple[Optional[List[tuple]], Optional[str]]:
    """
    ?덉쟾??荑쇰━ ?ㅽ뻾 ?ы띁: (rows, None) ?먮뒗 (None, err_msg)
    - 媛?ν븯硫?TimescaleConnector/????ъ슜?섏뿬 ?곌껐???ъ궗?⑺빀?덈떎.
    - ?ㅽ뙣 ??湲곗〈 諛⑹떇???대갚(psycopg2.connect).
    - ?ㅽ뙣 ??荑쇰━ ?욌?遺??붾쾭洹몄슜)??濡쒓렇???④퉩?덈떎.
    """
    # 1) ?곗꽑 TimescaleConnector/? ?ъ슜 ?쒕룄
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is not None:
            try:
                connector = get_connector_func()
                if connector is not None:
                    # connector媛 pg_pool ?꾨줈?쇳떚瑜??쒓났?????덉쑝誘濡??곗꽑 ?ъ슜
                    conn_owner = getattr(connector, "pg_pool", connector)
                    raw_conn, from_pool = conn_owner._acquire_conn()
                    cur = None
                    try:
                        cur = raw_conn.cursor()
                        if params:
                            cur.execute(query, params)
                        else:
                            cur.execute(query)
                        rows = cur.fetchall() if fetch_all else cur.fetchone()
                        return (rows if rows is not None else []), None
                    except Exception as e:
                        q_preview = (query or "")[:200].replace("\n", " ")
                        logger.debug("[timescale_db] (pool) 荑쇰━ ?ㅽ뻾 ?ㅽ뙣: %s | 荑쇰━(?욌?遺?: %s", e, q_preview, exc_info=True)
                        try:
                            if raw_conn:
                                raw_conn.rollback()
                        except Exception:
                            pass
                        return None, f"荑쇰━ ?ㅽ뻾 ?ㅽ뙣: {str(e)}"
                    finally:
                        try:
                            if cur is not None:
                                try:
                                    cur.close()
                                except Exception:
                                    pass
                        finally:
                            try:
                                conn_owner._release_conn(raw_conn, from_pool, failed=False)
                            except Exception:
                                # 留뚯빟 ?덉쇅媛 諛쒖깮?덈떎硫??ㅽ뙣 ?뚮옒洹몃줈 諛섑솚
                                try:
                                    conn_owner._release_conn(raw_conn, from_pool, failed=True)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("[timescale_db] connector 湲곕컲 ?ㅽ뻾 ?쒕룄 ?ㅽ뙣, fallback: %s", e, exc_info=True)
    except Exception:
        # ?대뼡 ?댁쑀濡쒕뱺 connector 濡쒕뵫 ?먯껜媛 ?ㅽ뙣?대룄 ?꾨옒濡??대갚
        pass

    # 2) ?대갚: 湲곗〈??吏곸젒 ?곌껐 諛⑹떇
    conn, err = _connect_db(cfg)
    if conn is None:
        return None, err
    cur = None
    try:
        cur = conn.cursor()
        try:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
        except Exception as e:
            q_preview = (query or "")[:200].replace("\n", " ")
            logger.debug("[timescale_db] 荑쇰━ ?ㅽ뻾 ?ㅽ뙣: %s | 荑쇰━(?욌?遺?: %s", e, q_preview, exc_info=True)
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return None, f"荑쇰━ ?ㅽ뻾 ?ㅽ뙣: {str(e)}"
        rows = cur.fetchall() if fetch_all else cur.fetchone()
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return (rows if rows is not None else []), None
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        logger.debug("[timescale_db] 荑쇰━ ?꾨컲 ?덉쇅", exc_info=True)
        return None, str(e)


# -------------------------------------------------------------------------
# ?곌껐 ?곹깭 議고쉶 (UI??
# -------------------------------------------------------------------------
def fetch_conn_status(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    UI?먯꽌 二쇨린?곸쑝濡??몄텧?섎뒗 DB ?곹깭 議고쉶 ?좏떥由ы떚?낅땲??
    蹂寃? 吏곸젒 psycopg2.connect ???媛?ν븯硫?connector/????ъ슜?섏뿬
    二쇨린 ?대쭅?쇰줈 ?명븳 ?④린 ?곌껐 ??쬆??諛⑹??⑸땲??
    """
    out: Dict[str, Any] = {
        "status": "disconnected",
        "host": cfg.get("host", "-"),
        "port": cfg.get("port", "-"),
        "dbname": cfg.get("dbname", "-"),
        "version": "-",
        "ts_version": "-",
        "uptime": "-",
        "conn_count": "-",
        "error": None,
    }

    # 1) 媛?ν븳 寃쎌슦 connector/? ?ъ슜
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is not None:
            try:
                connector = get_connector_func()
                if connector is not None:
                    conn_owner = getattr(connector, "pg_pool", connector)
                    conn = None
                    pool = None
                    cur = None
                    try:
                        # ??먯꽌 ?띾뱷?섍굅??direct self.conn fallback??諛섑솚
                        conn, pool = conn_owner._acquire_conn()
                        if conn is None:
                            raise RuntimeError("connector._acquire_conn媛 None??諛섑솚??)
                        cur = conn.cursor()
                        try:
                            cur.execute("SELECT version();")
                            ver = cur.fetchone()
                            out["version"] = ver[0] if ver else "-"
                        except Exception:
                            out["version"] = "-"
                        try:
                            cur.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb';")
                            r = cur.fetchone()
                            out["ts_version"] = r[0] if r else "-"
                        except Exception:
                            out["ts_version"] = "-"
                        try:
                            cur.execute("SELECT date_trunc('second', now() - pg_postmaster_start_time())::text;")
                            r = cur.fetchone()
                            out["uptime"] = r[0] if r else "-"
                        except Exception:
                            out["uptime"] = "-"
                        try:
                            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s;", (cfg.get("dbname"),))
                            r = cur.fetchone()
                            out["conn_count"] = int(r[0]) if r else "-"
                        except Exception:
                            out["conn_count"] = "-"
                        out["status"] = "connected"
                        return out
                    except Exception as exc:
                        logger.debug("[timescale_db] connector ?ъ슜 以??곹깭 議고쉶 ?ㅽ뙣: %s", exc)
                        out["error"] = str(exc)
                        return out
                    finally:
                        try:
                            if cur is not None:
                                try:
                                    cur.close()
                                except Exception:
                                    pass
                        finally:
                            try:
                                conn_owner._release_conn(conn, pool, failed=False)
                            except Exception:
                                try:
                                    conn_owner._release_conn(conn, pool, failed=True)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("[timescale_db] connector ?몄뒪?댁뒪???ㅽ뙣, fallback: %s", e, exc_info=True)
    except Exception:
        pass

    # 2) ?대갚: 湲곗〈??吏곸젒 ?곌껐 諛⑹떇
    try:
        import psycopg2  # type: ignore
    except Exception as e:
        out["error"] = f"psycopg2 誘몄꽕移? {e}"
        return out

    conn = None
    try:
        # DSN ?곗꽑
        dsn = cfg.get("dsn") or os.getenv("TIMESCALE_DSN") or os.getenv("DATABASE_URL")
        if dsn:
            conn = psycopg2.connect(dsn, connect_timeout=3)
        else:
            conn = psycopg2.connect(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 5432)),
                dbname=cfg.get("dbname", ""),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                connect_timeout=3,
            )
    except Exception as e:
        out["error"] = f"DB ?곌껐 ?ㅽ뙣: {e}"
        return out

    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT version();")
            ver = cur.fetchone()
            out["version"] = ver[0] if ver else "-"
        except Exception:
            out["version"] = "-"
        try:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb';")
            r = cur.fetchone()
            out["ts_version"] = r[0] if r else "-"
        except Exception:
            out["ts_version"] = "-"
        try:
            cur.execute("SELECT date_trunc('second', now() - pg_postmaster_start_time())::text;")
            r = cur.fetchone()
            out["uptime"] = r[0] if r else "-"
        except Exception:
            out["uptime"] = "-"
        try:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s;", (cfg.get("dbname"),))
            r = cur.fetchone()
            out["conn_count"] = int(r[0]) if r else "-"
        except Exception:
            out["conn_count"] = "-"
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        out["status"] = "connected"
        return out
    except Exception as e:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        out["error"] = str(e)
        return out


# -------------------------------------------------------------------------
# 吏꾨떒 ?좏떥由ы떚
# -------------------------------------------------------------------------
def diagnose_data(cfg: Dict[str, Any], sample_limit: int = 5) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "market_ticks_exists": False,
        "candle_gaps_exists": False,
        "market_ticks_count": None,
        "distinct_symbols": None,
        "latest_samples": [],
        "error": None,
    }
    try:
        q_exist = "SELECT to_regclass('public.market_ticks') IS NOT NULL AS mt, to_regclass('public.candle_gaps') IS NOT NULL AS cg;"
        rows, err = _safe_fetch_query(cfg, q_exist, fetch_all=True)
        if rows is None:
            out["error"] = f"吏꾨떒 ?ㅽ뙣: {err}"
            return out
        mt_exists, cg_exists = rows[0]
        out["market_ticks_exists"] = bool(mt_exists)
        out["candle_gaps_exists"] = bool(cg_exists)
        if not out["market_ticks_exists"]:
            return out

        q_cnt = "SELECT count(*) FROM market_ticks;"
        rows, err = _safe_fetch_query(cfg, q_cnt)
        out["market_ticks_count"] = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0

        q_sym = "SELECT count(DISTINCT symbol) FROM market_ticks;"
        rows, err = _safe_fetch_query(cfg, q_sym)
        out["distinct_symbols"] = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0

        q_sample = f"""
            SELECT symbol, max(exchange_ts) AS last_ts, count(*) AS cnt
            FROM market_ticks
            GROUP BY symbol
            ORDER BY max(exchange_ts) DESC
            LIMIT {int(sample_limit)};
        """
        rows, err = _safe_fetch_query(cfg, q_sample)
        sam = []
        if rows:
            for sym, last_ts, cnt in rows:
                try:
                    if last_ts is not None and getattr(last_ts, "tzinfo", None) is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    sam.append({"symbol": sym, "last_ts": last_ts.isoformat() if last_ts is not None else None, "count": int(cnt)})
                except Exception:
                    sam.append({"symbol": sym, "last_ts": str(last_ts), "count": int(cnt) if cnt is not None else None})
        out["latest_samples"] = sam
    except Exception as e:
        logger.debug("[timescale_db] diagnose_data ?덉쇅", exc_info=True)
        out["error"] = str(e)
    return out


# =========================================================================
# TimescaleConnector ?숈쟻 濡쒕뱶 (import 寃쎈줈 ?먮룞 ?먯깋)
# =========================================================================
# (?대? ?꾩뿉 ?뺤쓽??_get_timescale_connector ?ъ슜)
# -------------------------------------------------------------------------


# -------------------------------------------------------------------------
# Staging ??Candles ?대룞 ?⑥닔 (unchanged)
# -------------------------------------------------------------------------
def flush_staging_to_candles(batch_size: int = 1000) -> int:
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is None:
            logger.error("[Finalizer] ??get_timescale_connector ?⑥닔瑜?李얠쓣 ???놁쓬")
            return 0

        connector = get_connector_func()
        if connector is None:
            logger.error("[Finalizer] ??TimescaleDB 而ㅻ꽖???놁쓬")
            return 0

        conn_obj = getattr(connector, "pg_pool", connector)
        raw_conn, from_pool = conn_obj._acquire_conn()

        try:
            with raw_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.staging_candles")
                count = cur.fetchone()[0]
                logger.info("[Finalizer] staging_candles ?꾩옱 ???? %d", count)
                if count == 0:
                    conn_obj._release_conn(raw_conn, from_pool, failed=False)
                    return 0

                move_sql = """
                    WITH uniqued AS (
                        SELECT DISTINCT ON (symbol, timeframe, time)
                            id, symbol, timeframe, exchange, time,
                            open, high, low, close, volume, quote_volume,
                            trade_count, is_complete, seq
                        FROM public.staging_candles
                        ORDER BY symbol, timeframe, time, inserted_at DESC
                        LIMIT %s
                    ),
                    ins AS (
                        INSERT INTO public.candles
                            (symbol, timeframe, exchange, time,
                             open, high, low, close, volume, quote_volume,
                             trade_count, is_complete, seq)
                        SELECT symbol, timeframe, exchange, time,
                               open, high, low, close, volume, quote_volume,
                               trade_count, is_complete, seq
                        FROM uniqued
                        ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                            exchange     = COALESCE(EXCLUDED.exchange,     candles.exchange),
                            open         = COALESCE(EXCLUDED.open,         candles.open),
                            high         = GREATEST(COALESCE(candles.high, EXCLUDED.high),
                                                    COALESCE(EXCLUDED.high, candles.high)),
                            low          = LEAST(COALESCE(candles.low, EXCLUDED.low),
                                                 COALESCE(EXCLUDED.low, candles.low)),
                            close        = EXCLUDED.close,
                            volume       = COALESCE(candles.volume, 0) + COALESCE(EXCLUDED.volume, 0),
                            quote_volume = COALESCE(EXCLUDED.quote_volume, candles.quote_volume),
                            trade_count  = COALESCE(EXCLUDED.trade_count,  candles.trade_count),
                            is_complete  = EXCLUDED.is_complete,
                            seq          = COALESCE(EXCLUDED.seq, candles.seq)
                        RETURNING 1
                    )
                    DELETE FROM public.staging_candles
                    WHERE id IN (SELECT id FROM uniqued)
                    RETURNING 1;
                """
                cur.execute(move_sql, (batch_size,))
                moved = cur.rowcount if cur.rowcount is not None else 0

            raw_conn.commit()
            logger.info("[Finalizer] ??%d媛??대룞 ?꾨즺", moved)
            conn_obj._release_conn(raw_conn, from_pool, failed=False)
            return moved

        except Exception as e:
            try:
                raw_conn.rollback()
            except Exception:
                pass
            conn_obj._release_conn(raw_conn, from_pool, failed=True)
            logger.error("[Finalizer] ??flush_staging_to_candles ?ㅽ뙣: %s", e, exc_info=True)
            return 0

    except Exception as e:
        logger.error("[Finalizer] ??flush_staging_to_candles ?꾩껜 ?ㅽ뙣: %s", e, exc_info=True)
        return 0


# (?꾨옒??fetch_* ?⑥닔?ㅼ? 湲곗〈 援ы쁽??洹몃?濡??좎? ???앸왂?섏? ?딄퀬 ?댁쟾怨??숈씪?섍쾶 ?ъ슜 媛??
# fetch_hypertables, fetch_compression_policies, fetch_continuous_aggs,
# fetch_backfills, fetch_gaps ??湲곗〈 ?뺤쓽瑜?洹몃?濡??ъ슜?섎㈃ ?⑸땲??
