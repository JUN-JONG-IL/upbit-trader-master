# -*- coding: utf-8 -*-
"""
timescale_db — 하위호환 re-export 모듈 및 헬퍼
- 실제 구현은 src/data_01/timescale/core/ 하위 모듈에 위치할 수 있습니다.
- 목적: TimescaleConnector 클래스와 관련 유틸을 안전하게 찾아 재노출하고,
  get_timescale_connector()를 통해 안정적인 싱글톤 인스턴스 반환을 보장합니다.
- 보강:
  - 모듈 레벨 캐시(_connector_instance)로 반복 생성 방지
  - TimescaleConnector 인스턴스 생성시 다양한 시그니처(무인자/DSN 인자 등) 시도
  - 연결 실패시 명확한 디버그/경고 로그
  - fetch_* 헬퍼에서 커서 사용을 try/finally 대신 with 문 사용으로 안정화
  - 전역 풀(pool.py)이 존재하고 ENABLE_AUTO_INIT_POOL 환경변수가 설정되어 있으면
    init_global_pool_from_env()를 안전하게 호출하도록 보강 (전역 풀 자동 초기화 보조).
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
# 모듈 수준 가변: 외부에서 재할당될 수 있는 기본 참조들
# --------------------------------------------------------------------------
TimescaleConnector: Optional[type] = None  # 실제 connector 클래스 (가능하면)
timescale_build_dsn = None  # DSN 생성 helper (가능하면)

# 캐시된 connector 인스턴스(싱글톤 패턴 보조)
_connector_instance: Optional[Any] = None


# --------------------------------------------------------------------------
# 1) 상대 import 시도 (패키지로 로드된 경우)
# --------------------------------------------------------------------------
try:
    from .core.connector_base import TimescaleConnector  # type: ignore
    from .timescale_utils import timescale_build_dsn  # type: ignore
    logger.debug("[timescale_db] 상대 import로 TimescaleConnector/timescale_build_dsn 로드 성공")
except Exception as _e:
    logger.debug("[timescale_db] 핵심 클래스 상대 import 실패(정상 가능): %s", _e)

    # ----------------------------------------------------------------------
    # 2) sys.modules 검색: 이미 로드된 모듈들에서 클래스/함수 검색 (비파���)
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
                    # 기본적인 형태 추정: 클래스며 connect 메서드가 있음
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
    # 3) 파일 경로 기반 동적 로드 시도 (마지막 수단)
    # ----------------------------------------------------------------------
    if TimescaleConnector is None:
        try:
            _here = _pl.Path(__file__).resolve().parent
            _core_dir = _here / "core"

            # 합성 패키지 스텁을 만들어서 상대 import가 동작하도록 도움
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
                """파일 경로로 서브모듈을 로드하고 sys.modules에 등록합니다."""
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

            # connector_base의 의존성(믹스인 등)부터 로드
            _ddl = _load_submodule("core/schema_ddl.py",    f"{_CORE_PKG}.schema_ddl",    _CORE_PKG)
            _cw  = _load_submodule("core/candle_writer.py", f"{_CORE_PKG}.candle_writer", _CORE_PKG)
            _qh  = _load_submodule("core/query_helpers.py", f"{_CORE_PKG}.query_helpers", _CORE_PKG)

            if _ddl is None or _cw is None or _qh is None:
                raise ImportError("믹스인 의존성 로드 실패 (schema_ddl/candle_writer/query_helpers)")

            # connector_base 로드
            _cb = _load_submodule("core/connector_base.py", f"{_CORE_PKG}.connector_base", _CORE_PKG)
            if _cb:
                TimescaleConnector = getattr(_cb, "TimescaleConnector", None)
                if TimescaleConnector is not None:
                    logger.info("[timescale_db] ✅ TimescaleConnector 동적 로드 성공")
        except Exception as _e2:
            logger.warning("[timescale_db] 동적 로드 실패: %s", _e2)

    # timescale_build_dsn 폴백 로드 시도
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

    # 최종 폴백: 간단한 환경변수 기반 DSN 빌더
    if timescale_build_dsn is None:
        def timescale_build_dsn() -> str:  # type: ignore[misc]
            import os
            return os.environ.get("DATABASE_URL", "")


# --------------------------------------------------------------------------
# get_timescale_connector — 싱글톤 인스턴스 반환 (bootstrap.py 등에서 사용)
# --------------------------------------------------------------------------
def _try_instantiate_connector(cls: type, dsn_arg: Optional[str] = None):
    """
    TimescaleConnector 클래스를 다양한 시그니처로 인스턴스화 시도.
    - 인자 없음
    - dsn 문자열 1개 인자
    - 키워드 dsn=db_url
    """
    try:
        # 1) 무인자 생성 시도
        try:
            return cls()
        except TypeError:
            pass

        # 2) 단일 문자열 인자(dsn) 시도
        if dsn_arg:
            try:
                return cls(dsn_arg)
            except TypeError:
                pass

        # 3) 키워드 인자 시도
        try:
            return cls(dsn=dsn_arg)
        except Exception:
            pass

    except Exception as exc:
        logger.debug("[timescale_db] connector 인스턴스화 실패: %s", exc, exc_info=True)
    return None


def _attempt_init_global_pool_if_configured():
    """
    전역 풀(pool.py)이 존재하고 환경변수 ENABLE_AUTO_INIT_POOL이 활성화되어 있으면
    pool.init_global_pool_from_env()를 호출합니다. 실패해도 무시합니다.
    """
    try:
        if str(os.getenv("ENABLE_AUTO_INIT_POOL", "")).lower() not in ("1", "true", "yes"):
            return
        # 상대 import 우선
        try:
            from . import pool as poolmod  # type: ignore
        except Exception:
            # 파일 경로 기반 폴더에서 동적 로드 시도 (비패키지 상황 견고성)
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
                logger.debug("[timescale_db] pool 모듈 동적 로드 실패: %s", e)
                return
        # init 함수가 있으면 호출 (무해한 호출)
        init_fn = getattr(poolmod, "init_global_pool_from_env", None)
        if callable(init_fn):
            try:
                logger.info("[timescale_db] ENABLE_AUTO_INIT_POOL 활성: 전역 풀 초기화 시도")
                init_fn()
                logger.info("[timescale_db] 전역 풀 자동 초기화 시도 완료")
            except Exception as e:
                logger.warning("[timescale_db] 전역 풀 자동 초기화 실패: %s", e)
    except Exception:
        logger.debug("[timescale_db] _attempt_init_global_pool_if_configured 실패", exc_info=True)


def get_timescale_connector() -> Optional[Any]:
    """
    TimescaleConnector 싱글톤 인스턴스를 반환합니다.

    동작:
      - 모듈 수준 캐시(_connector_instance)를 재사용 (있고 연결 유효하면 그대로 반환)
      - 없으면 TimescaleConnector 클래스가 있으면 인스턴스화 시도(여러 시그니처 자동 시도)
      - 인스턴스화 성공 시 connect() 호출하여 실제 연결 보장
      - 실패 시 None 반환
    """
    global _connector_instance, TimescaleConnector, timescale_build_dsn

    # 이미 캐시된 인스턴스가 있다면 connect()로 유효성 재확인
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
            logger.debug("[timescale_db] cached connector health check 실패", exc_info=True)
            # fall through to recreate

    if TimescaleConnector is None:
        logger.warning("[timescale_db] TimescaleConnector 클래스 없음 - connector 생성 불가")
        return None

    # 전역 풀 자동 초기화 시도 (환경변수 ENABLE_AUTO_INIT_POOL=true 인 경우)
    try:
        _attempt_init_global_pool_if_configured()
    except Exception:
        logger.debug("[timescale_db] 전역 풀 자동 초기화 시도 중 예외", exc_info=True)

    # Build DSN if helper present
    dsn = None
    try:
        try:
            dsn = timescale_build_dsn() if callable(timescale_build_dsn) else None
        except Exception:
            dsn = None

    except Exception:
        dsn = None

    # 시그니처 다양한 시도
    conn_obj = _try_instantiate_connector(TimescaleConnector, dsn_arg=dsn)
    if conn_obj is None:
        logger.warning("[timescale_db] TimescaleConnector 인스턴스화 실패 (여러 시그니처 시도)")
        return None

    # 연결 시도: connect()가 True/None/connection-object 등을 반환할 수 있으므로 허용적으로 처리
    try:
        result = conn_obj.connect()
        # 정상적으로 연결되었거나 connect가 None(암묵적 성공)인 경우 허용
        if result is False:
            logger.warning("[timescale_db] get_timescale_connector: connector.connect()가 False를 반환했습니다")
            return None
        # 캐시 후 반환
        _connector_instance = conn_obj
        logger.info("[timescale_db] get_timescale_connector: connector 생성 및 연결 성공")
        return _connector_instance
    except Exception as exc:
        logger.warning("[timescale_db] connector.connect() 호출 중 예외: %s", exc, exc_info=True)
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
# 버전 호환 쿼리 헬퍼 (모듈 수준 함수) — timescale_settings_dialog 등에서 사용
# 모든 함수는 'conn' (psycopg2 connection) 인자를 받아 그 커넥션만 사용합니다.
# --------------------------------------------------------------------------
def fetch_compression_policies(conn) -> Sequence:
    """압축 정책 조회 (TimescaleDB 버전 호환).
    conn: psycopg2 raw connection 객체
    안전: 내부에서 cursor 컨텍스트를 사용해 커서 누수 방지
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
            logger.debug("[timescale_db] compression_policies — %s 성공 (rows=%d)", label, len(rows))
            return rows
        except Exception as exc:
            logger.debug("[timescale_db] compression_policies — %s 실패: %s", label, exc)
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
                logger.info("[timescale_db] compression_policies — %s 사용", label)
            return rows

    logger.warning("[timescale_db] compression_policies — 모든 쿼리 실패; 빈 목록 반환")
    return []


def fetch_continuous_aggs(conn) -> Sequence:
    """Continuous Aggregates 조회 (TimescaleDB 버전 호환).
    conn: psycopg2 raw connection 객체
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
            logger.debug("[timescale_db] continuous_aggs — primary 쿼리 성공 (rows=%d)", len(rows))
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
                logger.info("[timescale_db] continuous_aggs — fallback 쿼리 사용 (rows=%d)", len(rows))
                return rows
        except Exception:
            logger.warning("[timescale_db] continuous_aggs — fallback 쿼리도 실패; 빈 목록 반환")
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