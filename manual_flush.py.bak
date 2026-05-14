# -*- coding: utf-8 -*-
"""
수동으로 staging → candles 이동 스크립트 (안전한 커넥션 사용)
- 우선 전역 풀(connection_from_pool)을 사용하고, 없으면 psycopg2.connect로 안전하게 연결합니다.
- 항상 커서/커넥션을 닫고 예외 시 rollback 처리합니다.
"""
from __future__ import annotations

import os
import logging
import traceback
from typing import Optional

logger = logging.getLogger(__name__)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

# 풀 우선 import (권장)
connection_from_pool = None
try:
    from src.02_data.timescale.pool import connection_from_pool  # type: ignore
    logger.debug("connection_from_pool imported from src.02_data.timescale.pool")
except Exception:
    connection_from_pool = None
    logger.debug("connection_from_pool not available; fallback to psycopg2.connect")

# 환경변수 기반 DB 설정(폴백값 포함)
DB_CONFIG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "port": int(os.getenv("PGPORT", "58529")),
    "database": os.getenv("PGDATABASE", "upbit_trader"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

# 이동 쿼리들
_MOVE_SQL = """
    INSERT INTO candles (
        id, exchange, symbol, timeframe, 
        time, open, high, low, close,
        volume, quote_volume, trade_count,
        is_complete, seq
    )
    SELECT 
        id, exchange, symbol, timeframe,
        time, open, high, low, close,
        volume, quote_volume, trade_count,
        is_complete, seq
    FROM staging_candles
    ORDER BY time ASC
    LIMIT 1000
    ON CONFLICT (symbol, timeframe, time) 
    DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        quote_volume = EXCLUDED.quote_volume,
        trade_count = EXCLUDED.trade_count,
        is_complete = EXCLUDED.is_complete
"""

_DELETE_SQL = """
    DELETE FROM staging_candles
    WHERE id IN (
        SELECT id FROM staging_candles
        ORDER BY time ASC
        LIMIT %s
    )
"""


def _do_flush_with_conn(conn) -> None:
    """주어진 psycopg2 connection으로 flush 작업을 수행합니다. 커서 관리는 내부에서 처리."""
    cur = None
    try:
        cur = conn.cursor()
        # 1) Staging 건수 확인
        cur.execute("SELECT COUNT(*) FROM staging_candles")
        staging_count = cur.fetchone()[0]
        logger.info("✅ Staging: %d개", staging_count)

        if staging_count == 0:
            logger.info("❌ 이동할 데이터 없음")
            return

        # 2) Candles로 이동
        cur.execute(_MOVE_SQL)
        moved = cur.rowcount if cur.rowcount is not None else 0
        logger.info("✅ Candles 이동: %d개", moved)

        # 3) 이동된 데이터 삭제
        if moved > 0:
            cur.execute(_DELETE_SQL, (moved,))
            deleted = cur.rowcount if cur.rowcount is not None else 0
            logger.info("✅ Staging 삭제: %d개", deleted)

        # 4) 커밋
        try:
            conn.commit()
            logger.info("커밋 완료")
        except Exception as ce:
            logger.warning("커밋 실패: %s", ce)

        # 5) 최종 확인 (선택적 로그)
        try:
            cur.execute("SELECT COUNT(*) FROM staging_candles")
            staging_after = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM candles")
            candles_after = cur.fetchone()[0]
            logger.info("완료: Staging=%d, Candles=%d", staging_after, candles_after)
        except Exception:
            logger.debug("완료 확인 중 예외", exc_info=True)

    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                logger.debug("커서 close 중 예외", exc_info=True)


def manual_flush() -> None:
    """플러시 진입점: pool 우선, fallback으로 psycopg2 직접 연결 사용."""
    logger.info("🔄 수동 flush 시작...")

    # 1) pool 사용 경로 (권장)
    if connection_from_pool is not None:
        try:
            with connection_from_pool() as conn:
                _do_flush_with_conn(conn)
            return
        except Exception as e:
            logger.exception("풀 기반 flush 중 예외, fallback 경로로 시도합니다: %s", e)

    # 2) fallback: psycopg2 직접 연결 (항상 try/finally로 닫음)
    try:
        import psycopg2  # type: ignore
    except Exception as imp_exc:
        logger.error("psycopg2 로드 실패: %s", imp_exc)
        return

    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            connect_timeout=5,
        )
        _do_flush_with_conn(conn)
    except Exception as e:
        logger.exception("❌ 에러 발생: %s", e)
        try:
            if conn is not None:
                conn.rollback()
                logger.debug("롤백 수행")
        except Exception:
            logger.debug("롤백 중 예외", exc_info=True)
        traceback.print_exc()
    finally:
        try:
            if conn is not None:
                conn.close()
                logger.debug("직접 연결 close 완료")
        except Exception:
            logger.debug("연결 close 중 예외", exc_info=True)


if __name__ == "__main__":
    manual_flush()