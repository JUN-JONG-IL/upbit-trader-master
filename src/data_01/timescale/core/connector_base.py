# -*- coding: utf-8 -*-
"""
connector_base — TimescaleConnector
연결/풀/execute 담당 핵심 클래스.

변경 요지(안정성 우선):
- 모듈 단독 로드(importlib.spec) 시 상대 import 실패 문제를 방지하기 위한 폴백 로딩 추가.
- DSN 우선순위에 TIMESCALE_DSN 추가.
- executemany에서 psycopg2.extras.execute_values 사용 시
  "the query contains more than one '%s' placeholder" 오류가 발생하면
  execute_values가 기대하는 template 형태로 SQL을 변환하여 자동 재시도하도록 보강.
- 기타 방어 강화(예외 시 명확한 메시지).
- 기존 로직(세마포어, 풀 폴백, executemany 청크 등)은 유지/보완.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import sys
import traceback
import json
import re
from contextlib import contextmanager
from typing import Any, Iterable, List, Optional, Tuple, Generator
from urllib.parse import quote_plus, unquote, urlparse
from itertools import islice

# --------------------------------------------------------------------------
# 상대 import 시도하되 실패하면 같은 디렉터리의 파일을 경로 기반으로 동적 로드하는
# 폴백(fallback) 로직을 사용합니다. 이렇게 하면 importlib.spec_from_file_location
# 으로 파일을 직접 불러올 때 발생하는 "attempted relative import with no known parent package"
# 오류를 피할 수 있습니다.
# --------------------------------------------------------------------------
def _safe_relative_import(module_name: str, attr_name: str):
    """
    같은 패키지 내 상대 import를 시도하고 실패하면 파일 경로로 동적 로드 후 attr을 반환.
    module_name: 예: "schema_ddl" (같은 디렉터리 파일명에서 .py를 뺀 형태)
    attr_name: 모듈에서 가져올 클래스/심볼 이름
    """
    try:
        # 상대 import (정상적으로 패키지로 로드된 경우)
        mod = __import__(f".{module_name}", globals(), locals(), [attr_name], 0)
        return getattr(mod, attr_name)
    except Exception:
        # 폴백: 현재 파일의 디렉터리에서 파일을 찾아 로드
        try:
            import importlib.util
            import pathlib
            base = pathlib.Path(__file__).parent
            candidate = base / (module_name + ".py")
            if not candidate.exists():
                # 상위 패키지 위치(예: core가 아니라 한 단계 위에 있을 경우)도 시도
                candidate2 = base.parent / (module_name + ".py")
                if candidate2.exists():
                    candidate = candidate2
            if not candidate.exists():
                raise ImportError(f"폴백 로드 실패: {candidate} 파일을 찾을 수 없습니다.")
            spec = importlib.util.spec_from_file_location(f"_fallback_{module_name}_{int(time.time())}", str(candidate))
            if spec is None or spec.loader is None:
                raise ImportError(f"폴백 로드 실패: spec 생성 실패 ({candidate})")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            if not hasattr(mod, attr_name):
                raise ImportError(f"폴백 로드된 {candidate}에 {attr_name}가 없습니다.")
            return getattr(mod, attr_name)
        except Exception as e:
            # 에러를 래핑하여 상위에서 알기 쉽게 던짐
            raise ImportError(f"모듈 로드 실패: {module_name}.{attr_name} — {e}") from e


# --------------------------------------------------------------------------
# 원래는 패키지 상대 import로 처리하던 mixin/헬퍼들을 안전하게 로드
# --------------------------------------------------------------------------
try:
    # 정상적인 패키지 상황에서의 상대 import 시도
    from .schema_ddl import SchemaDDLMixin
except Exception:
    SchemaDDLMixin = _safe_relative_import("schema_ddl", "SchemaDDLMixin")

try:
    from .candle_writer import CandleWriterMixin
except Exception:
    CandleWriterMixin = _safe_relative_import("candle_writer", "CandleWriterMixin")

try:
    from .query_helpers import QueryHelperMixin
except Exception:
    QueryHelperMixin = _safe_relative_import("query_helpers", "QueryHelperMixin")

# --------------------------------------------------------------------------
# psycopg2 지연 임포트 (환경에 따라 없을 수 있음)
# --------------------------------------------------------------------------
try:
    import psycopg2
    import psycopg2.extras as pg_extras
    from psycopg2.extras import execute_values, RealDictCursor
    from psycopg2.pool import SimpleConnectionPool as _SimpleConnectionPool
except Exception:
    psycopg2 = None  # type: ignore
    pg_extras = None
    execute_values = None
    RealDictCursor = None
    _SimpleConnectionPool = None  # type: ignore

# --------------------------------------------------------------------------
# 전역 연결 풀 (pool.py) — 프로세스 내 단 하나의 풀 유지
# --------------------------------------------------------------------------
_POOL_MODULE_AVAILABLE = False
_init_global_pool = None
_pool_get_connection = None
_pool_release_connection = None
_close_global_pool = None


def _try_load_pool_module() -> bool:
    """pool.py 모듈을 상대 또는 파일 경로 기반으로 로드합니다."""
    global _POOL_MODULE_AVAILABLE, _init_global_pool, _pool_get_connection
    global _pool_release_connection, _close_global_pool
    if _POOL_MODULE_AVAILABLE:
        return True
    try:
        # 상대 import (패키지로 로드된 경우)
        from ..pool import (  # type: ignore
            init_global_pool as _ig,
            get_connection as _gc,
            release_connection as _rc,
            close_global_pool as _cg,
        )
        _init_global_pool = _ig
        _pool_get_connection = _gc
        _pool_release_connection = _rc
        _close_global_pool = _cg
        _POOL_MODULE_AVAILABLE = True
        return True
    except (ImportError, ModuleNotFoundError):
        pass
    try:
        import importlib.util
        import pathlib
        _pool_path = pathlib.Path(__file__).parent.parent / "pool.py"
        if _pool_path.exists():
            _spec = importlib.util.spec_from_file_location("_timescale_pool_file", str(_pool_path))
            if _spec and _spec.loader:
                import sys as _sys
                _pool_mod = _sys.modules.get("_timescale_pool_file")
                if _pool_mod is None:
                    _pool_mod = importlib.util.module_from_spec(_spec)
                    _sys.modules["_timescale_pool_file"] = _pool_mod
                    _spec.loader.exec_module(_pool_mod)
                _init_global_pool = _pool_mod.init_global_pool
                _pool_get_connection = _pool_mod.get_connection
                _pool_release_connection = _pool_mod.release_connection
                _close_global_pool = _pool_mod.close_global_pool
                _POOL_MODULE_AVAILABLE = True
                return True
    except Exception:
        pass
    return False


def _build_dsn() -> str:
    """DSN 문자열 생성 — 환경 변수 기반 폴백 포함."""
    try:
        from ..timescale_utils import timescale_build_dsn  # type: ignore
        return timescale_build_dsn()
    except Exception:
        pass
    # 우선순위: DATABASE_URL -> TIMESCALE_DSN -> PG* vars
    url = os.environ.get("DATABASE_URL") or os.environ.get("TIMESCALE_DSN")
    if url:
        return url
    user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER") or os.environ.get("POSTGRES_APP_USER")
    password = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD") or os.environ.get("POSTGRES_APP_PASSWORD")
    host = os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT") or "5432"
    db = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB") or "upbit_trader"
    if user and password:
        pw = quote_plus(password)
        return f"postgresql://{user}:{pw}@{host}:{port}/{db}"
    parts = []
    if host:
        parts.append(f"host={host}")
    if port:
        parts.append(f"port={port}")
    if db:
        parts.append(f"dbname={db}")
    if user:
        parts.append(f"user={user}")
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


# --------------------------------------------------------------------------
# 로거 설정 (파일 단독 실행 시도 대비)
# --------------------------------------------------------------------------
logger = logging.getLogger("timescale_db")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [timescale_db] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.setLevel(logging.INFO)
logger.propagate = False

_CONNECT_RETRY_BASE_DELAY = 1.0  # 연결 재시도 기본 대기 시간 (초)

_try_load_pool_module()

# --------------------------------------------------------------------------
# 동시성 제어 환경변수 (세마포어 / executemany 청크)
# --------------------------------------------------------------------------
_MAX_CONCURRENT_OPS = int(os.getenv("TIMESCALE_MAX_CONCURRENT_OPS", "50"))  # 기본 동시 작업 제한
_OP_SEM_TIMEOUT_SEC = float(os.getenv("TIMESCALE_OP_SEM_TIMEOUT_SEC", "10.0"))  # 세마포어 획득 타임아웃
_EXECUTE_CHUNK_SIZE = int(os.getenv("TIMESCALE_EXECUTE_CHUNK_SIZE", "500"))  # executemany 청크 사이즈


def _chunked(iterable, size):
    """iterable을 size 단위로 나누는 제너레이터"""
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk


class TimescaleConnector(SchemaDDLMixin, CandleWriterMixin, QueryHelperMixin):
    """
    동기식 Timescale/Postgres 커넥터 — 스테이징 + upsert 헬퍼 포함.
    싱글톤 패턴으로 동작합니다.
    """
    _instance = None
    _lock = threading.Lock()
    _connection_logged = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, dsn: Optional[str] = None, ensure_schema_on_connect: bool = True):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.dsn = dsn or _build_dsn()
        self.conn = None
        self.ensure_schema_on_connect = ensure_schema_on_connect
        self._last_activity: float = time.time()
        self._connection_timeout: int = int(os.getenv("TIMESCALE_CONN_TIMEOUT_SEC", "60"))
        self._pool = None
        self._pool_lock = threading.Lock()
        self._conn_lock = threading.Lock()
        # registry: id(conn) -> "global" | "local" | False
        self._pool_conn_registry: dict = {}
        # last time global pool failed - used for cooldown logic
        self._last_global_pool_fail: float = 0.0
        self._global_fail_cooldown: float = float(os.getenv("TIMESCALE_GLOBAL_FAIL_COOLDOWN_SEC", "30"))
        # local pool sizing (safer defaults)
        self._local_minconn = int(os.getenv("TIMESCALE_LOCAL_MINCONN", "2"))
        self._local_maxconn = int(os.getenv("TIMESCALE_LOCAL_MAXCONN", "10"))
        # 동시 작업 제한용 세마포어 (프로세스 내부에서 DB 접속 사용량 제어)
        self._max_concurrent_ops = max(1, _MAX_CONCURRENT_OPS)
        self._op_semaphore = threading.BoundedSemaphore(self._max_concurrent_ops)
        self._op_sem_timeout = _OP_SEM_TIMEOUT_SEC

        # ------------------------------
        # 스키마 초기화 동기화 필드 (추가)
        # ------------------------------
        self._schema_lock = threading.Lock()
        self._schema_ensured = False
        self._last_schema_attempt = 0.0
        self._schema_attempt_cooldown = float(os.getenv("TIMESCALE_SCHEMA_COOLDOWN_SEC", "300"))  # 기본 5분

        logger.debug("[TimescaleDB] Connector initialized with schema cooldown: %ss", self._schema_attempt_cooldown)
        self._init_conn_pool()

    # -------------------
    # 연결 / 풀 관리
    # -------------------
    def connect(self, timeout: int = 5) -> bool:
        if self.conn:
            try:
                if not self.conn.closed:
                    with self.conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                    logger.debug("[TimescaleDB] 기존 연결 재사용")
                    return True
            except Exception as e:
                logger.debug("[TimescaleDB] 기존 연결 끊어짐, 재연결 시도: %s", e)
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

        if psycopg2 is None:
            logger.error("psycopg2 미설치. pip install psycopg2-binary 실행")
            return False

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if isinstance(self.dsn, str) and self.dsn.startswith(("postgresql://", "postgres://")):
                    parsed = urlparse(self.dsn)
                    user = unquote(parsed.username) if parsed.username else None
                    password = unquote(parsed.password) if parsed.password else None
                    host = parsed.hostname or os.environ.get("PGHOST", "127.0.0.1")
                    port = parsed.port or int(os.environ.get("PGPORT", 5432))
                    dbname = (parsed.path.lstrip("/") if parsed.path else None) or os.environ.get("PGDATABASE", "upbit_trader")
                    conn_kwargs = {
                        "host": host, "port": port, "dbname": dbname,
                        "connect_timeout": int(timeout),
                        "keepalives": 1, "keepalives_idle": 30,
                        "keepalives_interval": 10, "keepalives_count": 5,
                    }
                    if user:
                        conn_kwargs["user"] = user
                    if password:
                        conn_kwargs["password"] = password
                    self.conn = psycopg2.connect(**conn_kwargs)
                else:
                    try:
                        self.conn = psycopg2.connect(
                            self.dsn, connect_timeout=int(timeout),
                            keepalives=1, keepalives_idle=30,
                            keepalives_interval=10, keepalives_count=5,
                        )
                    except Exception:
                        dsn_with = f"{self.dsn} connect_timeout={int(timeout)}"
                        self.conn = psycopg2.connect(dsn_with)

                self.conn.autocommit = False
                if not TimescaleConnector._connection_logged:
                    logger.info("[TimescaleDB] ✅ 최초 연결 성공 (attempt %d/%d)", attempt + 1, max_retries)
                    TimescaleConnector._connection_logged = True
                else:
                    logger.debug("[TimescaleDB] 재연결 성공 (attempt %d/%d)", attempt + 1, max_retries)
                self._last_activity = time.time()

                # ------------------------------
                # 스키마 초기화: 프로세스 내에서 반복 실행을 막기 위해
                # double-checked locking + 쿨다운을 적용합니다.
                # ------------------------------
                if self.ensure_schema_on_connect:
                    now = time.time()
                    if (not getattr(self, "_schema_ensured", False)) and (now - getattr(self, "_last_schema_attempt", 0.0) > getattr(self, "_schema_attempt_cooldown", 300.0)):
                        with self._schema_lock:
                            if not getattr(self, "_schema_ensured", False):
                                self._last_schema_attempt = now
                                try:
                                    logger.info("[TimescaleDB] 스키마 무결성 검사 시작...")
                                    self.ensure_timescaledb_extension()
                                    self.ensure_candles_hypertable()
                                    self._schema_ensured = True
                                    logger.info("[TimescaleDB] 스키마 초기화 완료 및 이후 시도 차단")
                                except Exception as e:
                                    logger.warning("[TimescaleDB] 스키마 초기화 시도 중 오류(쿨다운 적용): %s", e)
                                    try:
                                        if self.conn and not self.conn.closed:
                                            self.conn.rollback()
                                    except Exception:
                                        logger.debug("[TimescaleDB] 롤백 실패 (무시): %s", e)
                return True

            except Exception as e:
                logger.warning("[TimescaleDB] 연결 실패 (attempt %d/%d): %s", attempt + 1, max_retries, str(e))
                self.conn = None
                if attempt < max_retries - 1:
                    time.sleep(_CONNECT_RETRY_BASE_DELAY * (2 ** attempt))

        logger.error("[TimescaleDB] ❌ 연결 최종 실패 (%d회 시도)", max_retries)
        return False

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None
        logger.debug("[TimescaleDB] close() 호출됨 (전역 풀은 유지)")

    def _init_conn_pool(self) -> bool:
        """
        로컬 풀 초기화.
        - 전역 풀 모듈이 존재하면 로컬 풀은 만들지 않습니다(중복 연결 폭증 방지).
        - 전역 풀을 사용할 수 없는 환경에서만 로컬 풀을 생성합니다.
        """
        try:
            with self._pool_lock:
                if self._pool is not None:
                    return True
                if _POOL_MODULE_AVAILABLE:
                    logger.info("[TimescaleDB] 전역 풀 사용 가능, 로컬 풀 생성 생략")
                    self._pool = None
                    return True
                if not self.dsn:
                    logger.error("[TimescaleDB] DSN 비어있음 — 로컬 풀 생성 실패")
                    return False
                minc = max(1, self._local_minconn)
                maxc = max(minc, self._local_maxconn)
                logger.info("[TimescaleDB] 로컬 연결 풀 생성 시도 (minconn=%d, maxconn=%d)", minc, maxc)
                if _SimpleConnectionPool is None:
                    logger.warning("[TimescaleDB] psycopg2.pool.SimpleConnectionPool 미사용 가능 - 로컬 풀 미생성")
                    self._pool = None
                    return False
                # 안전: 풀 생성 시도
                try:
                    self._pool = _SimpleConnectionPool(minconn=minc, maxconn=maxc, dsn=self.dsn)
                except Exception as exc:
                    logger.error("[TimescaleDB] 로컬 풀 생성 실패: %s", exc, exc_info=True)
                    self._pool = None
                    return False

                # 연결 검사
                try:
                    test_conn = self._pool.getconn()
                    if test_conn is None:
                        self._pool.closeall()
                        self._pool = None
                        return False
                    with test_conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                finally:
                    try:
                        if test_conn is not None:
                            self._pool.putconn(test_conn)
                    except Exception:
                        pass
                logger.info("[TimescaleDB] 로컬 연결 풀 초기화 완료 (maxconn=%d)", maxc)
                return True
        except Exception as exc:
            logger.error("[TimescaleDB] 로컬 연결 풀 초기화 실패: %s", exc, exc_info=True)
            self._pool = None
            return False

    # ------------------------------------------------------------------
    # 안전한 connection scope (context manager)
    # ------------------------------------------------------------------
    @contextmanager
    def _connection_scope(self) -> Generator[Tuple[Any, Any], None, None]:
        """
        항상 self._acquire_conn()로 얻은 connection을 반환하도록 보장합니다.
        예외가 발생하면 먼저 conn.rollback()을 시도한 뒤 self._release_conn(..., failed=True)을 호출합니다.
        """
        conn = None
        from_pool = False
        acquired_sem = False
        try:
            # 세마포어 획득 (타임아웃 적용)
            try:
                acquired_sem = self._op_semaphore.acquire(timeout=self._op_sem_timeout)
                if not acquired_sem:
                    raise RuntimeError("[TimescaleDB] 동시 작업 제한 초과: DB 작업을 얻지 못했습니다 (세마포어 타임아웃)")
            except Exception as e:
                logger.warning("[TimescaleDB] 세마포어 획득 실패/타임아웃: %s", e)
                raise

            res = self._acquire_conn()
            if isinstance(res, tuple) and len(res) == 2:
                conn, from_pool = res
            else:
                conn = res
                from_pool = False
            yield (conn, from_pool)
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                if failed:
                    try:
                        if conn is not None and not getattr(conn, "closed", False):
                            conn.rollback()
                    except Exception:
                        pass
                try:
                    if conn is not None:
                        self._release_conn(conn, from_pool, failed=failed)
                except Exception:
                    logger.exception("[TimescaleDB] _connection_scope: _release_conn 호출 중 예외")
            except Exception:
                logger.exception("[TimescaleDB] _connection_scope: finally 블록 예외")
            finally:
                # 세마포어 해제는 반드시 수행
                if acquired_sem:
                    try:
                        self._op_semaphore.release()
                    except Exception:
                        logger.debug("[TimescaleDB] 세마포어 해제 실패", exc_info=True)

    # ------------------------------------------------------------------
    # 권장되는 커넥션/커서 컨텍스트 (외부에서 사용 권장)
    # 사용 예:
    #   with connector.get_connection_ctx() as (conn, cur, from_pool):
    #       cur.execute(...)
    # ------------------------------------------------------------------
    @contextmanager
    def get_connection_ctx(self):
        with self._connection_scope() as (conn, from_pool):
            cur = None
            try:
                # RealDictCursor가 있는 경우 기본으로 사용
                if RealDictCursor is not None:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                else:
                    cur = conn.cursor()
                yield (conn, cur, from_pool)
            finally:
                try:
                    if cur is not None:
                        try:
                            cur.close()
                        except Exception:
                            pass
                except Exception:
                    logger.debug("[TimescaleDB] get_connection_ctx: cursor close 예외", exc_info=True)

    # -------------------
    # _acquire_conn / policy 개선
    # -------------------
    def _acquire_conn(self):
        """
        전역 풀 -> 로컬 풀 -> 단일 연결 순으로 시도합니다.
        정책 변경(안정성):
         - 전역 풀이 사용 가능하더라도 get_connection 실패가 반복되면 쿨다운을 적용하여
           즉시 로컬 풀을 만들지 않고 단일 연결(fallback self.conn)로 회귀함.
         - 로컬 풀은 전역 풀이 없을 때만 생성/사용 (중복 풀 방지).
        """
        # 1) 전역 풀 시도 (모듈 API)
        if _POOL_MODULE_AVAILABLE and _pool_get_connection is not None:
            now = time.time()
            if now - getattr(self, "_last_global_pool_fail", 0.0) > getattr(self, "_global_fail_cooldown", 30.0):
                try:
                    conn = _pool_get_connection()
                    try:
                        logger.debug("[TimescaleDB.DEBUG] 전역 풀에서 연결 획득 id=%s closed=%s", id(conn), getattr(conn, "closed", None))
                    except Exception:
                        logger.debug("[TimescaleDB.DEBUG] 전역 풀에서 연결 획득 id=%s", id(conn))
                    return conn, "global"
                except Exception as exc:
                    self._last_global_pool_fail = now
                    logger.warning("[TimescaleDB] 전역 풀 연결 획득 실패 - 쿨다운 적용: %s", exc)
            else:
                logger.debug("[TimescaleDB] 전역 풀 최근 실패 쿨다운 중 - 스킵 (남은 %.1fs)", max(0.0, self._global_fail_cooldown - (time.time() - self._last_global_pool_fail)))

        # 2) 로컬 풀 시도 (단, 전역 풀이 사용 불가한 환경에서만)
        with self._pool_lock:
            pool = self._pool

        if pool is not None:
            for attempt in range(3):
                try:
                    conn = pool.getconn()
                    if conn is None:
                        if attempt < 2:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        break
                    if getattr(conn, "closed", False):
                        try:
                            pool.putconn(conn, close=True)
                        except Exception:
                            pass
                        if attempt < 2:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        break
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                            cur.fetchone()
                        try:
                            logger.debug("[TimescaleDB.DEBUG] 로컬 풀에서 연결 획득 id=%s", id(conn))
                        except Exception:
                            logger.debug("[TimescaleDB.DEBUG] 로컬 풀에서 연결 획득")
                        return conn, "local"
                    except Exception as ping_exc:
                        logger.warning("[TimescaleDB] 풀 연결 ping 실패 (attempt %d/3): %s", attempt + 1, ping_exc)
                        try:
                            pool.putconn(conn, close=True)
                        except Exception:
                            pass
                        if attempt < 2:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        break
                except Exception as exc:
                    logger.warning("[TimescaleDB] 풀 연결 획득 실패 (attempt %d/3): %s", attempt + 1, exc)
                    if attempt < 2:
                        time.sleep(0.1 * (attempt + 1))
                        continue
                    break

        # 3) 단일 연결 폴백 (안정성 우선)
        logger.info("[TimescaleDB] 단일 연결 폴백 모드 사용")
        with self._conn_lock:
            if not self._ensure_connection():
                raise RuntimeError("[TimescaleDB] 연결 실패")
            try:
                logger.debug("[TimescaleDB.DEBUG] 단일 self.conn 사용 id=%s", id(self.conn) if self.conn is not None else None)
            except Exception:
                logger.debug("[TimescaleDB.DEBUG] 단일 self.conn 사용")
            return self.conn, False

    def _release_conn(self, conn, from_pool, failed: bool = False) -> None:
        """
        conn 반환/종료 처리.
        from_pool: "global" | "local" | False
        """
        if conn is None:
            return
        try:
            # 전역 풀에서 얻은 경우
            if from_pool == "global" or from_pool is True:
                try:
                    logger.debug("[TimescaleDB.DEBUG] release -> global id=%s failed=%s", id(conn), failed)
                except Exception:
                    logger.debug("[TimescaleDB.DEBUG] release -> global id=%s failed=%s", id(conn), failed)

                if _POOL_MODULE_AVAILABLE and _pool_release_connection is not None:
                    try:
                        _pool_release_connection(conn, failed=failed)
                        logger.debug("[TimescaleDB] 전역 풀에 연결 반환(id=%s) 성공 (failed=%s)", id(conn), failed)
                        return
                    except Exception as exc:
                        logger.warning("[TimescaleDB] 전역 풀 반환 실패(모듈 API): %s", exc)

                with self._pool_lock:
                    pool = self._pool
                if pool is not None:
                    try:
                        pool.putconn(conn, close=failed)
                        logger.debug("[TimescaleDB] 전역 풀 fallback으로 로컬풀에 putconn(id=%s) 시도", id(conn))
                        return
                    except Exception as exc:
                        logger.warning("[TimescaleDB] 전역 풀 반환 실패(풀.putconn): %s", exc)

            # 로컬 풀에서 얻은 경우
            if from_pool == "local":
                try:
                    logger.debug("[TimescaleDB.DEBUG] release -> local id=%s failed=%s", id(conn), failed)
                except Exception:
                    logger.debug("[TimescaleDB.DEBUG] release -> local id=%s failed=%s", id(conn), failed)

                with self._pool_lock:
                    pool = self._pool
                if pool is not None:
                    try:
                        pool.putconn(conn, close=failed)
                        logger.debug("[TimescaleDB] 로컬 풀에 연결 반환(id=%s) 성공 (failed=%s)", id(conn), failed)
                        return
                    except Exception as exc:
                        logger.warning("[TimescaleDB] 로컬 풀 반환 실패: %s", exc)
                try:
                    conn.close()
                except Exception:
                    pass
                return

            # 단일 연결(fallback) 또는 알 수 없는 태그
            if failed:
                try:
                    if getattr(self, "conn", None) is conn:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        self.conn = None
                        logger.debug("[TimescaleDB] 단일 연결 실패로 self.conn 무효화(id=%s)", id(conn))
                except Exception:
                    pass
            else:
                try:
                    conn.close()
                except Exception:
                    pass
                logger.debug("[TimescaleDB] 출처 불명 연결(id=%s) 닫음", id(conn))
        except Exception:
            logger.exception("[TimescaleDB] _release_conn 예외 처리 중 오류")

    # -------------------
    # DB 실행 헬퍼: execute / executemany / fetchall
    # - executemany는 대용량일 때 execute_values로 분할 처리
    # - execute_values에서 SQL placeholder 문제 발생 시 template 변환 후 재시도
    # -------------------
    def execute(self, sql: str, params: Optional[Iterable[Any]] = None, commit: bool = True) -> None:
        with self.get_connection_ctx() as (conn, cur, _):
            cur.execute(sql, params)
            if commit:
                try:
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise

    def executemany(self, insert_sql: str, rows: Iterable[Iterable[Any]], page_size: Optional[int] = None, commit: bool = True) -> None:
        """
        대량 insert/update 지원:
        - 가능하면 psycopg2.extras.execute_values 사용 (성능 좋음)
        - 환경변수로 지정된 청크(_EXECUTE_CHUNK_SIZE) 단위로 나눠 실행
        - execute_values에서 "the query contains more than one '%s' placeholder" 오류가 발생하면
          SQL을 execute_values 호환 형태로 변환(template 사용)하여 재시도합니다.
        """
        page = page_size or _EXECUTE_CHUNK_SIZE
        # materialize iterator for chunking
        if isinstance(rows, list):
            rows_iterable = rows
        else:
            rows_iterable = list(rows)
        if not rows_iterable:
            return

        # If execute_values available, use it in chunks
        if execute_values is not None:
            for chunk in _chunked(rows_iterable, page):
                with self.get_connection_ctx() as (conn, cur, _):
                    try:
                        # 시도 1: 원본 insert_sql 그대로 사용
                        execute_values(cur, insert_sql, chunk, page_size=page)
                        if commit:
                            conn.commit()
                    except Exception as exc:
                        # execute_values가 특정한 ValueError를 던지면, template 방식으로 재시도
                        tried_retry = False
                        try:
                            msg = str(exc)
                            if isinstance(exc, ValueError) and "more than one '%s' placeholder" in msg:
                                # VALUES(...) 부분에서 괄호 부분을 템플릿으로 추출
                                m = re.search(r"VALUES\s*\((.*?)\)", insert_sql, flags=re.IGNORECASE | re.DOTALL)
                                if m:
                                    values_tpl = "(" + m.group(1) + ")"
                                    # SQL을 "VALUES %s" 형태로 변환
                                    new_sql = re.sub(r"VALUES\s*\(.*?\)", "VALUES %s", insert_sql, flags=re.IGNORECASE | re.DOTALL)
                                    try:
                                        execute_values(cur, new_sql, chunk, template=values_tpl, page_size=page)
                                        if commit:
                                            conn.commit()
                                        tried_retry = True
                                    except Exception:
                                        tried_retry = False
                        except Exception:
                            tried_retry = False

                        if tried_retry:
                            # 재시도 성공: 다음 청크로 진행
                            continue

                        # 위 재시도들도 실패한 경우: 롤백하고 실패 청크를 저장
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        logger.exception("[TimescaleDB] execute_values 실패 — chunk saved to isolator")
                        try:
                            isol_dir = "./stager_isolated"
                            os.makedirs(isol_dir, exist_ok=True)
                            filename = f"failed_chunk_{int(time.time())}.jsonl"
                            with open(os.path.join(isol_dir, filename), "w", encoding="utf-8") as f:
                                for r in chunk:
                                    f.write(json.dumps(r, default=str) + "\n")
                            logger.warning("[TimescaleDB] 실패 청크를 %s 에 저장했습니다", filename)
                        except Exception:
                            logger.exception("[TimescaleDB] 실패 청크 저장 중 예외")
                        raise
        else:
            # fallback: psycopg2 cursor.executemany with chunking
            for chunk in _chunked(rows_iterable, page):
                with self.get_connection_ctx() as (conn, cur, _):
                    try:
                        cur.executemany(insert_sql, chunk)
                        if commit:
                            conn.commit()
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        logger.exception("[TimescaleDB] executemany 실패 — chunk saved to isolator")
                        try:
                            isol_dir = "./stager_isolated"
                            os.makedirs(isol_dir, exist_ok=True)
                            filename = f"failed_chunk_{int(time.time())}.jsonl"
                            with open(os.path.join(isol_dir, filename), "w", encoding="utf-8") as f:
                                for r in chunk:
                                    f.write(json.dumps(r, default=str) + "\n")
                            logger.warning("[TimescaleDB] 실패 청크를 %s 에 저장했습니다", filename)
                        except Exception:
                            logger.exception("[TimescaleDB] 실패 청크 저장 중 예외")
                        raise

    def fetchall(self, sql: str, params: Optional[Iterable[Any]] = None) -> List[dict]:
        with self.get_connection_ctx() as (conn, cur, _):
            cur.execute(sql, params)
            rows = cur.fetchall()
            # RealDictCursor인 경우 dict 반환, 아니면 튜플->dict 로직 필요 (생략)
            return rows

    # -------------------
    # 내부 헬퍼: ensure connection
    # -------------------
    def _ensure_connection(self) -> bool:
        """단일 self.conn 보장(폴백 모드)"""
        if self.conn and not getattr(self.conn, "closed", True):
            return True
        try:
            ok = self.connect(timeout=int(os.getenv("TIMESCALE_CONN_TIMEOUT_SEC", "10")))
            return ok
        except Exception:
            return False

    # -------------------
    # 기타 유틸리티/관리 메서드 (간단히 노출)
    # -------------------
    def dump_pool_debug(self) -> dict:
        """debug_pool_dump 등에서 호출할 수 있는 상태 덤프를 반환"""
        try:
            with self._pool_lock:
                pool = self._pool
            info = {
                "has_global_pool_module": _POOL_MODULE_AVAILABLE,
                "local_pool": None,
                "max_concurrent_ops": self._max_concurrent_ops,
            }
            if pool is not None:
                try:
                    # SimpleConnectionPool에는 public API가 제한적이므로 best-effort
                    info["local_pool"] = {"minconn": getattr(pool, "minconn", None), "maxconn": getattr(pool, "maxconn", None)}
                except Exception:
                    info["local_pool"] = "unknown"
            return info
        except Exception:
            logger.exception("[TimescaleDB] dump_pool_debug 실패")
            return {}

# 파일 끝