# -*- coding: utf-8 -*-
"""TimescaleDB 탭 공통 백그라운드 Worker 유틸리티

모든 탭이 공유하는 psycopg2 쿼리 실행 Worker.
메인스레드 블로킹을 완전히 방지하기 위해 QThread 기반으로 작성되었습니다.

변경 요약 (한국어):
- 각 Worker에서 매번 psycopg2.connect()를 호출하는 대신 스레드 안전한
  ThreadedConnectionPool을 사용하도록 변경했습니다.
- 풀은 커넥션 파라미터별로 캐시(딕셔너리)되어 재사용됩니다.
- 풀 생성 실패 시(또는 psycopg2.pool 미사용 환경)에는 기존처럼 직접 연결로 폴백합니다.
- 모든 경로에서 연결을 반환/닫도록 보장하여 커넥션 누수를 방지합니다.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional, Tuple

try:
    from PyQt5.QtCore import QThread, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

# TimescaleDB 기본 포트 및 DB명 (config.yaml TIMESCALE.DATABASE 기준)
_DEFAULT_PORT = 58529
_DEFAULT_DB = "upbit_trader"

# ----------------------------------------------------------------------
# 커넥션 풀 관리(모듈 레벨)
# - _pools: DSN 키 -> ThreadedConnectionPool 인스턴스
# - _pool_lock: 풀 생성/조회 시 동기화용
# ----------------------------------------------------------------------
_pool_lock = threading.Lock()
_pools: dict = {}  # key -> pool
# 풀 설정: 필요 시 환경변수 또는 설정에서 변경 가능
_POOL_MINCONN = 1
_POOL_MAXCONN = 10


def _normalize_host(host: str) -> str:
    """Windows에서 localhost가 ::1(IPv6)로 해석되는 문제를 방지합니다.
    localhost 또는 빈 문자열은 127.0.0.1(IPv4)로 강제 변환합니다.
    """
    if not host or str(host).strip().lower() == "localhost":
        return "127.0.0.1"
    return str(host).strip()


def build_connect_kwargs(conn_params: dict, connect_timeout: int = 3) -> dict:
    """conn_params 딕셔너리를 psycopg2.connect() 키워드 인수로 변환합니다.

    TimescaleSettings.load_connection()이 반환하는 "db"/"pass" 키와
    psycopg2 표준 "database"/"password" 키를 모두 지원합니다.
    """
    p = conn_params or {}

    def _first_nonempty(keys, default):
        for k in keys:
            v = p.get(k)
            if v is not None and str(v).strip():
                return v
        return default

    def _first_set(keys, default):
        for k in keys:
            if k in p:
                return p[k]
        return default

    database = _first_nonempty(["database", "dbname", "db"], _DEFAULT_DB)
    password = _first_set(["password", "pass", "passwd"], "")
    return {
        "host": _normalize_host(p.get("host", "") or ""),
        "port": int(p.get("port", _DEFAULT_PORT)),
        "database": database,
        "user": p.get("user", "") or "postgres",
        "password": password,
        "connect_timeout": connect_timeout,
    }


def _pool_key_from_kwargs(kwargs: dict) -> str:
    """풀 키 생성: host:port/database@user"""
    return f"{kwargs.get('host')}:{kwargs.get('port')}/{kwargs.get('database')}@{kwargs.get('user')}"


def _ensure_pool_for_kwargs(kwargs: dict):
    """해당 연결 파라미터에 대해 ThreadedConnectionPool을 생성하거나 반환합니다.
    실패 시 None 반환(이 경우 direct connect로 폴백).
    """
    key = _pool_key_from_kwargs(kwargs)
    with _pool_lock:
        pool = _pools.get(key)
        if pool:
            return pool
        # lazy import pool class
        try:
            from psycopg2.pool import ThreadedConnectionPool
        except Exception as e:
            logger.debug("[db_worker] psycopg2.pool.ThreadedConnectionPool 사용 불가: %s", e)
            return None
        try:
            pool = ThreadedConnectionPool(
                _POOL_MINCONN,
                _POOL_MAXCONN,
                host=kwargs.get("host"),
                port=kwargs.get("port"),
                database=kwargs.get("database"),
                user=kwargs.get("user"),
                password=kwargs.get("password"),
                connect_timeout=kwargs.get("connect_timeout", 3),
            )
            # 간단히 테스트 커넥션 획득/반환
            try:
                conn = pool.getconn()
                if getattr(conn, "closed", 0):
                    # 닫힌 커넥션이면 close 처리
                    pool.putconn(conn, close=True)
                    raise RuntimeError("초기 풀 커넥션이 닫혀 있음")
                pool.putconn(conn, close=False)
            except Exception:
                # 풀 생성 실패 시 정리 후 None 반환
                try:
                    pool.closeall()
                except Exception:
                    pass
                logger.warning("[db_worker] 풀 생성 후 초기화 실패")
                return None
            _pools[key] = pool
            logger.info("[db_worker] connection pool 생성: %s (min=%d,max=%d)", key, _POOL_MINCONN, _POOL_MAXCONN)
            return pool
        except Exception as e:
            logger.warning("[db_worker] ThreadedConnectionPool 생성 실패: %s", e)
            return None


def _get_conn_from_pool_or_direct(conn_params: dict) -> Tuple[object, Optional[object]]:
    """
    풀에서 연결을 얻습니다.
    반환: (conn, pool_or_None)
      pool_or_None이 None이면 직접 연결(직접 close 필요)
      pool_or_None이 pool이면 반환 시 pool.putconn(conn)을 사용해�� 합니다.
    """
    kwargs = build_connect_kwargs(conn_params)
    pool = _ensure_pool_for_kwargs(kwargs)
    if pool is not None:
        # 풀에서 가져오기 (비정상 커넥션이면 재시도)
        try:
            conn = pool.getconn()
            # 만약 이미 닫힌 커넥션이면 재시도 또는 예외 처리
            if getattr(conn, "closed", 0):
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = pool.getconn()
            return conn, pool
        except Exception as e:
            logger.debug("[db_worker] pool.getconn 실패, direct connect로 폴백: %s", e)
            # fallback to direct connect
    # direct connect (폴백)
    try:
        import psycopg2
        kwargs_direct = kwargs.copy()
        # psycopg2.connect expects 'dbname' or 'database'
        if "database" in kwargs_direct:
            kwargs_direct["dbname"] = kwargs_direct.pop("database")
        conn = psycopg2.connect(**kwargs_direct)
        return conn, None
    except Exception as e:
        logger.error("[db_worker] direct psycopg2.connect 실패: %s", e)
        raise


def _release_conn(conn, pool):
    """pool이 주어지면 pool.putconn, 아니면 conn.close()"""
    try:
        if conn is None:
            return
        if pool is not None:
            try:
                pool.putconn(conn, close=False)
            except Exception:
                # 실패하면 안전하게 닫음
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
        logger.exception("[db_worker] _release_conn 예외")


# ------------------------------------------------------------------
# QThread Worker들 (풀 사용)
# ------------------------------------------------------------------
if _HAS_QT:
    class TimescaleWorker(QThread):
        """백그라운드 psycopg2 쿼리 실행 Worker.

        메인스레드 블로킹 완전 방지.
        이제 connection pool을 사용하여 커넥션 재사용을 권장합니다.
        """

        finished = pyqtSignal(object)   # 결과 (rows list)
        error = pyqtSignal(str)         # 에러 메시지

        def __init__(self, conn_params: dict, query: str, params: Optional[tuple] = None, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._query = query
            self._params = params or ()

        def run(self) -> None:
            """백그라운드 스레드에서 쿼리를 실행하고 결과를 시그널로 전달합니다."""
            conn = None
            pool = None
            try:
                conn, pool = _get_conn_from_pool_or_direct(self._conn_params)
                with conn.cursor() as cur:
                    cur.execute(self._query, self._params)
                    rows = cur.fetchall()
                # 성공 시 결과 전송
                self.finished.emit(rows)
            except Exception as exc:
                logger.debug("[TimescaleWorker] 쿼리 오류: %s", exc)
                try:
                    self.error.emit(str(exc))
                except Exception:
                    pass
            finally:
                _release_conn(conn, pool)

    class TimescaleWriteWorker(QThread):
        """백그라운드 psycopg2 DML(DELETE/UPDATE/INSERT) 실행 Worker.

        트랜잭션 커밋 후 영향받은 행 수를 시그널로 반환합니다.
        """

        finished = pyqtSignal(int)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, query: str, params: Optional[tuple] = None, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._query = query
            self._params = params or ()

        def run(self) -> None:
            """백그라운드 스레드에서 DML을 실행하고 결과를 시그널로 전달합니다."""
            conn = None
            pool = None
            try:
                conn, pool = _get_conn_from_pool_or_direct(self._conn_params)
                # 쓰기 작업은 트랜잭션 관리 필요
                try:
                    conn.autocommit = False
                except Exception:
                    # 일부 풀/커넥션은 autocommit 속성 설정 방식을 다르게 처리할 수 있음
                    pass
                try:
                    with conn.cursor() as cur:
                        cur.execute(self._query, self._params)
                        rowcount = cur.rowcount
                    try:
                        conn.commit()
                    except Exception:
                        # commit 실패 시 rollback 시도
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        raise
                    self.finished.emit(rowcount if rowcount >= 0 else 0)
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
            except Exception as exc:
                logger.debug("[TimescaleWriteWorker] DML 오류: %s", exc)
                try:
                    self.error.emit(str(exc))
                except Exception:
                    pass
            finally:
                _release_conn(conn, pool)

    class TimescaleVacuumWorker(QThread):
        """백그라운드 VACUUM 실행 Worker.

        autocommit=True 모드로 VACUUM을 실행합니다.
        """

        finished = pyqtSignal(str)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, table_name: str = "", parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._table_name = table_name.strip()

        def run(self) -> None:
            """백그라운드 스레드에서 VACUUM을 실행합니다."""
            conn = None
            pool = None
            try:
                conn, pool = _get_conn_from_pool_or_direct(self._conn_params)
                try:
                    conn.autocommit = True
                except Exception:
                    pass
                from psycopg2 import sql as pgsql  # 지연 임포트
                with conn.cursor() as cur:
                    if self._table_name:
                        stmt = pgsql.SQL("VACUUM ANALYZE {}").format(pgsql.Identifier(self._table_name))
                        cur.execute(stmt)
                        msg = f"VACUUM ANALYZE {self._table_name} 완료"
                    else:
                        cur.execute("VACUUM ANALYZE")
                        msg = "VACUUM ANALYZE (전체) 완료"
                self.finished.emit(msg)
            except Exception as exc:
                logger.debug("[TimescaleVacuumWorker] VACUUM 오류: %s", exc)
                try:
                    self.error.emit(str(exc))
                except Exception:
                    pass
            finally:
                _release_conn(conn, pool)

    class TimescaleQueryWorker(QThread):
        """백그라운드 psycopg2 SELECT 실행 Worker — 컬럼 헤더 + 행 데이터를 함께 반환합니다."""

        finished = pyqtSignal(list, list)
        error = pyqtSignal(str)

        def __init__(self, conn_params: dict, query: str, params: Optional[tuple] = None, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}
            self._query = query
            self._params = params or ()

        def run(self) -> None:
            """백그라운드 스레드에서 쿼리를 실행하고 헤더+행을 시그널로 전달합니다."""
            conn = None
            pool = None
            try:
                conn, pool = _get_conn_from_pool_or_direct(self._conn_params)
                with conn.cursor() as cur:
                    cur.execute(self._query, self._params or None)
                    headers = [d[0] for d in (cur.description or [])]
                    rows = [list(r) for r in cur.fetchall()]
                self.finished.emit(headers, rows)
            except Exception as exc:
                logger.debug("[TimescaleQueryWorker] 쿼리 오류: %s", exc)
                try:
                    self.error.emit(str(exc))
                except Exception:
                    pass
            finally:
                _release_conn(conn, pool)

else:
    # PyQt 설치가 없을 때의 스텁 (동작 보조용)
    class TimescaleWorker:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, query="", params=None, parent=None):
            pass

    class TimescaleWriteWorker:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, query="", params=None, parent=None):
            pass

    class TimescaleVacuumWorker:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, table_name="", parent=None):
            pass

    class TimescaleQueryWorker:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, query="", params=None, parent=None):
            pass