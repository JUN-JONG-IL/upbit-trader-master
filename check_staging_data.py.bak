# -*- coding: utf-8 -*-
"""
TimescaleDB staging_candles 테이블 데이터 확인 스크립트 (풀 우선 사용)
- 전역 풀(connection_from_pool)을 우선 사용합니다.
- 풀이 없으면 psycopg2.connect()로 안전하게 연결하고 try/finally로 자원 정리합니다.
- 대량 조회 시 커서/연결 누수를 방지하도록 컨텍스트 매니저를 사용합니다.
"""
from __future__ import annotations

import os
import traceback
import logging
from datetime import datetime, timedelta
from typing import ContextManager
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

# DB 연결 설정 (환경변수 우선)
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


# ============================================================
# 1. Staging 테이블 전체 건수 확인
# ============================================================
def check_staging_count() -> int:
    """staging_candles 테이블 총 건수"""
    print("\n" + "=" * 60)
    print("📊 Staging 테이블 전체 건수")
    print("=" * 60)

    with _get_connection_ctx() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM staging_candles")
            count = cur.fetchone()[0]
            print(f"✅ staging_candles 총 건수: {count:,}개")

    return int(count)


# ============================================================
# 2. 최근 N개 캔들 확인
# ============================================================
def check_recent_candles(limit: int = 100) -> None:
    """최근 수집된 캔들 확인"""
    print("\n" + "=" * 60)
    print(f"📊 최근 {limit}개 캔들")
    print("=" * 60)

    with _get_connection_ctx() as conn:
        with conn.cursor() as cur:
            # received_at 등 불필요 컬럼 제외
            cur.execute(
                """
                SELECT 
                    symbol, 
                    time, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume
                FROM staging_candles 
                ORDER BY time DESC 
                LIMIT %s
                """,
                (limit,),
            )

            rows = cur.fetchall()

            if not rows:
                print("❌ 데이터 없음")
                return

            print(f"\n{'심볼':<15} {'시간':<20} {'종가':>12} {'거래량':>15}")
            print("-" * 70)

            for row in rows:
                symbol, tme, open_, high, low, close, volume = row
                print(f"{symbol:<15} {str(tme):<20} {close:>12.2f} {volume:>15.4f}")

            print(f"\n✅ 총 {len(rows)}개 표시")


# ============================================================
# 3. 심볼별 건수 확인
# ============================================================
def check_by_symbol() -> None:
    """심볼별 데이터 건수"""
    print("\n" + "=" * 60)
    print("📊 심볼별 건수 (상위 20개)")
    print("=" * 60)

    with _get_connection_ctx() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    symbol, 
                    COUNT(*) as count,
                    MIN(time) as first_time,
                    MAX(time) as last_time
                FROM staging_candles 
                GROUP BY symbol
                ORDER BY count DESC
                LIMIT 20
                """
            )

            rows = cur.fetchall()

            if not rows:
                print("❌ 데이터 없음")
                return

            print(f"\n{'심볼':<15} {'건수':>8} {'최초시각':<20} {'최근시각':<20}")
            print("-" * 70)

            for symbol, cnt, first_time, last_time in rows:
                print(f"{symbol:<15} {cnt:>8} {str(first_time):<20} {str(last_time):<20}")

            print(f"\n✅ 총 {len(rows)}개 심볼")


# ============================================================
# 4. 시간대별 분포 확인
# ============================================================
def check_time_distribution() -> None:
    """시간대별 데이터 분포 (최근 24시간)"""
    print("\n" + "=" * 60)
    print("📊 시간대별 데이터 분포 (최근 24시간)")
    print("=" * 60)

    with _get_connection_ctx() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    DATE_TRUNC('hour', time) as hour,
                    COUNT(*) as count
                FROM staging_candles 
                WHERE time >= NOW() - INTERVAL '24 hours'
                GROUP BY hour
                ORDER BY hour DESC
                LIMIT 24
                """
            )

            rows = cur.fetchall()

            if not rows:
                print("❌ 최근 24시간 데이터 없음")
                return

            print(f"\n{'시간':<20} {'건수':>8}")
            print("-" * 30)

            for hour, count in rows:
                print(f"{str(hour):<20} {count:>8}")

            print(f"\n✅ 총 {len(rows)}시간")


# ============================================================
# 5. Candles 테이블 확인 (최종 저장소)
# ============================================================
def check_candles_table() -> None:
    """candles 테이블 확인 (Finalizer 처리 후)"""
    print("\n" + "=" * 60)
    print("📊 Candles 테이블 확인 (최종 저장소)")
    print("=" * 60)

    with _get_connection_ctx() as conn:
        with conn.cursor() as cur:
            # 테이블 존재 확인
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'candles'
                )
                """
            )
            exists = cur.fetchone()[0]

            if not exists:
                print("❌ candles 테이블이 존재하지 않습니다")
                return

            # 총 건수
            cur.execute("SELECT COUNT(*) FROM candles")
            count = cur.fetchone()[0]
            print(f"✅ candles 총 건수: {count:,}개")

            if count > 0:
                # 최근 10개
                cur.execute(
                    """
                    SELECT 
                        symbol, 
                        time, 
                        close, 
                        volume
                    FROM candles 
                    ORDER BY time DESC 
                    LIMIT 10
                    """
                )

                rows = cur.fetchall()

                print(f"\n{'심볼':<15} {'시간':<20} {'종가':>12} {'거래량':>15}")
                print("-" * 70)

                for symbol, tme, close, volume in rows:
                    print(f"{symbol:<15} {str(tme):<20} {close:>12.2f} {volume:>15.4f}")


# ============================================================
# 🚀 메인 실행
# ============================================================
def main() -> None:
    """전체 확인 실행"""
    print("\n" + "🔍" * 30)
    print("TimescaleDB 데이터 확인 시작")
    print("🔍" * 30)

    print(f"\n✅ DB 연결 정보:")
    print(f"   host: {DB_CONFIG['host']}")
    print(f"   port: {DB_CONFIG['port']}")
    print(f"   database: {DB_CONFIG['database']}")
    print(f"   user: {DB_CONFIG['user']}")

    try:
        # 1. Staging 총 건수
        count = check_staging_count()

        if count > 0:
            # 2. 최근 캔들
            check_recent_candles(limit=20)

            # 3. 심볼별 건수
            check_by_symbol()

            # 4. 시간대별 분포
            check_time_distribution()

        # 5. Candles 테이블 확인
        check_candles_table()

        print("\n" + "✅" * 30)
        print("데이터 확인 완료!")
        print("✅" * 30 + "\n")

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()