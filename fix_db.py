# -*- coding: utf-8 -*-
"""
DB 자동 수정 스크립트 (안전한 커넥션 사용)
- 우선 전역 풀(connection_from_pool)을 사용하고, 없으면 psycopg2.connect로 안전하게 연결하여
  작업 수행 후 항상 커서/커넥션을 닫습니다.
- 예외 발생 시 스택트레이스 출력 및 안내 메시지 출력.
"""
from __future__ import annotations

import os
import traceback
import logging
from typing import Optional

logger = logging.getLogger(__name__)
# 콘솔에서 실행할 때 명시적 출력도 남기도록 기본 설정 (스크립트 레벨)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

# 풀이 있을 경우 우선 사용 (권장)
connection_from_pool = None
try:
    # 명확한 경로: src/data_01/timescale/pool.py 의 connection_from_pool 사용
    from src.data_01.timescale.pool import connection_from_pool  # type: ignore
    logger.debug("connection_from_pool imported from src.data_01.timescale.pool")
except Exception:
    connection_from_pool = None
    logger.debug("connection_from_pool not available; fallback to psycopg2.connect")

# DB 접속 기본값(환경변수 우선)
DB_HOST = os.getenv("PGHOST", "127.0.0.1")
DB_PORT = int(os.getenv("PGPORT", "58529"))
DB_NAME = os.getenv("PGDATABASE", "upbit_trader")
DB_USER = os.getenv("PGUSER", "postgres")
DB_PASSWORD = os.getenv("PGPASSWORD", "postgres")


def _run_alter_and_index(cur) -> None:
    """실제 ALTER / INDEX 쿼리를 실행합니다. cur는 열린 커서여야 합니다."""
    # 1. processed 컬럼 추가
    logger.info("1️⃣ processed 컬럼 추가...")
    cur.execute(
        """
        ALTER TABLE staging_candles 
        ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE
        """
    )
    logger.info("   ✅ 완료")

    # 2. 인덱스 생성
    logger.info("2️⃣ 인덱스 생성...")
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_staging_candles_processed 
        ON staging_candles(processed) 
        WHERE NOT processed
        """
    )
    logger.info("   ✅ 완료")

    # 3. 확인
    logger.info("3️⃣ 결과 확인...")
    cur.execute(
        """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'staging_candles' 
          AND column_name = 'processed'
        """
    )
    result = cur.fetchone()
    if result:
        logger.info("   ✅ 성공: %s (%s)", result[0], result[1])
    else:
        logger.warning("   ❌ 실패: processed 컬럼을 찾을 수 없음")


def main() -> None:
    """메인 실행 루틴: pool 우선 사용, 없으면 안전하게 psycopg2로 연결."""
    logger.info("🔧 staging_candles 테이블 수정 중...")

    # 1) Pool 사용 경로 (권장)
    if connection_from_pool is not None:
        logger.info("풀 기반 연결 사용 중 (connection_from_pool)")
        try:
            # connection_from_pool은 contextmanager로 conn을 반환해야 함
            with connection_from_pool() as conn:
                cur = None
                try:
                    cur = conn.cursor()
                    _run_alter_and_index(cur)
                    # 변경 사항 커밋
                    try:
                        conn.commit()
                        logger.info("커밋 완료")
                    except Exception as ce:
                        logger.warning("커밋 실패: %s", ce)
                finally:
                    if cur is not None:
                        try:
                            cur.close()
                        except Exception:
                            pass
            logger.info("🎉 모든 작업 완료! 앱을 재시작하세요: python src/app/main.py")
            return
        except Exception as e:
            logger.exception("풀 기반 실행 중 예외 발생, 폴백 경로로 시도합니다: %s", e)

    # 2) Fallback: psycopg2 직접 연결 (항상 try/finally로 닫음)
    try:
        import psycopg2  # type: ignore
    except Exception as imp_exc:
        logger.error("psycopg2 로드 실패: %s", imp_exc)
        logger.error("DB 접속 불가 - psycopg2 또는 connection pool이 필요합니다.")
        return

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5,
        )
        cur = conn.cursor()
        _run_alter_and_index(cur)
        conn.commit()
        logger.info("🎉 모든 작업 완료! 앱을 재시작하세요: python src/app/main.py")
    except Exception as e:
        logger.exception("❌ 에러 발생: %s", e)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:
            pass
        logger.info("\n💡 해결 방법:")
        logger.info("1. TimescaleDB가 실행 중인지 확인: docker ps")
        logger.info("2. 비밀번호가 맞는지 확인 (기본값: postgres)")
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
