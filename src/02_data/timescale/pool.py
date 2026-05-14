# -*- coding: utf-8 -*-
"""
전역 연결 풀 관리자 (Timescale/Postgres 용)
- 주요 개선:
  * 초기화 재시도 및 지수 백오프
  * 초기화 실패 쿨다운(TIMESCALE_GLOBAL_FAIL_COOLDOWN_SEC)
  * env 우선 DSN 처리(DATABASE_URL / TIMESCALE_DSN / PGHOST 등)
  * 자동 초기화 옵션(ENABLE_AUTO_INIT_POOL)
  * 덤프 경로 노출(TIMESCALE_POOL_DUMP_PATH) — debug_pool_dump.py 호환성 향상
  * 한글 주석 및 로깅 보강
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
import json
import tempfile
import os
from typing import Any, Dict, Optional
from contextlib import contextmanager

try:
    from psycopg2.pool import SimpleConnectionPool as _SimpleConnectionPool
except Exception:
    _SimpleConnectionPool = None  # type: ignore

logger = logging.getLogger("timescale_pool")

# -----------------------------------------------------------------------
# 모듈 레벨 상수 / 외부에서 참조 가능하게 노출 (debug 도구 호환)
# -----------------------------------------------------------------------
_ACTIVE_DUMP_FN = "timescale_pool_status.json"
TIMESCALE_POOL_DUMP_PATH = os.path.join(tempfile.gettempdir(), _ACTIVE_DUMP_FN)

# 환경변수 기반 기본값 (환경으로 오버라이드 가능)
_DEFAULT_MONITOR_INTERVAL = float(os.getenv("POOL_MONITOR_INTERVAL", "5.0"))
_DEFAULT_MONITOR_THRESHOLD_SECONDS = float(os.getenv("POOL_MONITOR_THRESHOLD_SECONDS", "30.0"))
_DEFAULT_INIT_RETRIES = int(os.getenv("POOL_INIT_RETRIES", "3"))
_DEFAULT_INIT_BACKOFF_BASE_SEC = float(os.getenv("POOL_INIT_BACKOFF_BASE_SEC", "0.1"))
_DEFAULT_FAIL_COOLDOWN_SEC = int(os.getenv("TIMESCALE_GLOBAL_FAIL_COOLDOWN_SEC", "60"))
_ENABLE_AUTO_INIT_ON_GET = os.getenv("ENABLE_AUTO_INIT_POOL", "0").lower() in ("1", "true", "yes")

# -----------------------------------------------------------------------
# sys.modules 기반 프로세스 전역 상태
# -----------------------------------------------------------------------
_STATE_KEY = "__timescale_pool_state__"


def _get_state() -> Dict[str, Any]:
    """프로세스 전체에서 하나의 상태 딕셔너리 반환."""
    state = sys.modules.get(_STATE_KEY)
    if state is None:
        state = {
            "pool": None,
            "dsn": None,
            "lock": threading.Lock(),
            "_active": {},
            "_monitor_thread": None,
            "_monitor_stop": False,
            "_monitor_interval": _DEFAULT_MONITOR_INTERVAL,
            "_monitor_threshold_seconds": _DEFAULT_MONITOR_THRESHOLD_SECONDS,
            "_monitor_enabled": False,
            "minconn": None,
            "maxconn": None,
            "_last_init_fail_at": 0.0,
            "_fail_cooldown_sec": _DEFAULT_FAIL_COOLDOWN_SEC,
            "_init_retries": _DEFAULT_INIT_RETRIES,
            "_init_backoff_base": _DEFAULT_INIT_BACKOFF_BASE_SEC,
        }
        sys.modules[_STATE_KEY] = state
    return state


# -----------------------------------------------------------------------
# 모니터 스레드 관련
# -----------------------------------------------------------------------
def _start_monitor_if_needed(state: Dict[str, Any]) -> None:
    """백그라운드 모니터 스레드를 시작합니다(이미 실행 중이면 재시작하지 않음)."""
    if not state.get("_monitor_enabled"):
        return
    t = state.get("_monitor_thread")
    if t and t.is_alive():
        return

    def _monitor_loop():
        logger.debug("[Pool.MON] monitor started")
        try:
            while not state.get("_monitor_stop"):
                try:
                    _check_and_dump(state)
                except Exception:
                    logger.exception("[Pool.MON] monitor loop error")
                time.sleep(state.get("_monitor_interval", _DEFAULT_MONITOR_INTERVAL))
        finally:
            logger.debug("[Pool.MON] monitor stopped")

    thr = threading.Thread(target=_monitor_loop, name="timescale-pool-monitor", daemon=True)
    state["_monitor_thread"] = thr
    thr.start()


def _detect_dump_path(state: Dict[str, Any]) -> str:
    """
    덤프 파일 경로 우선순위:
    1) 모듈 상수 TIMESCALE_POOL_DUMP_PATH (외부에서 덮어쓰기 가능)
    2) 환경변수 TIMESCALE_POOL_DUMP_PATH 또는 POOL_DUMP_PATH
    3) 시스템 tmpdir/_ACTIVE_DUMP_FN
    """
    # 모듈 상수(외부에서 변경 가능)
    if globals().get("TIMESCALE_POOL_DUMP_PATH"):
        return globals().get("TIMESCALE_POOL_DUMP_PATH")
    env_path = os.getenv("TIMESCALE_POOL_DUMP_PATH") or os.getenv("POOL_DUMP_PATH")
    if env_path:
        return env_path
    return os.path.join(tempfile.gettempdir(), _ACTIVE_DUMP_FN)


def _check_and_dump(state: Dict[str, Any]) -> None:
    """active 맵을 검사하고 이상 시 요약을 덤프합니다."""
    active = state.get("_active", {})
    maxconn = state.get("maxconn") or 0
    now = time.time()
    active_count = len(active)
    long_held = []
    threshold = state.get("_monitor_threshold_seconds", _DEFAULT_MONITOR_THRESHOLD_SECONDS)
    for cid, meta in list(active.items()):
        age = now - meta.get("acquired_at", now)
        if age >= threshold:
            long_held.append({"id": cid, "age": age, "stack": meta.get("stack", "")})

    write_needed = False
    if maxconn and active_count >= max(1, int(maxconn * 0.8)):
        write_needed = True
    if long_held:
        write_needed = True

    logger.debug("[Pool.MON] active_count=%d maxconn=%s long_held=%d", active_count, maxconn, len(long_held))

    if not write_needed:
        return

    snap = {
        "timestamp": now,
        "active_count": active_count,
        "maxconn": maxconn,
        "long_held_count": len(long_held),
        "long_held": long_held[:50],
    }

    try:
        fn = _detect_dump_path(state)
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        logger.warning("[Pool.MON] pool snapshot dumped to %s (active=%d long_held=%d)", fn, active_count, len(long_held))
    except Exception:
        logger.exception("[Pool.MON] failed to write snapshot")


# -----------------------------------------------------------------------
# Helper: env→dsn, 기본값 수집
# -----------------------------------------------------------------------
def _env_dsn_precedence() -> Optional[str]:
    """
    env 우선순위로 DSN 획득:
    1) DATABASE_URL
    2) TIMESCALE_DSN
    3) build from PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE
    """
    url = os.getenv("DATABASE_URL") or os.getenv("TIMESCALE_DSN")
    if url:
        return url.strip() or None

    host = os.getenv("PGHOST") or os.getenv("TIMESCALE_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("PGPORT") or os.getenv("TIMESCALE_PORT") or os.getenv("POSTGRES_PORT")
    user = os.getenv("PGUSER") or os.getenv("TIMESCALE_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("PGPASSWORD") or os.getenv("TIMESCALE_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("PGDATABASE") or os.getenv("TIMESCALE_DB") or os.getenv("POSTGRES_DB")

    if host and port and user and db:
        if password:
            return f"postgresql://{user}:{password}@{host}:{port}/{db}"
        else:
            return f"postgresql://{user}@{host}:{port}/{db}"
    return None


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------
def _can_attempt_init(state: Dict[str, Any]) -> bool:
    """초기화 시도를 해도 되는지 쿨다운 등을 확인."""
    last_fail = state.get("_last_init_fail_at", 0.0) or 0.0
    cooldown = state.get("_fail_cooldown_sec", _DEFAULT_FAIL_COOLDOWN_SEC)
    if last_fail <= 0:
        return True
    if time.time() - last_fail >= cooldown:
        return True
    logger.info("[Pool] init 재시도 대기중 (마지막 실패 %ds 전). 쿨다운 %ds", int(time.time() - last_fail), cooldown)
    return False


def init_global_pool(
    dsn: Optional[str] = None,
    minconn: int = 5,
    maxconn: int = 50,
    retries: Optional[int] = None,
    backoff_base: Optional[float] = None,
    fail_cooldown_sec: Optional[int] = None,
):
    """
    전역 연결 풀 초기화 (1회만 실행됨).
    """
    if _SimpleConnectionPool is None:
        raise RuntimeError("[Pool] psycopg2.pool.SimpleConnectionPool import 실패 - 'pip install psycopg2-binary' 확인 필요")

    state = _get_state()
    with state["lock"]:
        if state.get("pool") is not None:
            logger.debug("[Pool] 전역 연결 풀 이미 존재 - 재사용")
            return state["pool"]

        if not _can_attempt_init(state):
            raise RuntimeError("[Pool] 전역 풀 초기화가 쿨다운 중입니다. 잠시 후 시도하세요.")

        final_dsn = dsn or state.get("dsn") or _env_dsn_precedence()
        if not final_dsn:
            raise RuntimeError("[Pool] DSN이 제공되지 않았습니다. DATABASE_URL 또는 TIMESCALE_DSN 환경변수를 설정하세요.")

        retries = retries if retries is not None else state.get("_init_retries", _DEFAULT_INIT_RETRIES)
        backoff_base = backoff_base if backoff_base is not None else state.get("_init_backoff_base", _DEFAULT_INIT_BACKOFF_BASE_SEC)
        if fail_cooldown_sec is not None:
            state["_fail_cooldown_sec"] = fail_cooldown_sec

        logger.info("[Pool] 전역 연결 풀 생성 시도 (minconn=%d, maxconn=%d, retries=%d)", minconn, maxconn, retries)

        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                pool = _SimpleConnectionPool(minconn, maxconn, final_dsn)
                test_conn = pool.getconn()
                if test_conn is None:
                    raise RuntimeError("[Pool] getconn() 반환 NULL")
                try:
                    with test_conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                finally:
                    pool.putconn(test_conn)

                state["pool"] = pool
                state["dsn"] = final_dsn
                state["minconn"] = minconn
                state["maxconn"] = maxconn
                state["_last_init_fail_at"] = 0.0

                if str(os.getenv("POOL_MONITOR", "")).lower() in ("1", "true", "yes"):
                    state["_monitor_enabled"] = True
                    _start_monitor_if_needed(state)

                logger.info("[Pool] ✅ 전역 연결 풀 초기화 완료 (테스트 성공)")
                return pool

            except Exception as exc:
                last_exc = exc
                logger.warning("[Pool] 전역 풀 초기화 실패 (시도 %d/%d): %s", attempt, retries, exc, exc_info=True)
                if attempt < retries:
                    sleep_for = backoff_base * (2 ** (attempt - 1))
                    logger.info("[Pool] 재시도 대기: %.3fs", sleep_for)
                    time.sleep(sleep_for)

        state["_last_init_fail_at"] = time.time()
        logger.error("[Pool] 연결 풀 초기화 최종 실패. 쿨다운 %ds 시작", state.get("_fail_cooldown_sec"))
        raise RuntimeError(f"[Pool] 연결 풀 초기화 실패(최종): {last_exc}") from last_exc


def init_global_pool_from_env() -> Any:
    minc = int(os.getenv("TIMESCALE_LOCAL_MINCONN", os.getenv("POOL_MINCONN", "1")))
    maxc = int(os.getenv("TIMESCALE_LOCAL_MAXCONN", os.getenv("POOL_MAXCONN", "10")))
    dsn = _env_dsn_precedence()
    retries = int(os.getenv("POOL_INIT_RETRIES", str(_DEFAULT_INIT_RETRIES)))
    backoff = float(os.getenv("POOL_INIT_BACKOFF_BASE_SEC", str(_DEFAULT_INIT_BACKOFF_BASE_SEC)))
    cooldown = int(os.getenv("TIMESCALE_GLOBAL_FAIL_COOLDOWN_SEC", str(_DEFAULT_FAIL_COOLDOWN_SEC)))
    return init_global_pool(dsn=dsn, minconn=minc, maxconn=maxc, retries=retries, backoff_base=backoff, fail_cooldown_sec=cooldown)


# -----------------------------------------------------------------------
# 연결 획득/반환 로직 (안정성 보강)
# -----------------------------------------------------------------------
def get_connection():
    """연결 획득 (3회 재시도, 지수 백오프)."""
    state = _get_state()
    pool = state.get("pool")

    if pool is None and _ENABLE_AUTO_INIT_ON_GET:
        try:
            logger.info("[Pool] 풀 미존재: 자동초기화 시도 (ENABLE_AUTO_INIT_POOL=1)")
            init_global_pool_from_env()
            pool = state.get("pool")
        except Exception as e:
            logger.warning("[Pool] 자동 초기화 실패: %s", e)

    if pool is None:
        raise RuntimeError("[Pool] 전역 연결 풀이 초기화되지 않았습니다. init_global_pool() 호출 필요")

    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            conn = pool.getconn()
            if conn is None:
                logger.warning("[Pool] getconn() NULL (attempt %d/3)", attempt + 1)
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                continue

            if getattr(conn, "closed", False):
                logger.warning("[Pool] 연결 closed (attempt %d/3)", attempt + 1)
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()

                try:
                    stk = "".join(traceback.format_stack(limit=6))
                    with state["lock"]:
                        state["_active"][str(id(conn))] = {"acquired_at": time.time(), "stack": stk, "last_seen": time.time()}
                except Exception:
                    pass

                logger.debug("[Pool] ✅ 연결 획득 성공 (attempt %d/3) id=%s", attempt + 1, id(conn))
                return conn

            except Exception as ping_exc:
                logger.warning("[Pool] ping 실패 (attempt %d/3): %s", attempt + 1, ping_exc)
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                last_exc = ping_exc
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                continue

        except Exception as exc:
            logger.warning("[Pool] 연결 획득 실패 (attempt %d/3): %s", attempt + 1, exc)
            last_exc = exc
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))

    raise RuntimeError(f"[Pool] 연결 획득 최종 실패: {last_exc}") from last_exc


def release_connection(conn, failed: bool = False) -> None:
    """연결 반환. active 맵에서 제거하고 pool.putconn 호출."""
    state = _get_state()
    pool = state.get("pool")

    if pool is None or conn is None:
        return

    try:
        try:
            with state["lock"]:
                meta = state["_active"].pop(str(id(conn)), None)
            if meta:
                duration = time.time() - meta.get("acquired_at", time.time())
                if duration >= 1.0:
                    logger.info("[Pool] connection id=%s held for %.2fs", id(conn), duration)
        except Exception:
            pass

        try:
            pool.putconn(conn, close=failed)
            logger.debug("[Pool] 연결 반환 완료 (failed=%s) id=%s", failed, id(conn))
        except TypeError:
            try:
                pool.putconn(conn)
            except Exception:
                pass
            if failed:
                try:
                    conn.close()
                except Exception:
                    pass
            logger.debug("[Pool] 연결 반환(호환모드) 완료 (failed=%s) id=%s", failed, id(conn))
    except Exception as exc:
        logger.warning("[Pool] 연결 반환 실패: %s", exc)


def close_global_pool() -> None:
    """전역 연결 풀 종료 및 상태 정리."""
    state = _get_state()

    with state["lock"]:
        pool = state.get("pool")
        if pool is None:
            return

        try:
            pool.closeall()
            logger.info("[Pool] 전�� 연결 풀 종료 완료")
        except Exception as exc:
            logger.warning("[Pool] 풀 종료 실패: %s", exc)
        finally:
            state["pool"] = None
            state["dsn"] = None
            try:
                state["_active"].clear()
            except Exception:
                pass
            state["_monitor_stop"] = True


# -----------------------------------------------------------------------
# 안전한 컨텍스트 매니저 유틸리티 (권장 사용)
# -----------------------------------------------------------------------
@contextmanager
def connection_from_pool():
    """Context manager to acquire and always release a pooled connection."""
    conn = None
    try:
        conn = get_connection()
        yield conn
    finally:
        try:
            release_connection(conn, failed=False)
        except Exception:
            logger.debug("[Pool] connection_from_pool: release failed", exc_info=True)


@contextmanager
def cursor_from_pool():
    """Convenience cursor context manager using pooled connection."""
    cur = None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        yield cur
    finally:
        try:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
        finally:
            try:
                release_connection(conn, failed=False)
            except Exception:
                logger.debug("[Pool] cursor_from_pool: release failed", exc_info=True)


# -----------------------------------------------------------------------
# 프로세스 종료 시 자동 정리
# -----------------------------------------------------------------------
import atexit as _atexit


def _cleanup_on_exit() -> None:
    """프로세스 종료 시 전역 연결 풀 정리."""
    state = _get_state()
    pool = state.get("pool")
    if pool is not None:
        try:
            pool.closeall()
            logger.info("[Pool] 프로세스 종료 - 전역 연결 풀 정리 완료")
        except Exception as exc:
            logger.warning("[Pool] 프로세스 종료 시 풀 정리 실패: %s", exc)
        finally:
            state["pool"] = None
            state["dsn"] = None
            try:
                state["_active"].clear()
            except Exception:
                pass
            state["_monitor_stop"] = True


_atexit.register(_cleanup_on_exit)