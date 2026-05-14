# -*- coding: utf-8 -*-
"""
테이블 스키마 확인 스크립트 (풀 우선 사용, 안전한 리소스 정리)
- 전역 풀(connection_from_pool)이 있으면 우선 사용합니다.
- 없으면 psycopg2.connect()로 연결하되 try/finally로 항상 close() 호출합니다.
- 한글 주석 포함.
"""
from __future__ import annotations

import os
import traceback
import logging
from typing import Optional, ContextManager
import contextlib

logger = logging.getLogger(__name__)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

# 풀 우선 import 시도 (권장)
connection_from_pool = None
try:
    from src.02_data.timescale.pool import connection_from_pool  # type: ignore
    logger.debug("connection_from_pool imported from src.02_data.timescale.pool")
except Exception:
    connection_from_pool = None
    logger.debug("connection_from_pool not available; will fallback to psycopg2.connect")

# 환경변수 기반 DB 설정(폴백값 포함)
DB_CONFIG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "port": int(os.getenv("PGPORT", "58529")),
    "database": os.getenv("PGDATABASE", "upbit_trader"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}


def _direct_connection_ctx() -> ContextManager:
    """psycopg2 직접 연결용 컨텍스트 매니저 (fallback)."""
    try:
        import psycopg2  # type: ignore
    except Exception as e:
        raise RuntimeError("psycopg2 모듈을 불러올 수 없습니다") from e

    @contextlib.contextmanager
    def _cm():
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
            yield conn
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                logger.debug("직접 연결 close 중 예외", exc_info=True)

    return _cm()


def _get_connection_ctx() -> ContextManager:
    """
    커넥션 컨텍스트 반환:
      - connection_from_pool() (있다면) 사용
      - 아니면 direct psycopg2 context 사용
    """
    if connection_from_pool is not None:
        return connection_from_pool()
    return _direct_connection_ctx()


def _print_schema(conn) -> None:
    """주어진 psycopg2 connection으로 스키마를 출력합니다."""
    cur = None
    try:
        cur = conn.cursor()
        print("=" * 60)
        print("📊 staging_candles 스키마")
        print("=" * 60)
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'staging_candles'
            ORDER BY ordinal_position
            """
        )
        for row in cur.fetchall():
            print(f"  {row[0]:<20} {row[1]:<20} nullable={row[2]}")

        print("\n" + "=" * 60)
        print("📊 candles 스키마")
        print("=" * 60)
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'candles'
            ORDER BY ordinal_position
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("❌ candles 테이블이 존재하지 않습니다")
        else:
            for row in rows:
                print(f"  {row[0]:<20} {row[1]:<20} nullable={row[2]}")
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                logger.debug("커서 close 중 예외", exc_info=True)


def check_schema() -> None:
    """외부 진입점: 안전한 컨텍스트로 연결을 얻어 스키마 출력 수행."""
    try:
        with _get_connection_ctx() as conn:
            _print_schema(conn)
    except Exception as exc:
        logger.error("스키마 확인 중 오류 발생: %s", exc)
        traceback.print_exc()


if __name__ == "__main__":
    check_schema()