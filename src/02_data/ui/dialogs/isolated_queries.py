# -*- coding: utf-8 -*-
"""
격리 데이터 DB 조회 함수 (isolated_queries.py)

isolated_candles 테이블에 대한 모든 DB 조회/삭제 쿼리를 담당합니다.
단일 책임 원칙(SRP): 데이터 액세스 로직만 담당합니다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 기본 조회 레코드 제한
DEFAULT_QUERY_LIMIT: int = 10_000

# 기간 필터 매핑 (콤보박스 텍스트 → 시간 수)
PERIOD_FILTER_MAP: Dict[str, int] = {
    "최근 1시간": 1,
    "최근 24시간": 24,
    "최근 7일": 168,
}


def get_db_conn():
    """TimescaleDB/PostgreSQL 연결 반환 (없으면 None)."""
    try:
        import psycopg2  # type: ignore
        host = os.getenv("TIMESCALE_HOST", os.getenv("POSTGRES_HOST", "localhost"))
        port = int(os.getenv("TIMESCALE_PORT", os.getenv("POSTGRES_PORT", "5432")))
        dbname = os.getenv("TIMESCALE_DB", os.getenv("POSTGRES_DB", "upbit_trader"))
        user = os.getenv("TIMESCALE_USER", os.getenv("POSTGRES_USER", "postgres"))
        password = os.getenv("TIMESCALE_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
        return psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
            connect_timeout=3,
        )
    except Exception as exc:
        logger.debug("[IsolatedQueries] DB 연결 실패: %s", exc)
        return None


def query_reason_stats() -> Tuple[Dict[str, int], Optional[str]]:
    """isolated_candles 테이블에서 격리 사유별 건수 집계.

    Returns:
        ({"OHLCV_INVALID": N, "PRICE_SPIKE": M, "NULL/미분류": K, ...}, error_msg_or_None)
    """
    conn = get_db_conn()
    if conn is None:
        return {}, "DB 연결 실패"
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(isolation_reason, 'NULL/미분류') AS reason,
                       COUNT(*) AS cnt
                FROM isolated_candles
                GROUP BY isolation_reason
                ORDER BY cnt DESC
                """
            )
            return {row[0]: int(row[1]) for row in cur.fetchall()}, None
    except Exception as exc:
        logger.warning("[IsolatedQueries] 통계 쿼리 실패: %s", exc)
        return {}, str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def query_isolated_rows(
    symbol_filter: Optional[str],
    reason_filter: Optional[str],
    period_hours: Optional[int],
    limit: int = DEFAULT_QUERY_LIMIT,
) -> Tuple[List[tuple], Optional[str]]:
    """isolated_candles 테이블에서 상세 레코드 조회.

    실제 컬럼명 사용: time (not timestamp), COALESCE(isolated_at, received_at)

    Returns:
        ([(symbol, time, isolation_reason, open, high, low, close, volume, isolated_at, raw_data), ...],
         error_msg_or_None)
    """
    conn = get_db_conn()
    if conn is None:
        return [], "DB 연결 실패"
    try:
        conditions: list = []
        params: list = []

        if symbol_filter:
            conditions.append("symbol ILIKE %s")
            params.append(f"%{symbol_filter}%")
        if reason_filter:
            conditions.append("isolation_reason = %s")
            params.append(reason_filter)
        if period_hours:
            since = datetime.now(timezone.utc) - timedelta(hours=period_hours)
            conditions.append("COALESCE(isolated_at, received_at) >= %s")
            params.append(since)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        query = f"""
            SELECT
                symbol,
                time,
                isolation_reason,
                open,
                high,
                low,
                close,
                volume,
                COALESCE(isolated_at, received_at) AS isolated_at,
                raw_data
            FROM isolated_candles
            {where_clause}
            ORDER BY COALESCE(isolated_at, received_at) DESC
            LIMIT %s
        """
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [tuple(row) for row in cur.fetchall()], None
    except Exception as exc:
        logger.warning("[IsolatedQueries] 상세 쿼리 실패: %s", exc)
        return [], str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_all_from_db(
    symbol_filter: Optional[str],
    reason_filter: Optional[str],
    period_hours: Optional[int],
) -> Tuple[int, Optional[str]]:
    """isolated_candles 테이블에서 필터 조건에 해당하는 모든 레코드 삭제.

    Returns:
        (삭제된 건수, 오류 메시지 또는 None)
    """
    conn = get_db_conn()
    if conn is None:
        return 0, "DB 연결 실패"
    try:
        conditions: list = []
        params: list = []

        if symbol_filter:
            conditions.append("symbol ILIKE %s")
            params.append(f"%{symbol_filter}%")
        if reason_filter:
            conditions.append("isolation_reason = %s")
            params.append(reason_filter)
        if period_hours:
            since = datetime.now(timezone.utc) - timedelta(hours=period_hours)
            conditions.append("COALESCE(isolated_at, received_at) >= %s")
            params.append(since)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"DELETE FROM isolated_candles {where_clause}"

        with conn.cursor() as cur:
            cur.execute(query, params)
            deleted = cur.rowcount
        conn.commit()
        return deleted, None
    except Exception as exc:
        logger.error("[IsolatedQueries] 전체 삭제 실패: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0, str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
