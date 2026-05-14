# -*- coding: utf-8 -*-
"""
DB 싱글톤 커넥터 — TimescaleDB / Redis / MongoDB (v1.0)

이 모듈은 소켓 고갈을 방지하기 위해 싱글톤 패턴으로 DB 연결을 관리합니다.
반환되는 TimescaleDB 객체는 실제 Connection Pool 입니다 (.get_connection()/.put_connection() 사용).
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
# 내부 유틸 — psycopg2 SimpleConnectionPool 래퍼
# ============================================================

class _Psycopg2PoolWrapper:
    """psycopg2 SimpleConnectionPool을 UI 유틸 인터페이스로 래핑.

    db_connectors.py 내부 전용 private 클래스.
    get_connection() / put_connection() / close_all() 인터페이스 제공.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def get_connection(self, retry: bool = True) -> Any:
        conn = self._pool.getconn()
        if conn is None:
            raise RuntimeError("[PoolWrapper] getconn() returned None")
        # ABORTED 상태 자동 롤백 (STATUS_READY=2, 0=연결 미사용)
        try:
            import psycopg2.extensions as _pg_ext  # type: ignore
            _idle_status = getattr(_pg_ext, "STATUS_READY", 2)
        except Exception:
            _idle_status = 2
        try:
            if conn.status != _idle_status:
                conn.rollback()
        except Exception as _rb_exc:
            logger.debug("[PoolWrapper] 자동 롤백 실패: %s", _rb_exc)
        return conn

    def put_connection(self, conn: Any) -> None:
        try:
            self._pool.putconn(conn)
        except Exception as e:
            logger.debug("[PoolWrapper] putconn 실패: %s", e)

    def close_all(self) -> None:
        try:
            self._pool.closeall()
        except Exception as e:
            logger.debug("[PoolWrapper] closeall 실패: %s", e)


# ============================================================
# 전역 싱글톤 캐시 (소켓 고갈 방지)
# ============================================================
_timescale_connector_cache: Optional[Any] = None
_timescale_connector_lock = threading.Lock()

_redis_client_cache: Optional[Any] = None
_redis_client_lock = threading.Lock()

_mongo_sync_client_cache: Optional[Any] = None
_mongo_sync_client_lock = threading.Lock()


def get_timescale_connector() -> Optional[Any]:
    """TimescaleDB 싱글톤 연결 풀 가져오기 (재연결 로직 포함).

    반환된 객체는 Connection Pool 입니다.
    연결을 직접 사용하려면 .get_connection() / .put_connection() 패턴을 사용하세요.

    Returns:
        TimescaleDB Connection Pool 인스턴스 또는 None
    """
    global _timescale_connector_cache

    with _timescale_connector_lock:
        # 기존 연결 ping 확인 (Pool의 get_connection/put_connection 사용)
        if _timescale_connector_cache is not None:
            try:
                conn = _timescale_connector_cache.get_connection(retry=False)
                _timescale_connector_cache.put_connection(conn)
                logger.debug("[UI Utils] TimescaleDB 기존 연결 풀 재사용")
                return _timescale_connector_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] TimescaleDB ping 실패 (캐시 유지): %s", ping_exc)
                return _timescale_connector_cache  # 캐시 클리어 없이 반환, caller가 처리

        # 새 연결 풀 생성
        if _timescale_connector_cache is None:
            try:
                # __timescale_pool_state__ 키로 이미 초기화된 풀 직접 사용 (가장 빠른 경로)
                _state = sys.modules.get("__timescale_pool_state__")
                if _state is not None and _state.get("pool") is not None:
                    _timescale_connector_cache = _Psycopg2PoolWrapper(_state["pool"])
                    logger.debug("[UI Utils] ✅ TimescaleDB (__timescale_pool_state__ 직접 사용)")
                    return _timescale_connector_cache

                # sys.modules에서 이미 초기화된 pool 검색 (가장 빠른 경로)
                for _pool_key in (
                    "timescale_pool", "_timescale_pool_ui",
                    "02_data.timescale.timescale_pool", "src.02_data.timescale.timescale_pool",
                    "timescale.pool", "02_data.timescale.pool", "src.02_data.timescale.pool",
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
                                        "[UI Utils] ✅ TimescaleDB (sys.modules %s)", _pool_key
                                    )
                                    return _timescale_connector_cache
                            except Exception as mod_exc:
                                logger.debug(
                                    "[UI Utils] sys.modules[%s] 시도 실패: %s", _pool_key, mod_exc
                                )

                # TimescaleConnector 직접 임포트 (src/02_data/timescale/pool.py)
                try:
                    from ...timescale.pool import (  # type: ignore
                        get_connection as _pool_get,
                        release_connection as _pool_release,
                    )

                    # pool.py 로드 후 __timescale_pool_state__ 재확인
                    _state2 = sys.modules.get("__timescale_pool_state__")
                    if _state2 is not None and _state2.get("pool") is not None:
                        _timescale_connector_cache = _Psycopg2PoolWrapper(_state2["pool"])
                        logger.info("[UI Utils] ✅ TimescaleDB (pool.py import)")
                        return _timescale_connector_cache
                except Exception as import_exc:
                    logger.debug("[UI Utils] pool.py 직접 임포트 실패: %s", import_exc)

                # 폴백: 파일 경로 기반 동적 로드
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

                            # pool.py 로드 후 __timescale_pool_state__ 확인
                            _state3 = sys.modules.get("__timescale_pool_state__")
                            if _state3 is not None and _state3.get("pool") is not None:
                                _timescale_connector_cache = _Psycopg2PoolWrapper(
                                    _state3["pool"]
                                )
                                logger.info("[UI Utils] ✅ TimescaleDB 싱글톤 (동적 로드)")
                                return _timescale_connector_cache
                except Exception as dyn_exc:
                    logger.debug("[UI Utils] 동적 로드 실패: %s", dyn_exc)

            except Exception as e:
                logger.warning("[UI Utils] TimescaleDB 연결 생성 실패: %s", e)
                _timescale_connector_cache = None

    return None


def get_redis_connector() -> Optional[Any]:
    """Redis 싱글톤 클라이언트 가져오기 (재연결 로직 포함).

    Returns:
        redis.Redis 클라이언트 인스턴스 또는 None
    """
    global _redis_client_cache

    with _redis_client_lock:
        # 기존 클라이언트 ping 확인
        if _redis_client_cache is not None:
            try:
                _redis_client_cache.ping()
                logger.debug("[UI Utils] Redis 기존 클라이언트 재사용")
                return _redis_client_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] Redis ping 실패: %s", ping_exc)
                _redis_client_cache = None

        # 새 클라이언트 생성
        try:
            import redis as _redis_mod  # type: ignore

            # Redis 설정 로드
            _redis_cfg: dict = {}
            try:
                from _01_core.database.redis_factory import _load_redis_config  # type: ignore

                _redis_cfg = _load_redis_config()
            except Exception as cfg_exc:
                logger.debug("[UI Utils] redis_factory 로드 실패, env fallback 사용: %s", cfg_exc)

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
                "[UI Utils] Redis 전역 싱글톤 생성 (host=%s port=%d decode=%s)",
                host,
                port,
                decode_responses,
            )
            return _redis_client_cache
        except ImportError:
            logger.warning("[UI Utils] redis 패키지 미설치 — pip install redis")
        except Exception as e:
            logger.warning("[UI Utils] Redis 연결 생성 실패: %s", e)
            _redis_client_cache = None

    return None


def get_mongo_sync_client() -> Optional[Any]:
    """MongoDB 동기 클라이언트 싱글톤 (pymongo) - Qt GUI 안전.

    PyQt5 QTimer 호환 (Event loop is closed 에러 없음).
    pymongo.MongoClient 사용 (motor 제거).

    환경 변수:
        MONGO_URI: MongoDB URI (기본값: mongodb://localhost:27017/upbit_trader)

    Returns:
        pymongo.MongoClient 인스턴스 (ping 확인됨) 또는 None
    """
    global _mongo_sync_client_cache

    with _mongo_sync_client_lock:
        # 기존 클라이언트 ping 확인
        if _mongo_sync_client_cache is not None:
            try:
                _mongo_sync_client_cache.admin.command("ping")
                logger.debug("[UI Utils] MongoDB 동기 클라이언트 재사용")
                return _mongo_sync_client_cache
            except Exception as ping_exc:
                logger.debug("[UI Utils] MongoDB ping 실패: %s", ping_exc)
                _mongo_sync_client_cache = None

        # 새 클라이언트 생성 (pymongo)
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
            logger.info("[UI Utils] ✅ MongoDB 동기 클라이언트 생성 (pymongo)")
            return _mongo_sync_client_cache
        except ImportError:
            logger.warning("[UI Utils] pymongo 패키지 미설치 — pip install pymongo")
        except Exception as e:
            logger.warning("[UI Utils] MongoDB 연결 실패: %s", e)
            _mongo_sync_client_cache = None

    return None
