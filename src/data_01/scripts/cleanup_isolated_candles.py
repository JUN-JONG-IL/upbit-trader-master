#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
격리 캔들 데이터 정리 유틸리티

isolated_candles 테이블에 쌓인 이상 데이터를 날짜 기준으로 삭제합니다.

실행 방법:
    # 삭제 대상 건수만 출력 (실제 삭제 없음)
    python -m src.data_01.scripts.cleanup_isolated_candles --dry-run

    # 30일 이전 데이터 삭제 (기본값)
    python -m src.data_01.scripts.cleanup_isolated_candles

    # 7일 이전 데이터 삭제
    python -m src.data_01.scripts.cleanup_isolated_candles --before-days 7

환경변수:
    TIMESCALE_DSN   : PostgreSQL DSN (예: postgresql://user:pass@host:port/db)
    PGHOST          : DB 호스트 (TIMESCALE_DSN 미설정 시 사용)
    PGPORT          : DB 포트
    PGUSER          : DB 사용자
    PGPASSWORD      : DB 비밀번호
    PGDATABASE      : DB 이름
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _build_dsn() -> str:
    """환경변수에서 DSN을 구성합니다."""
    dsn = os.getenv("TIMESCALE_DSN")
    if dsn:
        return dsn
    host = os.getenv("PGHOST", "127.0.0.1")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "")
    dbname = os.getenv("PGDATABASE", "upbit_trader")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


async def count_isolated(dsn: str, before_days: int) -> int:
    """삭제 대상 격리 캔들 건수를 반환합니다.

    Args:
        dsn: PostgreSQL 연결 DSN
        before_days: 기준 일수 (N일 이전 데이터 대상)

    Returns:
        삭제 대상 행 수
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg 미설치 — pip install asyncpg")
        return 0

    sql = """
        SELECT COUNT(*) AS cnt
        FROM isolated_candles
        WHERE created_at < NOW() - ($1 * INTERVAL '1 day')
    """
    try:
        conn = await asyncpg.connect(dsn)
        try:
            row = await conn.fetchrow(sql, before_days)
            return int(row["cnt"]) if row else 0
        finally:
            await conn.close()
    except Exception as exc:
        logger.error("건수 조회 실패: %s", exc)
        return 0


async def delete_isolated(dsn: str, before_days: int) -> int:
    """격리 캔들 데이터를 실제로 삭제합니다.

    Args:
        dsn: PostgreSQL 연결 DSN
        before_days: 기준 일수 (N일 이전 데이터 삭제)

    Returns:
        삭제된 행 수
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg 미설치 — pip install asyncpg")
        return 0

    sql = """
        DELETE FROM isolated_candles
        WHERE created_at < NOW() - ($1 * INTERVAL '1 day')
    """
    try:
        conn = await asyncpg.connect(dsn)
        try:
            result = await conn.execute(sql, before_days)
            # asyncpg execute 반환값: "DELETE N" 형식
            deleted = int(result.split()[-1]) if result else 0
            return deleted
        finally:
            await conn.close()
    except Exception as exc:
        logger.error("삭제 실패: %s", exc)
        return 0


async def main(dry_run: bool, before_days: int) -> None:
    """메인 실행 함수.

    Args:
        dry_run: True이면 건수만 출력하고 실제 삭제 안 함
        before_days: N일 이전 데이터 대상
    """
    dsn = _build_dsn()
    # 비밀번호를 제외한 연결 정보만 로깅 (보안)
    try:
        import urllib.parse as _urlparse
        parsed = _urlparse.urlparse(dsn)
        safe_dsn = f"{parsed.hostname}:{parsed.port}{parsed.path}"
    except Exception:
        safe_dsn = "(연결 정보 파싱 실패)"
    logger.info("DB 연결: %s", safe_dsn)
    logger.info("기준: %d일 이전 데이터", before_days)

    count = await count_isolated(dsn, before_days)
    logger.info("삭제 대상 건수: %d건", count)

    if dry_run:
        logger.info("[dry-run] 실제 삭제를 수행하지 않습니다.")
        return

    if count == 0:
        logger.info("삭제할 데이터가 없습니다.")
        return

    deleted = await delete_isolated(dsn, before_days)
    logger.info("삭제 완료: %d건", deleted)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="isolated_candles 테이블 데이터 정리 유틸리티"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="삭제 대상 건수만 출력하고 실제 삭제는 수행하지 않음",
    )
    p.add_argument(
        "--before-days",
        type=int,
        default=30,
        metavar="N",
        help="N일 이전 격리 데이터만 삭제 (기본값: 30일)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(dry_run=args.dry_run, before_days=args.before_days))
