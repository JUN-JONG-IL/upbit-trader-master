# -*- coding: utf-8 -*-
"""PostgreSQL 복제 상태 탭"""
from __future__ import annotations
import os
import logging
import threading
from typing import Optional, Dict, Tuple

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "replication_tab.ui")

# ---------------------------------------------------------------------
# 모듈 레벨: 간단한 ThreadedConnectionPool 캐시
# - 주기 폴링용으로 반복 생성되는 단기 접속을 방지하기 위해 풀을 사용합니다.
# - 풀 생성이 불가능한 환경(psycopg2.pool 미설치 등)에서는 direct connect로 폴백합니다.
# ---------------------------------------------------------------------
_pool_lock = threading.Lock()
_pools = {}  # key -> ThreadedConnectionPool
_POOL_MINCONN = 1
_POOL_MAXCONN = 3  # UI 폴링용이므로 작게 설정

def _build_connect_kwargs(params: Dict) -> Dict:
    """conn_params 딕셔너리에서 psycopg2.connect/ThreadedConnectionPool에 사용할 kwargs 생성."""
    host = params.get("host") or "localhost"
    port = int(params.get("port", 5433))
    db = params.get("database") or params.get("dbname") or params.get("db") or ""
    user = params.get("user") or "postgres"
    password = params.get("password") or ""
    return {"host": host, "port": port, "dbname": db, "user": user, "password": password}

def _pool_key(kwargs: Dict) -> str:
    return f"{kwargs.get('host')}:{kwargs.get('port')}/{kwargs.get('dbname')}@{kwargs.get('user')}"

def _ensure_pool(kwargs: Dict):
    """해당 키에 대한 ThreadedConnectionPool을 생성하거나 기존 것을 반환. 실패 시 None."""
    key = _pool_key(kwargs)
    with _pool_lock:
        pool = _pools.get(key)
        if pool:
            return pool
        try:
            from psycopg2.pool import ThreadedConnectionPool  # type: ignore
        except Exception as e:
            logger.debug("[ReplicationTab] ThreadedConnectionPool 사용 불가: %s", e)
            return None
        try:
            pool = ThreadedConnectionPool(
                _POOL_MINCONN,
                _POOL_MAXCONN,
                host=kwargs.get("host"),
                port=kwargs.get("port"),
                dbname=kwargs.get("dbname"),
                user=kwargs.get("user"),
                password=kwargs.get("password"),
            )
            # 간단한 검증: 1개 얻어 반환
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
                logger.warning("[ReplicationTab] 풀 초기화 테스트 실패")
                return None
            _pools[key] = pool
            logger.info("[ReplicationTab] connection pool 생성: %s", key)
            return pool
        except Exception as e:
            logger.warning("[ReplicationTab] ThreadedConnectionPool 생성 실패: %s", e)
            return None

def _get_conn(params: Dict) -> Tuple[Optional[object], Optional[object]]:
    """
    풀에�� conn을 얻거나 direct connect를 수행.
    반환: (conn, pool_or_None). pool_or_None이 None이면 direct connect(종료 시 conn.close() 필요).
    """
    kwargs = _build_connect_kwargs(params)
    pool = _ensure_pool(kwargs)
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
        except Exception as e:
            logger.debug("[ReplicationTab] pool.getconn 실패, direct connect로 폴백: %s", e)
    # direct connect fallback
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(**kwargs, connect_timeout=3)
        return conn, None
    except Exception as e:
        logger.debug("[ReplicationTab] direct connect 실패: %s", e)
        return None, None

def _release_conn(conn, pool):
    """pool이면 putconn, 아니면 close(). 안전하게 처리."""
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
        logger.exception("[ReplicationTab] _release_conn 예외 처리 중 오류")

# ---------------------------------------------------------------------
# Replication UI 탭
# ---------------------------------------------------------------------
if _HAS_QT:
    class ReplicationTab(QWidget):
        """복제 상태 탭 (Primary/Replica 지연, WAL 수신 속도, 동기화 상태)."""

        def __init__(self, parent=None, conn_params=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[ReplicationTab] UI 로드 실패: %s", exc)
            # 폴링 타이머
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._update)
            # 수동 갱신 버튼 연결(있으면)
            try:
                self.btnRefresh.clicked.connect(self._update)
            except AttributeError as exc:
                logger.debug("[ReplicationTab] 시그널 연결 실패: %s", exc)

        def start_updates(self, interval_ms: int = 10_000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update(self) -> None:
            """Primary에서 복제 상태(pg_stat_replication)를 조회한다."""
            params = self._conn_params or {}
            # UI 폴링에서는 primary(복제 제공자)에 연결해야 하므로 포트 기본값 5432/5433 환경에 따라 설정 가능
            # conn_params가 비어있으면 로컬 기본값 사용
            try:
                conn, pool = _get_conn(params)
                if conn is None:
                    raise RuntimeError("DB 연결을 얻을 수 없음")
                cur = None
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT client_addr, state, sent_lsn, write_lsn, "
                        "flush_lsn, replay_lsn, sync_state "
                        "FROM pg_stat_replication"
                    )
                    rows = cur.fetchall()
                    tbl = getattr(self, "tableReplication", None)
                    if tbl is not None:
                        tbl.setRowCount(0)
                        for row in rows:
                            r = tbl.rowCount()
                            tbl.insertRow(r)
                            from PyQt5.QtWidgets import QTableWidgetItem
                            for c, val in enumerate(row):
                                tbl.setItem(r, c, QTableWidgetItem(str(val) if val is not None else "-"))
                except Exception as exc:
                    logger.debug("[ReplicationTab] 복제 상태 조회 실패: %s", exc, exc_info=True)
                finally:
                    try:
                        if cur is not None:
                            try:
                                cur.close()
                            except Exception:
                                pass
                    finally:
                        _release_conn(conn, pool)
            except Exception as exc:
                logger.debug("[ReplicationTab] _update 전체 실패: %s", exc)

else:
    class ReplicationTab:  # type: ignore[no-redef]
        def __init__(self, parent=None, conn_params=None): pass
        def start_updates(self, interval_ms: int = 10_000) -> None: pass
        def stop_updates(self) -> None: pass