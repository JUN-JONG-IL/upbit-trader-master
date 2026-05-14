#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 복제 모니터 모듈.

Primary/Replica 복제 지연(replication lag) 및 복제 슬롯 상태를
주기적으로 수집하여 제공한다.

변경 요약 (한국어):
- 기존에는 매 폴링마다 psycopg2.connect()를 직접 호출하여 많은 단기 연결을 만들어 냈습니다.
- 이제 ThreadedConnectionPool을 사용해 DSN별 풀을 생성하고 재사용합니다.
- 풀 생성이 불가능한 환경(또는 psycopg2 미설치)에서는 기존 direct connect 폴백을 유지합니다.
- 모든 경로에서 커서와 연결(또는 풀 반환)을 finally 블록에서 안전하게 정리합니다.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional, Tuple

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore
    _HAS_PSYCOPG2 = False

logger = logging.getLogger(__name__)

# Primary 상태 조회 쿼리 (pg_stat_replication 뷰 사용)
_QUERY_PRIMARY_STATUS = """
SELECT
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    sync_state
FROM pg_stat_replication;
"""

# Replica 복제 지연 조회 쿼리
_QUERY_REPLICA_LAG = """
SELECT
    now() - pg_last_xact_replay_timestamp() AS replication_delay,
    pg_is_in_recovery()                     AS is_replica,
    pg_last_wal_receive_lsn()               AS receive_lsn,
    pg_last_wal_replay_lsn()                AS replay_lsn;
"""

# ------------------------------------------------------------------
# 모듈 레벨: DSN -> ThreadedConnectionPool 캐시 (스레드 안전)
# ------------------------------------------------------------------
_pool_lock = threading.Lock()
_pools: Dict[str, object] = {}  # key: dsn 문자열 -> ThreadedConnectionPool 인스턴스
_POOL_MINCONN = 1
_POOL_MAXCONN = 10


def _pool_key_from_dsn(dsn: str) -> str:
    """풀 키로 사용할 간단한 식별자 생성 (dsn 문자열 자체 사용)."""
    return dsn.strip()


def _ensure_pool_for_dsn(dsn: str):
    """
    주어진 DSN 문자열에 대해 ThreadedConnectionPool을 생성하거나 기존 것을 반환.
    실패 시 None을 반환하여 direct connect로 폴백하도록 합니다.
    """
    if not _HAS_PSYCOPG2:
        return None
    key = _pool_key_from_dsn(dsn)
    with _pool_lock:
        pool = _pools.get(key)
        if pool:
            return pool
        try:
            # 지연 임포트: ThreadedConnectionPool이 사용 가능한지 확인
            from psycopg2.pool import ThreadedConnectionPool  # type: ignore
        except Exception as e:
            logger.debug("[ReplicationMonitor] psycopg2.pool.ThreadedConnectionPool 사용 불가: %s", e)
            return None
        try:
            # ThreadedConnectionPool 생성: dsn 파라미터로 DSN 문자열 전달
            pool = ThreadedConnectionPool(
                _POOL_MINCONN,
                _POOL_MAXCONN,
                dsn=dsn,
            )
            # 간단히 풀에서 커넥션 획득/반환 테스트
            try:
                conn = pool.getconn()
                # 만약 커넥션이 이미 닫혀있다면 정리
                if getattr(conn, "closed", 0):
                    try:
                        pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    raise RuntimeError("풀 초기화: 획득한 커넥션이 닫혀 있음")
                pool.putconn(conn)
            except Exception:
                try:
                    pool.closeall()
                except Exception:
                    pass
                logger.warning("[ReplicationMonitor] 풀 초기화 테스트 실패")
                return None
            _pools[key] = pool
            logger.info("[ReplicationMonitor] connection pool 생성: key=%s (min=%d,max=%d)", key, _POOL_MINCONN, _POOL_MAXCONN)
            return pool
        except Exception as e:
            logger.warning("[ReplicationMonitor] ThreadedConnectionPool 생성 실패: %s", e)
            return None


def _get_conn_for_dsn(dsn: str) -> Tuple[Optional[object], Optional[object]]:
    """
    DSN에 대해 pool에서 연결을 얻거나 direct connect를 수행.
    반환: (conn, pool_or_None). pool_or_None이 None이면 direct connect(종료 시 conn.close() 필요).
    """
    if not _HAS_PSYCOPG2:
        return None, None
    pool = _ensure_pool_for_dsn(dsn)
    if pool:
        try:
            conn = pool.getconn()
            # 추가 안정성: 닫힌 연결이면 재시도
            if getattr(conn, "closed", 0):
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = pool.getconn()
            return conn, pool
        except Exception as e:
            logger.debug("[ReplicationMonitor] pool.getconn 실패, direct connect로 폴백: %s", e)
            # fall through to direct connect
    # direct connect fallback
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        return conn, None
    except Exception as e:
        logger.warning("[ReplicationMonitor] direct psycopg2.connect 실패: %s", e)
        return None, None


def _release_conn(conn, pool):
    """풀에 의해 관리되는 연결이면 putconn, 아니면 close(). 안전하게 예외 무시."""
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
        logger.exception("[ReplicationMonitor] _release_conn 예외 처리 중 오류")


# ------------------------------------------------------------------
# ReplicationMonitor 클래스 (풀 기반)
# ------------------------------------------------------------------
class ReplicationMonitor:
    """Primary/Replica 복제 상태를 주기적으로 수집하는 모니터.

    Example::

        monitor = ReplicationMonitor(
            primary_dsn="host=primary dbname=mydb user=postgres",
            replica_dsn="host=replica dbname=mydb user=postgres",
        )
        monitor.start()
        status = monitor.get_status()
        monitor.stop()
    """

    # 기본 폴링 주기 (초)
    DEFAULT_INTERVAL: float = 10.0

    def __init__(
        self,
        primary_dsn: str = "",
        replica_dsn: str = "",
        interval: float = DEFAULT_INTERVAL,
        on_update: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """복제 모니터를 초기화한다."""
        self._primary_dsn = primary_dsn or ""
        self._replica_dsn = replica_dsn or ""
        self._interval = float(interval)
        self._on_update = on_update

        self._status: Dict = {"primary": [], "replica": {}}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """모니터링 스레드를 시작한다."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="pg-replication-monitor"
        )
        self._thread.start()
        logger.info("ReplicationMonitor 시작됨 (주기: %.1fs)", self._interval)

    def stop(self) -> None:
        """모니터링 스레드를 정지한다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        logger.info("ReplicationMonitor 정지됨")

    def get_status(self) -> Dict:
        """마지막으로 수집된 복제 상태를 반환한다."""
        with self._lock:
            return dict(self._status)

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """백그라운드 폴링 루프."""
        while not self._stop_event.is_set():
            self._collect()
            self._stop_event.wait(self._interval)

    def _collect(self) -> None:
        """Primary/Replica 상태를 수집하고 내부 상태를 갱신한다."""
        primary_rows = self._query_primary()
        replica_info = self._query_replica()

        with self._lock:
            self._status = {"primary": primary_rows, "replica": replica_info}

        if self._on_update:
            try:
                self._on_update(self.get_status())
            except Exception:
                logger.exception("[ReplicationMonitor] on_update 콜백 실행 중 예외")

    def _query_primary(self) -> List[Dict]:
        """Primary 노드의 복제 상태를 조회한다."""
        if not _HAS_PSYCOPG2 or not self._primary_dsn:
            return []

        conn = None
        pool = None
        cur = None
        try:
            conn, pool = _get_conn_for_dsn(self._primary_dsn)
            if conn is None:
                return []
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(_QUERY_PRIMARY_STATUS)
            rows = [dict(row) for row in cur.fetchall()]
            return rows
        except Exception as exc:  # noqa: BLE001
            logger.warning("Primary 상태 조회 실패: %s", exc)
            return []
        finally:
            try:
                if cur is not None:
                    try:
                        cur.close()
                    except Exception:
                        pass
            finally:
                _release_conn(conn, pool)

    def _query_replica(self) -> Dict:
        """Replica 노드의 복제 지연을 조회한다."""
        if not _HAS_PSYCOPG2 or not self._replica_dsn:
            return {}

        conn = None
        pool = None
        cur = None
        try:
            conn, pool = _get_conn_for_dsn(self._replica_dsn)
            if conn is None:
                return {}
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(_QUERY_REPLICA_LAG)
            row = cur.fetchone()
            return dict(row) if row else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Replica 상태 조회 실패: %s", exc)
            return {}
        finally:
            try:
                if cur is not None:
                    try:
                        cur.close()
                    except Exception:
                        pass
            finally:
                _release_conn(conn, pool)