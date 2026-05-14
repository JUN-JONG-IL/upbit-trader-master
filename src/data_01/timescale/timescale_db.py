# -*- coding: utf-8 -*-
"""
timescale_db ???섏쐞?명솚 re-export 紐⑤뱢 諛??ы띁
- ?ㅼ젣 援ы쁽? src/data_01/timescale/core/ ?섏쐞 紐⑤뱢???꾩튂?????덉뒿?덈떎.
- 紐⑹쟻: TimescaleConnector ?대옒?ㅼ? 愿???좏떥???덉쟾?섍쾶 李얠븘 ?щ끂異쒗븯怨?
  get_timescale_connector()瑜??듯빐 ?덉젙?곸씤 ?깃????몄뒪?댁뒪 諛섑솚??蹂댁옣?⑸땲??
- 蹂닿컯:
  - 紐⑤뱢 ?덈꺼 罹먯떆(_connector_instance)濡?諛섎났 ?앹꽦 諛⑹?
  - TimescaleConnector ?몄뒪?댁뒪 ?앹꽦???ㅼ뼇???쒓렇?덉쿂(臾댁씤??DSN ?몄옄 ?? ?쒕룄
  - ?곌껐 ?ㅽ뙣??紐낇솗???붾쾭洹?寃쎄퀬 濡쒓렇
  - fetch_* ?ы띁?먯꽌 而ㅼ꽌 ?ъ슜??try/finally ???with 臾??ъ슜?쇰줈 ?덉젙??
  - ?꾩뿭 ?(pool.py)??議댁옱?섍퀬 ENABLE_AUTO_INIT_POOL ?섍꼍蹂?섍? ?ㅼ젙?섏뼱 ?덉쑝硫?
    init_global_pool_from_env()瑜??덉쟾?섍쾶 ?몄텧?섎룄濡?蹂닿컯 (?꾩뿭 ? ?먮룞 珥덇린??蹂댁“).
"""
from __future__ import annotations

import logging
import sys
import types
import os
import importlib.util as _ilu
import pathlib as _pl
from typing import Any, Optional, Sequence

logger = logging.getLogger("timescale_db")

# --------------------------------------------------------------------------
# 紐⑤뱢 ?섏? 媛蹂: ?몃??먯꽌 ?ы븷?밸맆 ???덈뒗 湲곕낯 李몄“??
# --------------------------------------------------------------------------
TimescaleConnector: Optional[type] = None  # ?ㅼ젣 connector ?대옒??(媛?ν븯硫?
timescale_build_dsn = None  # DSN ?앹꽦 helper (媛?ν븯硫?

# 罹먯떆??connector ?몄뒪?댁뒪(?깃????⑦꽩 蹂댁“)
_connector_instance: Optional[Any] = None


# --------------------------------------------------------------------------
# 1) ?곷? import ?쒕룄 (?⑦궎吏濡?濡쒕뱶??寃쎌슦)
# --------------------------------------------------------------------------
try:
    from .core.connector_base import TimescaleConnector  # type: ignore
    from .timescale_utils import timescale_build_dsn  # type: ignore
    logger.debug("[timescale_db] ?곷? import濡?TimescaleConnector/timescale_build_dsn 濡쒕뱶 ?깃났")
except Exception as _e:
    logger.debug("[timescale_db] ?듭떖 ?대옒???곷? import ?ㅽ뙣(?뺤긽 媛??: %s", _e)

    # ----------------------------------------------------------------------
    # 2) sys.modules 寃?? ?대? 濡쒕뱶??紐⑤뱢?ㅼ뿉???대옒???⑥닔 寃??(鍮꾪뙆占쏙옙占?
    # ----------------------------------------------------------------------
    if TimescaleConnector is None or timescale_build_dsn is None:
        _ts_module_patterns = ("timescale", "connector", "connector_base", "_timescale", "candle_writer")
        for _mn, _mm in list(sys.modules.items()):
            if _mm is None:
                continue
            if not any(p in _mn for p in _ts_module_patterns):
                continue
            if TimescaleConnector is None:
                _cls = getattr(_mm, "TimescaleConnector", None)
                if _cls is not None and isinstance(_cls, type):
                    # 湲곕낯?곸씤 ?뺥깭 異붿젙: ?대옒?ㅻŉ connect 硫붿꽌?쒓? ?덉쓬
                    if hasattr(_cls, "connect"):
                        TimescaleConnector = _cls
                        logger.debug("[timescale_db] TimescaleConnector found in sys.modules[%s]", _mn)
            if timescale_build_dsn is None:
                _fn = getattr(_mm, "timescale_build_dsn", None)
                if callable(_fn):
                    timescale_build_dsn = _fn
            if TimescaleConnector is not None and timescale_build_dsn is not None:
                break

    # ----------------------------------------------------------------------
    # 3) ?뚯씪 寃쎈줈 湲곕컲 ?숈쟻 濡쒕뱶 ?쒕룄 (留덉?留??섎떒)
    # ----------------------------------------------------------------------
    if TimescaleConnector is None:
        try:
            _here = _pl.Path(__file__).resolve().parent
            _core_dir = _here / "core"

            # ?⑹꽦 ?⑦궎吏 ?ㅽ뀅??留뚮뱾?댁꽌 ?곷? import媛 ?숈옉?섎룄濡??꾩?
            _PKG = "_timescale_dyn"
            _CORE_PKG = f"{_PKG}.core"

            if _PKG not in sys.modules:
                _pm = types.ModuleType(_PKG)
                _pm.__path__ = [str(_here)]  # type: ignore[assignment]
                _pm.__package__ = _PKG
                sys.modules[_PKG] = _pm

            if _CORE_PKG not in sys.modules:
                _cm = types.ModuleType(_CORE_PKG)
                _cm.__path__ = [str(_core_dir)]  # type: ignore[assignment]
                _cm.__package__ = _CORE_PKG
                sys.modules[_CORE_PKG] = _cm

            def _load_submodule(rel: str, mod_name: str, pkg: str):
                """?뚯씪 寃쎈줈濡??쒕툕紐⑤뱢??濡쒕뱶?섍퀬 sys.modules???깅줉?⑸땲??"""
                if mod_name in sys.modules:
                    return sys.modules[mod_name]
                _spec = _ilu.spec_from_file_location(mod_name, str(_here / rel))
                if not (_spec and _spec.loader):
                    return None
                _m = _ilu.module_from_spec(_spec)
                _m.__package__ = pkg
                sys.modules[mod_name] = _m
                try:
                    _spec.loader.exec_module(_m)  # type: ignore[union-attr]
                except Exception as _exc:
                    sys.modules.pop(mod_name, None)
                    raise _exc
                return _m

            # connector_base???섏〈??誘뱀뒪????遺??濡쒕뱶
            _ddl = _load_submodule("core/schema_ddl.py",    f"{_CORE_PKG}.schema_ddl",    _CORE_PKG)
            _cw  = _load_submodule("core/candle_writer.py", f"{_CORE_PKG}.candle_writer", _CORE_PKG)
            _qh  = _load_submodule("core/query_helpers.py", f"{_CORE_PKG}.query_helpers", _CORE_PKG)

            if _ddl is None or _cw is None or _qh is None:
                raise ImportError("誘뱀뒪???섏〈??濡쒕뱶 ?ㅽ뙣 (schema_ddl/candle_writer/query_helpers)")

            # connector_base 濡쒕뱶
            _cb = _load_submodule("core/connector_base.py", f"{_CORE_PKG}.connector_base", _CORE_PKG)
            if _cb:
                TimescaleConnector = getattr(_cb, "TimescaleConnector", None)
                if TimescaleConnector is not None:
                    logger.info("[timescale_db] ??TimescaleConnector ?숈쟻 濡쒕뱶 ?깃났")
        except Exception as _e2:
            logger.warning("[timescale_db] ?숈쟻 濡쒕뱶 ?ㅽ뙣: %s", _e2)

    # timescale_build_dsn ?대갚 濡쒕뱶 ?쒕룄
    if timescale_build_dsn is None:
        try:
            _tu_path = _pl.Path(__file__).resolve().parent / "timescale_utils.py"
            _tu_spec = _ilu.spec_from_file_location("_ts_utils_dyn", str(_tu_path))
            if _tu_spec and _tu_spec.loader:
                _tu_mod = _ilu.module_from_spec(_tu_spec)
                sys.modules["_ts_utils_dyn"] = _tu_mod
                _tu_spec.loader.exec_module(_tu_mod)  # type: ignore[union-attr]
                timescale_build_dsn = getattr(_tu_mod, "timescale_build_dsn", None)
        except Exception:
            pass

    # 理쒖쥌 ?대갚: 媛꾨떒???섍꼍蹂??湲곕컲 DSN 鍮뚮뜑
    if timescale_build_dsn is None:
        def timescale_build_dsn() -> str:  # type: ignore[misc]
            import os
            return os.environ.get("DATABASE_URL", "")


# --------------------------------------------------------------------------
# get_timescale_connector ???깃????몄뒪?댁뒪 諛섑솚 (bootstrap.py ?깆뿉???ъ슜)
# --------------------------------------------------------------------------
def _try_instantiate_connector(cls: type, dsn_arg: Optional[str] = None):
    """
    TimescaleConnector ?대옒?ㅻ? ?ㅼ뼇???쒓렇?덉쿂濡??몄뒪?댁뒪???쒕룄.
    - ?몄옄 ?놁쓬
    - dsn 臾몄옄??1媛??몄옄
    - ?ㅼ썙??dsn=db_url
    """
    try:
        # 1) 臾댁씤???앹꽦 ?쒕룄
        try:
            return cls()
        except TypeError:
            pass

        # 2) ?⑥씪 臾몄옄???몄옄(dsn) ?쒕룄
        if dsn_arg:
            try:
                return cls(dsn_arg)
            except TypeError:
                pass

        # 3) ?ㅼ썙???몄옄 ?쒕룄
        try:
            return cls(dsn=dsn_arg)
        except Exception:
            pass

    except Exception as exc:
        logger.debug("[timescale_db] connector ?몄뒪?댁뒪???ㅽ뙣: %s", exc, exc_info=True)
    return None


def _attempt_init_global_pool_if_configured():
    """
    ?꾩뿭 ?(pool.py)??議댁옱?섍퀬 ?섍꼍蹂??ENABLE_AUTO_INIT_POOL???쒖꽦?붾릺???덉쑝硫?
    pool.init_global_pool_from_env()瑜??몄텧?⑸땲?? ?ㅽ뙣?대룄 臾댁떆?⑸땲??
    """
    try:
        if str(os.getenv("ENABLE_AUTO_INIT_POOL", "")).lower() not in ("1", "true", "yes"):
            return
        # ?곷? import ?곗꽑
        try:
            from . import pool as poolmod  # type: ignore
        except Exception:
            # ?뚯씪 寃쎈줈 湲곕컲 ?대뜑?먯꽌 ?숈쟻 濡쒕뱶 ?쒕룄 (鍮꾪뙣?ㅼ? ?곹솴 寃ш퀬??
            try:
                _here = _pl.Path(__file__).resolve().parent
                _pool_path = _here / "pool.py"
                if _pool_path.exists():
                    _spec = _ilu.spec_from_file_location("_timescale_pool_auto", str(_pool_path))
                    _pm = _ilu.module_from_spec(_spec)
                    sys.modules["_timescale_pool_auto"] = _pm
                    _spec.loader.exec_module(_pm)  # type: ignore[union-attr]
                    poolmod = _pm
                else:
                    return
            except Exception as e:
                logger.debug("[timescale_db] pool 紐⑤뱢 ?숈쟻 濡쒕뱶 ?ㅽ뙣: %s", e)
                return
        # init ?⑥닔媛 ?덉쑝硫??몄텧 (臾댄빐???몄텧)
        init_fn = getattr(poolmod, "init_global_pool_from_env", None)
        if callable(init_fn):
            try:
                logger.info("[timescale_db] ENABLE_AUTO_INIT_POOL ?쒖꽦: ?꾩뿭 ? 珥덇린???쒕룄")
                init_fn()
                logger.info("[timescale_db] ?꾩뿭 ? ?먮룞 珥덇린???쒕룄 ?꾨즺")
            except Exception as e:
                logger.warning("[timescale_db] ?꾩뿭 ? ?먮룞 珥덇린???ㅽ뙣: %s", e)
    except Exception:
        logger.debug("[timescale_db] _attempt_init_global_pool_if_configured ?ㅽ뙣", exc_info=True)


def get_timescale_connector() -> Optional[Any]:
    """
    TimescaleConnector ?깃????몄뒪?댁뒪瑜?諛섑솚?⑸땲??

    ?숈옉:
      - 紐⑤뱢 ?섏? 罹먯떆(_connector_instance)瑜??ъ궗??(?덇퀬 ?곌껐 ?좏슚?섎㈃ 洹몃?濡?諛섑솚)
      - ?놁쑝硫?TimescaleConnector ?대옒?ㅺ? ?덉쑝硫??몄뒪?댁뒪???쒕룄(?щ윭 ?쒓렇?덉쿂 ?먮룞 ?쒕룄)
      - ?몄뒪?댁뒪???깃났 ??connect() ?몄텧?섏뿬 ?ㅼ젣 ?곌껐 蹂댁옣
      - ?ㅽ뙣 ??None 諛섑솚
    """
    global _connector_instance, TimescaleConnector, timescale_build_dsn

    # ?대? 罹먯떆???몄뒪?댁뒪媛 ?덈떎硫?connect()濡??좏슚???ы솗??
    if _connector_instance is not None:
        try:
            ok = True
            # some connector implementations may expose is_connected/connected or connect() that is idempotent
            if hasattr(_connector_instance, "is_connected"):
                try:
                    ok = bool(getattr(_connector_instance, "is_connected")())
                except Exception:
                    ok = True  # be permissive
            elif hasattr(_connector_instance, "connected"):
                try:
                    ok = bool(getattr(_connector_instance, "connected"))
                except Exception:
                    ok = True
            else:
                # if no health API, attempt connect() which should be safe/idempotent in well-designed connector
                try:
                    ok = bool(_connector_instance.connect())
                except Exception:
                    ok = False
            if ok:
                return _connector_instance
        except Exception:
            logger.debug("[timescale_db] cached connector health check ?ㅽ뙣", exc_info=True)
            # fall through to recreate

    if TimescaleConnector is None:
        logger.warning("[timescale_db] TimescaleConnector ?대옒???놁쓬 - connector ?앹꽦 遺덇?")
        return None

    # ?꾩뿭 ? ?먮룞 珥덇린???쒕룄 (?섍꼍蹂??ENABLE_AUTO_INIT_POOL=true ??寃쎌슦)
    try:
        _attempt_init_global_pool_if_configured()
    except Exception:
        logger.debug("[timescale_db] ?꾩뿭 ? ?먮룞 珥덇린???쒕룄 以??덉쇅", exc_info=True)

    # Build DSN if helper present
    dsn = None
    try:
        try:
            dsn = timescale_build_dsn() if callable(timescale_build_dsn) else None
        except Exception:
            dsn = None

    except Exception:
        dsn = None

    # ?쒓렇?덉쿂 ?ㅼ뼇???쒕룄
    conn_obj = _try_instantiate_connector(TimescaleConnector, dsn_arg=dsn)
    if conn_obj is None:
        logger.warning("[timescale_db] TimescaleConnector ?몄뒪?댁뒪???ㅽ뙣 (?щ윭 ?쒓렇?덉쿂 ?쒕룄)")
        return None

    # ?곌껐 ?쒕룄: connect()媛 True/None/connection-object ?깆쓣 諛섑솚?????덉쑝誘濡??덉슜?곸쑝濡?泥섎━
    try:
        result = conn_obj.connect()
        # ?뺤긽?곸쑝濡??곌껐?섏뿀嫄곕굹 connect媛 None(?붾У???깃났)??寃쎌슦 ?덉슜
        if result is False:
            logger.warning("[timescale_db] get_timescale_connector: connector.connect()媛 False瑜?諛섑솚?덉뒿?덈떎")
            return None
        # 罹먯떆 ??諛섑솚
        _connector_instance = conn_obj
        logger.info("[timescale_db] get_timescale_connector: connector ?앹꽦 諛??곌껐 ?깃났")
        return _connector_instance
    except Exception as exc:
        logger.warning("[timescale_db] connector.connect() ?몄텧 以??덉쇅: %s", exc, exc_info=True)
        try:
            # if connector exposes close/disconnect, attempt to call to cleanup partial resources
            for name in ("close", "disconnect", "stop", "terminate"):
                fn = getattr(conn_obj, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        except Exception:
            pass
        return None


# --------------------------------------------------------------------------
# 踰꾩쟾 ?명솚 荑쇰━ ?ы띁 (紐⑤뱢 ?섏? ?⑥닔) ??timescale_settings_dialog ?깆뿉???ъ슜
# 紐⑤뱺 ?⑥닔??'conn' (psycopg2 connection) ?몄옄瑜?諛쏆븘 洹?而ㅻ꽖?섎쭔 ?ъ슜?⑸땲??
# --------------------------------------------------------------------------
def fetch_compression_policies(conn) -> Sequence:
    """?뺤텞 ?뺤콉 議고쉶 (TimescaleDB 踰꾩쟾 ?명솚).
    conn: psycopg2 raw connection 媛앹껜
    ?덉쟾: ?대??먯꽌 cursor 而⑦뀓?ㅽ듃瑜??ъ슜??而ㅼ꽌 ?꾩닔 諛⑹?
    """
    _primary_sql = """
        SELECT
            h.hypertable_name AS hypertable,
            config::json->>'compress_after' AS compress_after,
            job_id
        FROM timescaledb_information.jobs j
        JOIN timescaledb_information.hypertables h
          ON j.hypertable_name = h.hypertable_name
        WHERE j.proc_name = 'policy_compression'
    """
    _secondary_sql = """
        SELECT
            h.table_name AS hypertable,
            config::json->>'compress_after' AS compress_after,
            job_id
        FROM timescaledb_information.jobs j
        JOIN timescaledb_information.hypertables h
          ON j.hypertable_name = h.table_name
        WHERE j.proc_name = 'policy_compression'
    """
    _fallback_sql = """
        SELECT
            ht.table_name AS hypertable,
            '-' AS compress_after,
            0 AS job_id
        FROM _timescaledb_catalog.hypertable ht
    """

    def _try_query(sql: str, label: str):
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            logger.debug("[timescale_db] compression_policies ??%s ?깃났 (rows=%d)", label, len(rows))
            return rows
        except Exception as exc:
            logger.debug("[timescale_db] compression_policies ??%s ?ㅽ뙣: %s", label, exc)
            try:
                conn.rollback()
            except Exception:
                pass
            return None

    for sql, label in (
        (_primary_sql,   "primary(v3.x)"),
        (_secondary_sql, "secondary(v2.x)"),
        (_fallback_sql,  "fallback(catalog)"),
    ):
        rows = _try_query(sql, label)
        if rows is not None:
            if label != "primary(v3.x)":
                logger.info("[timescale_db] compression_policies ??%s ?ъ슜", label)
            return rows

    logger.warning("[timescale_db] compression_policies ??紐⑤뱺 荑쇰━ ?ㅽ뙣; 鍮?紐⑸줉 諛섑솚")
    return []


def fetch_continuous_aggs(conn) -> Sequence:
    """Continuous Aggregates 議고쉶 (TimescaleDB 踰꾩쟾 ?명솚).
    conn: psycopg2 raw connection 媛앹껜
    """
    _primary_sql = """
        SELECT view_name, view_definition, '-' AS refresh_lag
        FROM timescaledb_information.continuous_aggregates
    """
    _fallback_sql = """
        SELECT view_name, '-' AS view_definition, '-' AS refresh_lag
        FROM _timescaledb_catalog.continuous_agg
    """
    try:
        with conn.cursor() as cur:
            cur.execute(_primary_sql)
            rows = cur.fetchall()
            logger.debug("[timescale_db] continuous_aggs ??primary 荑쇰━ ?깃났 (rows=%d)", len(rows))
            return rows
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            with conn.cursor() as cur:
                cur.execute(_fallback_sql)
                rows = cur.fetchall()
                logger.info("[timescale_db] continuous_aggs ??fallback 荑쇰━ ?ъ슜 (rows=%d)", len(rows))
                return rows
        except Exception:
            logger.warning("[timescale_db] continuous_aggs ??fallback 荑쇰━???ㅽ뙣; 鍮?紐⑸줉 諛섑솚")
            try:
                conn.rollback()
            except Exception:
                pass
            return []


__all__ = [
    "TimescaleConnector",
    "timescale_build_dsn",
    "get_timescale_connector",
    "fetch_compression_policies",
    "fetch_continuous_aggs",
]
