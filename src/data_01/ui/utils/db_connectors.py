# -*- coding: utf-8 -*-
"""
DB ?깃???而ㅻ꽖????TimescaleDB / Redis / MongoDB (v1.0)

??紐⑤뱢? ?뚯폆 怨좉컝??諛⑹??섍린 ?꾪빐 ?깃????⑦꽩?쇰줈 DB ?곌껐??愿由ы빀?덈떎.
諛섑솚?섎뒗 TimescaleDB 媛앹껜???ㅼ젣 Connection Pool ?낅땲??(.get_connection()/.put_connection() ?ъ슜).
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# ?대? ?좏떥 ??psycopg2 SimpleConnectionPool ?섑띁
# ============================================================

class _Psycopg2PoolWrapper:
    """psycopg2 SimpleConnectionPool??UI ?좏떥 ?명꽣?섏씠?ㅻ줈 ?섑븨.

    db_connectors.py ?대? ?꾩슜 private ?대옒??
    get_connection() / put_connection() / close_all() ?명꽣?섏씠???쒓났.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def get_connection(self, retry: bool = True) -> Any:
        conn = self._pool.getconn()
        if conn is None:
            raise RuntimeError("[PoolWrapper] getconn() returned None")
        # ABORTED ?곹깭 ?먮룞 濡ㅻ갚 (STATUS_READY=2, 0=?곌껐 誘몄궗??
        try:
            import psycopg2.extensions as _pg_ext  # type: ignore
            _idle_status = getattr(_pg_ext, "STATUS_READY", 2)
        except Exception:
            _idle_status = 2
        try:
            if conn.status != _idle_status:
                conn.rollback()
        except Exception as _rb_exc:
            logger.debug("[PoolWrapper] ?먮룞 濡ㅻ갚 ?ㅽ뙣: %s", _rb_exc)
        return conn

    def put_connection(self, conn: Any) -> None:
        try:
            self._pool.putconn(conn)
        except Exception as e:
            logger.debug("[PoolWrapper] putconn ?ㅽ뙣: %s", e)

    def close_all(self) -> None:
        try:
            self._pool.closeall()
        except Exception as e:
            logger.debug("[PoolWrapper] closeall ?ㅽ뙣: %s", e)


# ============================================================
# ?꾩뿭 ?깃???罹먯떆 (?뚯폆 怨좉컝 諛⑹?)
# ============================================================
_timescale_connector_cache: Optional[Any] = None
_timescale_connector_lock = threading.Lock()

_redis_client_cache: Optional[Any] = None
_redis_client_lock = threading.Lock()

_mongo_sync_client_cache: Optional[Any] = None
_mongo_sync_client_lock = threading.Lock()


def get_timescale_connector() -> Optional[Any]:
    """TimescaleDB ?깃????곌껐 ? 媛?몄삤湲?(?ъ뿰寃?濡쒖쭅 ?ы븿).

    諛섑솚??媛앹껜??Connection Pool ?낅땲??
    ?곌껐??吏곸젒 ?ъ슜?섎젮硫?.get_connection() / .put_connection() ?⑦꽩???ъ슜?섏꽭??

    Returns:
        TimescaleDB Connection Pool ?몄뒪?댁뒪 ?먮뒗 None
    """
    global _timescale_connector_cache

    with _timescale_connector_lock:
        # 湲곗〈 ?곌껐 ping ?뺤씤 (Pool??get_connection/put_connection ?ъ슜)
        if _timescale_connector_cache is not None:
            try:
                conn = _timescale_connector_cache.get_connection(retry=False)
                _timescale_connector_cache.put_connection(conn)
                logger.debug("[UI Utils] TimescaleDB 湲곗〈 ?곌껐 ? ?ъ궗??)
                return _timescale_connector_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] TimescaleDB ping ?ㅽ뙣 (罹먯떆 ?좎?): %s", ping_exc)
                return _timescale_connector_cache  # 罹먯떆 ?대━???놁씠 諛섑솚, caller媛 泥섎━

        # ???곌껐 ? ?앹꽦
        if _timescale_connector_cache is None:
            try:
                # __timescale_pool_state__ ?ㅻ줈 ?대? 珥덇린?붾맂 ? 吏곸젒 ?ъ슜 (媛??鍮좊Ⅸ 寃쎈줈)
                _state = sys.modules.get("__timescale_pool_state__")
                if _state is not None and _state.get("pool") is not None:
                    _timescale_connector_cache = _Psycopg2PoolWrapper(_state["pool"])
                    logger.debug("[UI Utils] ??TimescaleDB (__timescale_pool_state__ 吏곸젒 ?ъ슜)")
                    return _timescale_connector_cache

                # sys.modules?먯꽌 ?대? 珥덇린?붾맂 pool 寃??(媛??鍮좊Ⅸ 寃쎈줈)
                for _pool_key in (
                    "timescale_pool", "_timescale_pool_ui",
                    "data_01.timescale.timescale_pool", "src.data_01.timescale.timescale_pool",
                    "timescale.pool", "data_01.timescale.pool", "src.data_01.timescale.pool",
                    "_timescale_pool_dynamic",
                ):
                    _pm = sys.modules.get(_pool_key)
                    if _pm is not None:
                        _gfn = getattr(_pm, "get_timescale_connector", None)
                        if callable(_gfn):
                            try:
                                _c = _gfn()
                                if _c is not None:
                                    _timescale_connector_cache = _c
                                    logger.debug(
                                        "[UI Utils] ??TimescaleDB (sys.modules %s)", _pool_key
                                    )
                                    return _timescale_connector_cache
                            except Exception as mod_exc:
                                logger.debug(
                                    "[UI Utils] sys.modules[%s] ?쒕룄 ?ㅽ뙣: %s", _pool_key, mod_exc
                                )

                # TimescaleConnector 吏곸젒 ?꾪룷??(src/data_01/timescale/pool.py)
                try:
                    from ...timescale.pool import (  # type: ignore
                        get_connection as _pool_get,
                        release_connection as _pool_release,
                    )

                    # pool.py 濡쒕뱶 ??__timescale_pool_state__ ?ы솗??
                    _state2 = sys.modules.get("__timescale_pool_state__")
                    if _state2 is not None and _state2.get("pool") is not None:
                        _timescale_connector_cache = _Psycopg2PoolWrapper(_state2["pool"])
                        logger.info("[UI Utils] ??TimescaleDB (pool.py import)")
                        return _timescale_connector_cache
                except Exception as import_exc:
                    logger.debug("[UI Utils] pool.py 吏곸젒 ?꾪룷???ㅽ뙣: %s", import_exc)

                # ?대갚: ?뚯씪 寃쎈줈 湲곕컲 ?숈쟻 濡쒕뱶
                try:
                    import pathlib

                    _base = pathlib.Path(__file__).resolve().parents[2]
                    _pool_path = _base / "timescale" / "pool.py"

                    if _pool_path.exists():
                        _spec = importlib.util.spec_from_file_location(
                            "_timescale_pool_dynamic", str(_pool_path)
                        )
                        if _spec and _spec.loader:
                            _mod = sys.modules.get("_timescale_pool_dynamic")
                            if _mod is None:
                                _mod = importlib.util.module_from_spec(_spec)
                                sys.modules["_timescale_pool_dynamic"] = _mod
                                _spec.loader.exec_module(_mod)

                            # pool.py 濡쒕뱶 ??__timescale_pool_state__ ?뺤씤
                            _state3 = sys.modules.get("__timescale_pool_state__")
                            if _state3 is not None and _state3.get("pool") is not None:
                                _timescale_connector_cache = _Psycopg2PoolWrapper(
                                    _state3["pool"]
                                )
                                logger.info("[UI Utils] ??TimescaleDB ?깃???(?숈쟻 濡쒕뱶)")
                                return _timescale_connector_cache
                except Exception as dyn_exc:
                    logger.debug("[UI Utils] ?숈쟻 濡쒕뱶 ?ㅽ뙣: %s", dyn_exc)

            except Exception as e:
                logger.warning("[UI Utils] TimescaleDB ?곌껐 ?앹꽦 ?ㅽ뙣: %s", e)
                _timescale_connector_cache = None

    return None


def get_redis_connector() -> Optional[Any]:
    """Redis ?깃????대씪?댁뼵??媛?몄삤湲?(?ъ뿰寃?濡쒖쭅 ?ы븿).

    Returns:
        redis.Redis ?대씪?댁뼵???몄뒪?댁뒪 ?먮뒗 None
    """
    global _redis_client_cache

    with _redis_client_lock:
        # 湲곗〈 ?대씪?댁뼵??ping ?뺤씤
        if _redis_client_cache is not None:
            try:
                _redis_client_cache.ping()
                logger.debug("[UI Utils] Redis 湲곗〈 ?대씪?댁뼵???ъ궗??)
                return _redis_client_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] Redis ping ?ㅽ뙣: %s", ping_exc)
                _redis_client_cache = None

        # ???대씪?댁뼵???앹꽦
        try:
            import redis as _redis_mod  # type: ignore

            # Redis ?ㅼ젙 濡쒕뱶
            _redis_cfg: dict = {}
            try:
                from _01_core.database.redis_factory import _load_redis_config  # type: ignore

                _redis_cfg = _load_redis_config()
            except Exception as cfg_exc:
                logger.debug("[UI Utils] redis_factory 濡쒕뱶 ?ㅽ뙣, env fallback ?ъ슜: %s", cfg_exc)

            host = os.getenv("REDIS_HOST") or _redis_cfg.get("HOST", "localhost")
            port = int(os.getenv("REDIS_PORT") or _redis_cfg.get("PORT", 58530))
            db = int(os.getenv("REDIS_DB") or _redis_cfg.get("DB", 0))
            password = os.getenv("REDIS_PASSWORD") or _redis_cfg.get("PASSWORD") or None
            decode_responses = os.getenv("REDIS_DECODE_RESP", "true").lower() != "false"

            client = _redis_mod.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            client.ping()
            _redis_client_cache = client
            logger.info(
                "[UI Utils] Redis ?꾩뿭 ?깃????앹꽦 (host=%s port=%d decode=%s)",
                host,
                port,
                decode_responses,
            )
            return _redis_client_cache
        except ImportError:
            logger.warning("[UI Utils] redis ?⑦궎吏 誘몄꽕移???pip install redis")
        except Exception as e:
            logger.warning("[UI Utils] Redis ?곌껐 ?앹꽦 ?ㅽ뙣: %s", e)
            _redis_client_cache = None

    return None


def get_mongo_sync_client() -> Optional[Any]:
    """MongoDB ?숆린 ?대씪?댁뼵???깃???(pymongo) - Qt GUI ?덉쟾.

    PyQt5 QTimer ?명솚 (Event loop is closed ?먮윭 ?놁쓬).
    pymongo.MongoClient ?ъ슜 (motor ?쒓굅).

    ?섍꼍 蹂??
        MONGO_URI: MongoDB URI (湲곕낯媛? mongodb://localhost:27017/upbit_trader)

    Returns:
        pymongo.MongoClient ?몄뒪?댁뒪 (ping ?뺤씤?? ?먮뒗 None
    """
    global _mongo_sync_client_cache

    with _mongo_sync_client_lock:
        # 湲곗〈 ?대씪?댁뼵??ping ?뺤씤
        if _mongo_sync_client_cache is not None:
            try:
                _mongo_sync_client_cache.admin.command("ping")
                logger.debug("[UI Utils] MongoDB ?숆린 ?대씪?댁뼵???ъ궗??)
                return _mongo_sync_client_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] MongoDB ping ?ㅽ뙣: %s", ping_exc)
                _mongo_sync_client_cache = None

        # ???대씪?댁뼵???앹꽦 (pymongo)
        try:
            import pymongo  # type: ignore

            uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
            client = pymongo.MongoClient(
                uri,
                serverSelectionTimeoutMS=2000,
                directConnection=True,
            )
            client.admin.command("ping")
            _mongo_sync_client_cache = client
            logger.info("[UI Utils] ??MongoDB ?숆린 ?대씪?댁뼵???앹꽦 (pymongo)")
            return _mongo_sync_client_cache
        except ImportError:
            logger.warning("[UI Utils] pymongo ?⑦궎吏 誘몄꽕移???pip install pymongo")
        except Exception as e:
            logger.warning("[UI Utils] MongoDB ?곌껐 ?ㅽ뙣: %s", e)
            _mongo_sync_client_cache = None

    return None

