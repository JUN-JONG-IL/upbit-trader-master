# -*- coding: utf-8 -*-
"""
Timescale DB 접근 유틸 (호환성 강화 v3.2)

변경사항 v3.2 (2026-04-26):
- ✅ flush_staging_to_candles() — symbol_full 컬럼 제거 (존재하지 않는 컬럼 참조 에러 수정)
- ✅ 실제 스키마 기준으로 컬럼 목록 업데이트 (quote_volume, is_complete, seq 추가)
- ✅ DISTINCT ON 기준 컬럼 순서 수정: (symbol, timeframe, time) — PRIMARY KEY 순서 일치

추가 변경 (이번 패치):
- fetch_conn_status, _safe_fetch_query: 직접 psycopg2.connect() 대신
  가능하면 TimescaleConnector(또는 전역 풀)를 우선 사용하도록 변경하여
  UI/폴링에서 빈번한 단기 연결 생성을 방지합니다.
"""
from __future__ import annotations

import logging
import sys
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("timescale.db")
if logger.level == 0:
    logger.setLevel(logging.INFO)


def _connect_db(cfg: Dict[str, Any], timeout: int = 3) -> Tuple[Optional[Any], Optional[str]]:
    """
    psycopg2로 동기 연결을 시도.
    반환: (connection, None) 또는 (None, 에러메시지(한글))
    """
    try:
        import psycopg2  # type: ignore
    except Exception:
        logger.error("[timescale_db] psycopg2 미설치 - DB 연결 불가")
        return None, "psycopg2 미설치 (pip install psycopg2-binary 권장)"

    # DSN 우선: cfg의 dsn 또는 환경변수 TIMESCALE_DSN/DATABASE_URL 사용 가능
    dsn = cfg.get("dsn") or os.getenv("TIMESCALE_DSN") or os.getenv("DATABASE_URL")
    if dsn:
        try:
            conn = psycopg2.connect(dsn, connect_timeout=timeout)
            logger.debug("[timescale_db] DB 연결 성공 via DSN")
            return conn, None
        except Exception as e:
            logger.warning("[timescale_db] DSN 연결 실패: %s", e)

    host = cfg.get("host", "localhost")
    port = int(cfg.get("port", 5432))
    dbname = cfg.get("dbname") or cfg.get("db") or cfg.get("database") or ""
    user = cfg.get("user") or ""
    password = cfg.get("password") or ""
    logger.debug("[timescale_db] DB 접속 시도 -> host=%s port=%s dbname=%s user=%s", host, port, dbname, user)

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=timeout,
        )
        logger.debug("[timescale_db] DB 연결 성공: %s:%s/%s", host, port, dbname)
        return conn, None
    except Exception as e:
        msg = str(e)
        lmsg = msg.lower()
        logger.warning("[timescale_db] DB 연결 실패: %s", msg)
        if "authentication failed" in lmsg or "password authentication" in lmsg:
            return None, "인증 실패: DB 사용자/비밀번호를 확인하세요."
        if "role" in lmsg and "does not exist" in lmsg:
            return None, "DB 사용자(role)가 없습니다. 계정 설정을 확인하세요."
        if "connection refused" in lmsg or "could not connect to server" in lmsg:
            return None, "호스트/포트 접속 불가: DB 서버 실행/네트워크를 확인하세요."
        return None, f"DB 접속 실패: {msg}"


def _get_timescale_connector():
    """
    TimescaleConnector를 동적으로 로드합니다.

    탐색 순서:
    1. sys.modules에서 이미 로드된 모듈 찾기
    2. 후보 모듈명을 import해보기
    3. 파일 경로 기반 동적 로드

    Returns:
        get_timescale_connector 함수 또는 None
    """
    # 1. sys.modules에서 찾기 (여러 후보명)
    candidates_in_sys = [
        "src.data_01.timescale.timescale_pool",
        "data_01.timescale.timescale_pool",
        "data_01.timescale.timescale_pool",
        "timescale.timescale_pool",
        "timescale_pool",
        "src.app.timescale.timescale_pool",
    ]
    for mod_name in candidates_in_sys:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            func = getattr(mod, "get_timescale_connector", None)
            if func is not None:
                logger.debug("[timescale_db] ✅ get_timescale_connector found in sys.modules: %s", mod_name)
                return func

    # 2. importlib로 여러 후보 경로 시도
    import importlib
    import importlib.util
    module_candidates = [
        "data_01.timescale.timescale_pool",
        "src.data_01.timescale.timescale_pool",
        "src.app.data_01.timescale.timescale_pool",
        "timescale.timescale_pool",
        "timescale_pool",
    ]
    for candidate in module_candidates:
        try:
            mod = importlib.import_module(candidate)
            func = getattr(mod, "get_timescale_connector", None)
            if func is not None:
                logger.info("[timescale_db] ✅ timescale_pool import 성공: %s", candidate)
                return func
        except Exception:
            continue

    # 3. 파일 경로 기반 동적 로드 (현재 파일 기준)
    try:
        import pathlib
        current_file = pathlib.Path(__file__).resolve()
        pool_path = current_file.parent / "timescale_pool.py"
        if pool_path.exists():
            spec = importlib.util.spec_from_file_location("_timescale_pool_dynamic", str(pool_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_timescale_pool_dynamic"] = mod
                spec.loader.exec_module(mod)
                func = getattr(mod, "get_timescale_connector", None)
                if func is not None:
                    logger.info("[timescale_db] ✅ timescale_pool 동적 로드 성공: %s", pool_path)
                    return func
    except Exception as exc:
        logger.debug("[timescale_db] timescale_pool 동적 로드 실패: %s", exc, exc_info=True)

    logger.warning("[timescale_db] ⚠️ get_timescale_connector를 찾을 수 없음")
    return None


def _safe_fetch_query(cfg: Dict[str, Any], query: str, params: Optional[tuple] = None, fetch_all: bool = True) -> Tuple[Optional[List[tuple]], Optional[str]]:
    """
    안전한 쿼리 실행 헬퍼: (rows, None) 또는 (None, err_msg)
    - 가능하면 TimescaleConnector/풀을 사용하여 연결을 재사용합니다.
    - 실패 시 기존 방식을 폴백(psycopg2.connect).
    - 실패 시 쿼리 앞부분(디버그용)을 로그에 남깁니다.
    """
    # 1) 우선 TimescaleConnector/풀 사용 시도
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is not None:
            try:
                connector = get_connector_func()
                if connector is not None:
                    # connector가 pg_pool 프로퍼티를 제공할 수 있으므로 우선 사용
                    conn_owner = getattr(connector, "pg_pool", connector)
                    raw_conn, from_pool = conn_owner._acquire_conn()
                    cur = None
                    try:
                        cur = raw_conn.cursor()
                        if params:
                            cur.execute(query, params)
                        else:
                            cur.execute(query)
                        rows = cur.fetchall() if fetch_all else cur.fetchone()
                        return (rows if rows is not None else []), None
                    except Exception as e:
                        q_preview = (query or "")[:200].replace("\n", " ")
                        logger.debug("[timescale_db] (pool) 쿼리 실행 실패: %s | 쿼리(앞부분): %s", e, q_preview, exc_info=True)
                        try:
                            if raw_conn:
                                raw_conn.rollback()
                        except Exception:
                            pass
                        return None, f"쿼리 실행 실패: {str(e)}"
                    finally:
                        try:
                            if cur is not None:
                                try:
                                    cur.close()
                                except Exception:
                                    pass
                        finally:
                            try:
                                conn_owner._release_conn(raw_conn, from_pool, failed=False)
                            except Exception:
                                # 만약 예외가 발생했다면 실패 플래그로 반환
                                try:
                                    conn_owner._release_conn(raw_conn, from_pool, failed=True)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("[timescale_db] connector 기반 실행 시도 실패, fallback: %s", e, exc_info=True)
    except Exception:
        # 어떤 이유로든 connector 로딩 자체가 실패해도 아래로 폴백
        pass

    # 2) 폴백: 기존의 직접 연결 방식
    conn, err = _connect_db(cfg)
    if conn is None:
        return None, err
    cur = None
    try:
        cur = conn.cursor()
        try:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
        except Exception as e:
            q_preview = (query or "")[:200].replace("\n", " ")
            logger.debug("[timescale_db] 쿼리 실행 실패: %s | 쿼리(앞부분): %s", e, q_preview, exc_info=True)
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return None, f"쿼리 실행 실패: {str(e)}"
        rows = cur.fetchall() if fetch_all else cur.fetchone()
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return (rows if rows is not None else []), None
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        logger.debug("[timescale_db] 쿼리 전반 예외", exc_info=True)
        return None, str(e)


# -------------------------------------------------------------------------
# 연결 상태 조회 (UI용)
# -------------------------------------------------------------------------
def fetch_conn_status(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    UI에서 주기적으로 호출되는 DB 상태 조회 유틸리티입니다.
    변경: 직접 psycopg2.connect 대신 가능하면 connector/풀을 사용하여
    주기 폴링으로 인한 단기 연결 폭증을 방지합니다.
    """
    out: Dict[str, Any] = {
        "status": "disconnected",
        "host": cfg.get("host", "-"),
        "port": cfg.get("port", "-"),
        "dbname": cfg.get("dbname", "-"),
        "version": "-",
        "ts_version": "-",
        "uptime": "-",
        "conn_count": "-",
        "error": None,
    }

    # 1) 가능한 경우 connector/풀 사용
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is not None:
            try:
                connector = get_connector_func()
                if connector is not None:
                    conn_owner = getattr(connector, "pg_pool", connector)
                    conn = None
                    pool = None
                    cur = None
                    try:
                        # 풀에서 획득하거나 direct self.conn fallback을 반환
                        conn, pool = conn_owner._acquire_conn()
                        if conn is None:
                            raise RuntimeError("connector._acquire_conn가 None을 반환함")
                        cur = conn.cursor()
                        try:
                            cur.execute("SELECT version();")
                            ver = cur.fetchone()
                            out["version"] = ver[0] if ver else "-"
                        except Exception:
                            out["version"] = "-"
                        try:
                            cur.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb';")
                            r = cur.fetchone()
                            out["ts_version"] = r[0] if r else "-"
                        except Exception:
                            out["ts_version"] = "-"
                        try:
                            cur.execute("SELECT date_trunc('second', now() - pg_postmaster_start_time())::text;")
                            r = cur.fetchone()
                            out["uptime"] = r[0] if r else "-"
                        except Exception:
                            out["uptime"] = "-"
                        try:
                            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s;", (cfg.get("dbname"),))
                            r = cur.fetchone()
                            out["conn_count"] = int(r[0]) if r else "-"
                        except Exception:
                            out["conn_count"] = "-"
                        out["status"] = "connected"
                        return out
                    except Exception as exc:
                        logger.debug("[timescale_db] connector 사용 중 상태 조회 실패: %s", exc)
                        out["error"] = str(exc)
                        return out
                    finally:
                        try:
                            if cur is not None:
                                try:
                                    cur.close()
                                except Exception:
                                    pass
                        finally:
                            try:
                                conn_owner._release_conn(conn, pool, failed=False)
                            except Exception:
                                try:
                                    conn_owner._release_conn(conn, pool, failed=True)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("[timescale_db] connector 인스턴스화 실패, fallback: %s", e, exc_info=True)
    except Exception:
        pass

    # 2) 폴백: 기존의 직접 연결 방식
    try:
        import psycopg2  # type: ignore
    except Exception as e:
        out["error"] = f"psycopg2 미설치: {e}"
        return out

    conn = None
    try:
        # DSN 우선
        dsn = cfg.get("dsn") or os.getenv("TIMESCALE_DSN") or os.getenv("DATABASE_URL")
        if dsn:
            conn = psycopg2.connect(dsn, connect_timeout=3)
        else:
            conn = psycopg2.connect(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 5432)),
                dbname=cfg.get("dbname", ""),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                connect_timeout=3,
            )
    except Exception as e:
        out["error"] = f"DB 연결 실패: {e}"
        return out

    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT version();")
            ver = cur.fetchone()
            out["version"] = ver[0] if ver else "-"
        except Exception:
            out["version"] = "-"
        try:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb';")
            r = cur.fetchone()
            out["ts_version"] = r[0] if r else "-"
        except Exception:
            out["ts_version"] = "-"
        try:
            cur.execute("SELECT date_trunc('second', now() - pg_postmaster_start_time())::text;")
            r = cur.fetchone()
            out["uptime"] = r[0] if r else "-"
        except Exception:
            out["uptime"] = "-"
        try:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s;", (cfg.get("dbname"),))
            r = cur.fetchone()
            out["conn_count"] = int(r[0]) if r else "-"
        except Exception:
            out["conn_count"] = "-"
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        out["status"] = "connected"
        return out
    except Exception as e:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        out["error"] = str(e)
        return out


# -------------------------------------------------------------------------
# 진단 유틸리티
# -------------------------------------------------------------------------
def diagnose_data(cfg: Dict[str, Any], sample_limit: int = 5) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "market_ticks_exists": False,
        "candle_gaps_exists": False,
        "market_ticks_count": None,
        "distinct_symbols": None,
        "latest_samples": [],
        "error": None,
    }
    try:
        q_exist = "SELECT to_regclass('public.market_ticks') IS NOT NULL AS mt, to_regclass('public.candle_gaps') IS NOT NULL AS cg;"
        rows, err = _safe_fetch_query(cfg, q_exist, fetch_all=True)
        if rows is None:
            out["error"] = f"진단 실패: {err}"
            return out
        mt_exists, cg_exists = rows[0]
        out["market_ticks_exists"] = bool(mt_exists)
        out["candle_gaps_exists"] = bool(cg_exists)
        if not out["market_ticks_exists"]:
            return out

        q_cnt = "SELECT count(*) FROM market_ticks;"
        rows, err = _safe_fetch_query(cfg, q_cnt)
        out["market_ticks_count"] = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0

        q_sym = "SELECT count(DISTINCT symbol) FROM market_ticks;"
        rows, err = _safe_fetch_query(cfg, q_sym)
        out["distinct_symbols"] = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0

        q_sample = f"""
            SELECT symbol, max(exchange_ts) AS last_ts, count(*) AS cnt
            FROM market_ticks
            GROUP BY symbol
            ORDER BY max(exchange_ts) DESC
            LIMIT {int(sample_limit)};
        """
        rows, err = _safe_fetch_query(cfg, q_sample)
        sam = []
        if rows:
            for sym, last_ts, cnt in rows:
                try:
                    if last_ts is not None and getattr(last_ts, "tzinfo", None) is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    sam.append({"symbol": sym, "last_ts": last_ts.isoformat() if last_ts is not None else None, "count": int(cnt)})
                except Exception:
                    sam.append({"symbol": sym, "last_ts": str(last_ts), "count": int(cnt) if cnt is not None else None})
        out["latest_samples"] = sam
    except Exception as e:
        logger.debug("[timescale_db] diagnose_data 예외", exc_info=True)
        out["error"] = str(e)
    return out


# =========================================================================
# TimescaleConnector 동적 로드 (import 경로 자동 탐색)
# =========================================================================
# (이미 위에 정의된 _get_timescale_connector 사용)
# -------------------------------------------------------------------------


# -------------------------------------------------------------------------
# Staging → Candles 이동 함수 (unchanged)
# -------------------------------------------------------------------------
def flush_staging_to_candles(batch_size: int = 1000) -> int:
    try:
        get_connector_func = _get_timescale_connector()
        if get_connector_func is None:
            logger.error("[Finalizer] ❌ get_timescale_connector 함수를 찾을 수 없음")
            return 0

        connector = get_connector_func()
        if connector is None:
            logger.error("[Finalizer] ❌ TimescaleDB 커넥터 없음")
            return 0

        conn_obj = getattr(connector, "pg_pool", connector)
        raw_conn, from_pool = conn_obj._acquire_conn()

        try:
            with raw_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.staging_candles")
                count = cur.fetchone()[0]
                logger.info("[Finalizer] staging_candles 현재 행 수: %d", count)
                if count == 0:
                    conn_obj._release_conn(raw_conn, from_pool, failed=False)
                    return 0

                move_sql = """
                    WITH uniqued AS (
                        SELECT DISTINCT ON (symbol, timeframe, time)
                            id, symbol, timeframe, exchange, time,
                            open, high, low, close, volume, quote_volume,
                            trade_count, is_complete, seq
                        FROM public.staging_candles
                        ORDER BY symbol, timeframe, time, inserted_at DESC
                        LIMIT %s
                    ),
                    ins AS (
                        INSERT INTO public.candles
                            (symbol, timeframe, exchange, time,
                             open, high, low, close, volume, quote_volume,
                             trade_count, is_complete, seq)
                        SELECT symbol, timeframe, exchange, time,
                               open, high, low, close, volume, quote_volume,
                               trade_count, is_complete, seq
                        FROM uniqued
                        ON CONFLICT (symbol, timeframe, time) DO UPDATE SET
                            exchange     = COALESCE(EXCLUDED.exchange,     candles.exchange),
                            open         = COALESCE(EXCLUDED.open,         candles.open),
                            high         = GREATEST(COALESCE(candles.high, EXCLUDED.high),
                                                    COALESCE(EXCLUDED.high, candles.high)),
                            low          = LEAST(COALESCE(candles.low, EXCLUDED.low),
                                                 COALESCE(EXCLUDED.low, candles.low)),
                            close        = EXCLUDED.close,
                            volume       = COALESCE(candles.volume, 0) + COALESCE(EXCLUDED.volume, 0),
                            quote_volume = COALESCE(EXCLUDED.quote_volume, candles.quote_volume),
                            trade_count  = COALESCE(EXCLUDED.trade_count,  candles.trade_count),
                            is_complete  = EXCLUDED.is_complete,
                            seq          = COALESCE(EXCLUDED.seq, candles.seq)
                        RETURNING 1
                    )
                    DELETE FROM public.staging_candles
                    WHERE id IN (SELECT id FROM uniqued)
                    RETURNING 1;
                """
                cur.execute(move_sql, (batch_size,))
                moved = cur.rowcount if cur.rowcount is not None else 0

            raw_conn.commit()
            logger.info("[Finalizer] ✅ %d개 이동 완료", moved)
            conn_obj._release_conn(raw_conn, from_pool, failed=False)
            return moved

        except Exception as e:
            try:
                raw_conn.rollback()
            except Exception:
                pass
            conn_obj._release_conn(raw_conn, from_pool, failed=True)
            logger.error("[Finalizer] ❌ flush_staging_to_candles 실패: %s", e, exc_info=True)
            return 0

    except Exception as e:
        logger.error("[Finalizer] ❌ flush_staging_to_candles 전체 실패: %s", e, exc_info=True)
        return 0


# (아래의 fetch_* 함수들은 기존 구현을 그대로 유지 — 생략하지 않고 이전과 동일하게 사용 가능)
# fetch_hypertables, fetch_compression_policies, fetch_continuous_aggs,
# fetch_backfills, fetch_gaps 등 기존 정의를 그대로 사용하면 됩니다.