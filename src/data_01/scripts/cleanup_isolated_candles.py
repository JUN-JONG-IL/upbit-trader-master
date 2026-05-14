#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ê²©ë¦¬ ìº”ë“¤ ?°ì´???•ë¦¬ ? í‹¸ë¦¬í‹°

isolated_candles ?Œì´ë¸”ì— ?“ì¸ ?´ìƒ ?°ì´?°ë? ? ì§œ ê¸°ì??¼ë¡œ ?? œ?©ë‹ˆ??

?¤í–‰ ë°©ë²•:
    # ?? œ ?€??ê±´ìˆ˜ë§?ì¶œë ¥ (?¤ì œ ?? œ ?†ìŒ)
    python -m src.data_01.scripts.cleanup_isolated_candles --dry-run

    # 30???´ì „ ?°ì´???? œ (ê¸°ë³¸ê°?
    python -m src.data_01.scripts.cleanup_isolated_candles

    # 7???´ì „ ?°ì´???? œ
    python -m src.data_01.scripts.cleanup_isolated_candles --before-days 7

?˜ê²½ë³€??
    TIMESCALE_DSN   : PostgreSQL DSN (?? postgresql://user:pass@host:port/db)
    PGHOST          : DB ?¸ìŠ¤??(TIMESCALE_DSN ë¯¸ì„¤?????¬ìš©)
    PGPORT          : DB ?¬íŠ¸
    PGUSER          : DB ?¬ìš©??
    PGPASSWORD      : DB ë¹„ë?ë²ˆí˜¸
    PGDATABASE      : DB ?´ë¦„
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ?„ë¡œ?íŠ¸ ë£¨íŠ¸ë¥?PYTHONPATH??ì¶”ê?
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _build_dsn() -> str:
    """?˜ê²½ë³€?˜ì—??DSN??êµ¬ì„±?©ë‹ˆ??"""
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
    """?? œ ?€??ê²©ë¦¬ ìº”ë“¤ ê±´ìˆ˜ë¥?ë°˜í™˜?©ë‹ˆ??

    Args:
        dsn: PostgreSQL ?°ê²° DSN
        before_days: ê¸°ì? ?¼ìˆ˜ (N???´ì „ ?°ì´???€??

    Returns:
        ?? œ ?€??????
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg ë¯¸ì„¤ì¹???pip install asyncpg")
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
        logger.error("ê±´ìˆ˜ ì¡°íšŒ ?¤íŒ¨: %s", exc)
        return 0


async def delete_isolated(dsn: str, before_days: int) -> int:
    """ê²©ë¦¬ ìº”ë“¤ ?°ì´?°ë? ?¤ì œë¡??? œ?©ë‹ˆ??

    Args:
        dsn: PostgreSQL ?°ê²° DSN
        before_days: ê¸°ì? ?¼ìˆ˜ (N???´ì „ ?°ì´???? œ)

    Returns:
        ?? œ??????
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg ë¯¸ì„¤ì¹???pip install asyncpg")
        return 0

    sql = """
        DELETE FROM isolated_candles
        WHERE created_at < NOW() - ($1 * INTERVAL '1 day')
    """
    try:
        conn = await asyncpg.connect(dsn)
        try:
            result = await conn.execute(sql, before_days)
            # asyncpg execute ë°˜í™˜ê°? "DELETE N" ?•ì‹
            deleted = int(result.split()[-1]) if result else 0
            return deleted
        finally:
            await conn.close()
    except Exception as exc:
        logger.error("?? œ ?¤íŒ¨: %s", exc)
        return 0


async def main(dry_run: bool, before_days: int) -> None:
    """ë©”ì¸ ?¤í–‰ ?¨ìˆ˜.

    Args:
        dry_run: True?´ë©´ ê±´ìˆ˜ë§?ì¶œë ¥?˜ê³  ?¤ì œ ?? œ ????
        before_days: N???´ì „ ?°ì´???€??
    """
    dsn = _build_dsn()
    # ë¹„ë?ë²ˆí˜¸ë¥??œì™¸???°ê²° ?•ë³´ë§?ë¡œê¹… (ë³´ì•ˆ)
    try:
        import urllib.parse as _urlparse
        parsed = _urlparse.urlparse(dsn)
        safe_dsn = f"{parsed.hostname}:{parsed.port}{parsed.path}"
    except Exception:
        safe_dsn = "(?°ê²° ?•ë³´ ?Œì‹± ?¤íŒ¨)"
    logger.info("DB ?°ê²°: %s", safe_dsn)
    logger.info("ê¸°ì?: %d???´ì „ ?°ì´??, before_days)

    count = await count_isolated(dsn, before_days)
    logger.info("?? œ ?€??ê±´ìˆ˜: %dê±?, count)

    if dry_run:
        logger.info("[dry-run] ?¤ì œ ?? œë¥??˜í–‰?˜ì? ?ŠìŠµ?ˆë‹¤.")
        return

    if count == 0:
        logger.info("?? œ???°ì´?°ê? ?†ìŠµ?ˆë‹¤.")
        return

    deleted = await delete_isolated(dsn, before_days)
    logger.info("?? œ ?„ë£Œ: %dê±?, deleted)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="isolated_candles ?Œì´ë¸??°ì´???•ë¦¬ ? í‹¸ë¦¬í‹°"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="?? œ ?€??ê±´ìˆ˜ë§?ì¶œë ¥?˜ê³  ?¤ì œ ?? œ???˜í–‰?˜ì? ?ŠìŒ",
    )
    p.add_argument(
        "--before-days",
        type=int,
        default=30,
        metavar="N",
        help="N???´ì „ ê²©ë¦¬ ?°ì´?°ë§Œ ?? œ (ê¸°ë³¸ê°? 30??",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(dry_run=args.dry_run, before_days=args.before_days))

