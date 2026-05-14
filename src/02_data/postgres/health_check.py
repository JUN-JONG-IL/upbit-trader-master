# -*- coding: utf-8 -*-
"""
Postgres health_check 모듈 (보강판)
- 역할: get_status(role='primary'|'replica'), ping(role) 제공
- 보강: 지정 DB가 없다는 오류가 발생하면 기본 DB('postgres')로 재시도하여
  서버 레벨 가용성(포트/인스턴스 실행 여부)을 우선 판단하도록 함.
- 풀(또는 커넥션 재사용)을 도입하여 주기적/동시 헬스체크가 매번 새 백엔드
  프로세스를 생성하는 문제를 완화합니다.
"""
from __future__ import annotations

import importlib.util
import os
import json
import logging
import traceback
import types
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import threading

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DB_CONFIG_YAML = os.path.join(_REPO_ROOT, "src", "01_core", "config", "db_connections.yaml")
_DB_CONFIG_JSON = os.path.join(_REPO_ROOT, "src", "01_core", "config", "db_connections.json")

# constants.py를 경로 기반으로 로드 (01_core는 Python 식별자 제한으로 직접 import 불가)
_CONST_PATH = str(Path(__file__).parents[3] / "01_core" / "config" / "constants.py")

def _load_constants() -> Optional[types.ModuleType]:
    """constants.py 모듈을 경로 기반으로 로드합니다."""
    try:
        spec = importlib.util.spec_from_file_location("_pg_hc_constants", _CONST_PATH)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    except Exception as exc:
        logger.debug("[postgres.health_check] constants 로드 실패: %s", exc)
    return None

_CONSTS = _load_constants()
_DEFAULT_PRIMARY_PORT: int = getattr(_CONSTS, "DEFAULT_POSTGRES_PRIMARY_PORT", 5433)
_DEFAULT_REPLICA_PORT: int = getattr(_CONSTS, "DEFAULT_POSTGRES_REPLICA_PORT", 5434)
_DEFAULT_HOST: str = getattr(_CONSTS, "DEFAULT_POSTGRES_PRIMARY_HOST", "127.0.0.1")

# 모듈 레벨 기본값 (환경변수 + constants 기반으로 동적 생성)
def _build_module_host() -> str:
    """환경변수와 constants를 참조하여 모듈 레벨 HOST 문자열을 생성합니다."""
    h = os.environ.get("POSTGRES_HOST", _DEFAULT_HOST)
    p = int(os.environ.get("POSTGRES_PORT", str(_DEFAULT_PRIMARY_PORT)))
    return f"{h}:{p}"

HOST = _build_module_host()
host = HOST
__host__ = HOST

pg_conn_primary = None
pg_conn_replica = None

def _load_saved_config() -> Optional[Dict[str, Dict[str, Any]]]:
    """저장된 DB 설정(YAML/JSON)을 로드합니다."""
    try:
        import yaml  # type: ignore
        if os.path.isfile(_DB_CONFIG_YAML):
            with open(_DB_CONFIG_YAML, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data
    except Exception as exc:
        logger.debug("[postgres.health_check] YAML 설정 로드 실패: %s", exc)
    try:
        if os.path.isfile(_DB_CONFIG_JSON):
            with open(_DB_CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
    except Exception as exc:
        logger.debug("[postgres.health_check] JSON 설정 로드 실패: %s", exc)
    return None

def _get_params_for_role(role: str = "primary") -> Tuple[str, int, str, Optional[str], str]:
    """역할(primary/replica)에 맞는 DB 연결 파라미터를 반환합니다."""
    cfg = _load_saved_config() or {}
    section_name = "postgres_primary" if role == "primary" else "postgres_replica"
    default_map = {
        "primary": (_DEFAULT_HOST, _DEFAULT_PRIMARY_PORT),
        "replica": (_DEFAULT_HOST, _DEFAULT_REPLICA_PORT),
    }
    host_def, port_def = default_map.get(role, (_DEFAULT_HOST, _DEFAULT_PRIMARY_PORT))
    if section_name in cfg:
        sec = cfg[section_name] or {}
        h = sec.get("host", host_def)
        p = int(sec.get("port", port_def))
        user = sec.get("user") or os.environ.get("POSTGRES_USER", "postgres")
        password = sec.get("password") or os.environ.get("POSTGRES_PASSWORD")
        db = sec.get("database") or os.environ.get("POSTGRES_DB", "postgres")
        return (h, p, user, password, db)
    if "postgres" in cfg:
        sec = cfg["postgres"] or {}
        h = sec.get("host", host_def)
        p = int(sec.get("port", port_def))
        user = sec.get("user") or os.environ.get("POSTGRES_USER", "postgres")
        password = sec.get("password") or os.environ.get("POSTGRES_PASSWORD")
        db = sec.get("database") or os.environ.get("POSTGRES_DB", "postgres")
        return (h, p, user, password, db)
    h = os.environ.get("POSTGRES_HOST", host_def)
    p = int(os.environ.get("POSTGRES_PORT", port_def))
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD")
    db = os.environ.get("POSTGRES_DB", "postgres")
    return (h, p, user, password, db)

# --------------------------------------------------------------------
# psycopg2 ThreadedConnectionPool 캐시 (role/params별)
# - 헬스체크가 빈번할 때 매번 새 연결을 열지 않도록 관리
# --------------------------------------------------------------------
_pool_lock = threading.Lock()
_pool_cache: Dict[str, object] = {}  # key -> ThreadedConnectionPool
_POOL_MINCONN = 1
_POOL_MAXCONN = 3

def _pool_key_from_params(params: Tuple[str, int, str, Optional[str], str]) -> str:
    host, port, user, password, db = params
    return f"{host}:{port}/{db}@{user}"

def _ensure_psycopg2_pool(params: Tuple[str, int, str, Optional[str], str]):
    """주어진 파라미터로 ThreadedConnectionPool을 생성하거나 기존 풀을 반환. 실패하면 None 리턴."""
    try:
        from psycopg2.pool import ThreadedConnectionPool  # type: ignore
    except Exception:
        return None
    key = _pool_key_from_params(params)
    with _pool_lock:
        pool = _pool_cache.get(key)
        if pool:
            return pool
        try:
            host, port, user, password, db = params
            pool = ThreadedConnectionPool(
                _POOL_MINCONN,
                _POOL_MAXCONN,
                host=host,
                port=port,
                user=user,
                password=password or "",
                dbname=db,
                connect_timeout=2,
            )
            # 간단히 획득/반환 테스트
            try:
                conn = pool.getconn()
                if getattr(conn, "closed", 0):
                    pool.putconn(conn, close=True)
                    raise RuntimeError("획득한 커넥션이 닫혀있음")
                pool.putconn(conn)
            except Exception:
                try:
                    pool.closeall()
                except Exception:
                    pass
                logger.debug("[postgres.health_check] 풀 초기화 테스트 실패")
                return None
            _pool_cache[key] = pool
            logger.debug("[postgres.health_check] psycopg2 pool 생성: %s", key)
            return pool
        except Exception as exc:
            logger.debug("[postgres.health_check] psycopg2.pool 생성 실패: %s", exc)
            return None

def _get_conn_from_pool_or_direct(params: Tuple[str, int, str, Optional[str], str]):
    """pool에서 conn을 얻거나 direct connect를 수행. (conn, pool_or_None) 반환"""
    pool = _ensure_psycopg2_pool(params)
    if pool:
        try:
            conn = pool.getconn()
            if getattr(conn, "closed", 0):
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = pool.getconn()
            return conn, pool
        except Exception as exc:
            logger.debug("[postgres.health_check] pool.getconn 실패, direct connect로 폴백: %s", exc)
    # direct connect fallback
    try:
        import psycopg2  # type: ignore
        host, port, user, password, db = params
        conn = psycopg2.connect(host=host, port=port, user=user, password=password or "", dbname=db, connect_timeout=2)
        return conn, None
    except Exception as exc:
        logger.debug("[postgres.health_check] psycopg2 direct connect 실패: %s", exc)
        return None, None

def _release_conn(conn, pool):
    """pool이면 putconn, 아니면 conn.close(). 안전하게 처리."""
    try:
        if conn is None:
            return
        if pool is not None:
            try:
                pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        logger.debug("[postgres.health_check] _release_conn 예외", exc_info=True)

# --------------------------------------------------------------------
# 기존 드라이버/async 검사 로직(풀 기반 사용 추가)
# --------------------------------------------------------------------
def _try_sync_psycopg(params: Tuple[str, int, str, Optional[str], str], timeout: int = 2) -> Optional[Dict[str, Any]]:
    host, port, user, password, db = params
    # try psycopg (v3) first (unchanged)
    try:
        import psycopg  # type: ignore
        try:
            conn = psycopg.connect(host=host, port=port, user=user, password=password or "", dbname=db, timeout=timeout)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            conn.close()
            return {"status": "ok", "impl": "psycopg", "host": f"{host}:{port}"}
        except Exception as e:
            logger.debug("[postgres.health_check] psycopg connect/exec 실패: %s", e)
    except ImportError:
        logger.debug("[postgres.health_check] psycopg(v3) 미설치")
    # psycopg2: 이제 pool 우선 사용
    try:
        import psycopg2  # type: ignore
        # pool 또는 direct connect 사용
        conn = None
        pool = None
        try:
            conn, pool = _get_conn_from_pool_or_direct(params)
            if conn is None:
                return None
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            # 성공
            return {"status": "ok", "impl": "psycopg2", "host": f"{host}:{port}"}
        except Exception as e:
            logger.debug("[postgres.health_check] psycopg2 exec 실패: %s", e)
            return None
        finally:
            try:
                _release_conn(conn, pool)
            except Exception:
                pass
    except ImportError:
        logger.debug("[postgres.health_check] psycopg2 미설치")
    return None

def _try_asyncpg(params: Tuple[str, int, str, Optional[str], str], timeout: int = 2) -> Optional[Dict[str, Any]]:
    try:
        import asyncio
        import asyncpg  # type: ignore

        async def _check():
            host, port, user, password, db = params
            conn_str = dict(host=host, port=port, user=user, password=password or "", database=db)
            conn = await asyncpg.connect(**conn_str, timeout=timeout)
            val = await conn.fetchval("SELECT 1")
            await conn.close()
            return bool(val)
        try:
            ok = asyncio.run(_check())
            if ok:
                host, port, *_ = params
                return {"status": "ok", "impl": "asyncpg", "host": f"{host}:{port}"}
        except Exception as e:
            logger.debug("[postgres.health_check] asyncpg 실패: %s", e)
    except ImportError:
        logger.debug("[postgres.health_check] asyncpg 미설치")
    return None

def _tcp_probe_only(host: str, port: int, timeout: int = 2) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        logger.debug("[postgres.health_check] tcp probe 실패: %s", e)
        return False

def get_status(role: str = "primary") -> Dict[str, Any]:
    """
    get_status: 우선 드라이버로 SELECT 1 시도.
    만약 'database does not exist' 와 같은 오류 발생 시에는
    - 대체 DB('postgres' 또는 환경변수 POSTGRES_DB 기본값)로 재시도하여 서버 가용성 확인,
    - 재시도도 실패하면 최종적으로 tcp probe 결과로 응답.
    """
    try:
        params = _get_params_for_role(role)
        host, port, user, password, db = params
        host_str = f"{host}:{port}"
        # 1) 표준 DB 시도 (pool 사용 포함)
        res = _try_sync_psycopg(params)
        if res:
            return {"status": "ok", "message": "select_ok", "host": host_str, "impl": res.get("impl", "psycopg"), "meta": {}}
        res = _try_asyncpg(params)
        if res:
            return {"status": "ok", "message": "select_ok", "host": host_str, "impl": res.get("impl", "asyncpg"), "meta": {}}

        # 2) 여기까지 실패: 구체적 오류가 'database does not exist'인지 판단해 보강 시도
        #    -> 설정/환경변수에 지정된 DB가 잘못되었을 가능성 있으므로 기본 DB('postgres')로 재시도
        alt_db = os.environ.get("POSTGRES_DB", "postgres")
        if alt_db and alt_db != db:
            try:
                alt_params = (host, port, user, password, alt_db)
                logger.debug("[postgres.health_check] 지정 DB(%s) 실패, 대체 DB(%s)로 재시도", db, alt_db)
                res_alt = _try_sync_psycopg(alt_params)
                if res_alt:
                    return {"status": "ok", "message": f"select_ok_alt_db({alt_db})", "host": host_str, "impl": res_alt.get("impl", "psycopg"), "meta": {"tried_db": alt_db}}
                res_alt = _try_asyncpg(alt_params)
                if res_alt:
                    return {"status": "ok", "message": f"select_ok_alt_db({alt_db})", "host": host_str, "impl": res_alt.get("impl", "asyncpg"), "meta": {"tried_db": alt_db}}
            except Exception as e:
                logger.debug("[postgres.health_check] 대체 DB 재시도 중 예외: %s", e)

        # 3) 드라이버로 모두 직접 연결 못하면 네트워크 레벨(tcp)로 포트 열림 확인
        if _tcp_probe_only(host, port, timeout=2):
            # 서버(인스턴스)는 살아있음. DB명 문제일 가능성 높음.
            return {"status": "ok", "message": "tcp_open_only", "host": host_str, "impl": "tcp_probe", "meta": {"note": "db_missing_or_auth_issue"}}
        else:
            return {"status": "fail", "message": "connect_failed", "host": host_str, "impl": "tcp_probe", "meta": {}}
    except Exception as e:
        logger.exception("[postgres.health_check] get_status 예외: %s", e)
        return {"status": "error", "message": str(e), "host": "--", "impl": "--", "meta": {"trace": traceback.format_exc()}}

def ping(role: str = "primary") -> bool:
    try:
        st = get_status(role)
        return st.get("status") == "ok"
    except Exception as exc:
        logger.debug("[postgres.health_check] ping 예외: %s", exc)
        return False

def health(role: str = "primary") -> Dict[str, Any]:
    return get_status(role)

def check(role: str = "primary") -> Dict[str, Any]:
    return get_status(role)

def _update_module_host_defaults() -> None:
    """모듈 레벨 HOST 변수를 환경변수 기반으로 갱신합니다."""
    try:
        host_p, port_p, *_ = _get_params_for_role("primary")
        global HOST, host, __host__
        HOST = f"{host_p}:{port_p}"
        host = HOST
        __host__ = HOST
    except Exception as exc:
        logger.debug("[postgres.health_check] _update_module_host_defaults 실패: %s", exc)

_update_module_host_defaults()