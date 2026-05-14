#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
寃⑸━ 罹붾뱾 ?곗씠???뺣━ ?좏떥由ы떚

isolated_candles ?뚯씠釉붿뿉 ?볦씤 ?댁긽 ?곗씠?곕? ?좎쭨 湲곗??쇰줈 ??젣?⑸땲??

?ㅽ뻾 諛⑸쾿:
    # ??젣 ???嫄댁닔留?異쒕젰 (?ㅼ젣 ??젣 ?놁쓬)
    python -m src.data_01.scripts.cleanup_isolated_candles --dry-run

    # 30???댁쟾 ?곗씠????젣 (湲곕낯媛?
    python -m src.data_01.scripts.cleanup_isolated_candles

    # 7???댁쟾 ?곗씠????젣
    python -m src.data_01.scripts.cleanup_isolated_candles --before-days 7

?섍꼍蹂??
    TIMESCALE_DSN   : PostgreSQL DSN (?? postgresql://user:pass@host:port/db)
    PGHOST          : DB ?몄뒪??(TIMESCALE_DSN 誘몄꽕?????ъ슜)
    PGPORT          : DB ?ы듃
    PGUSER          : DB ?ъ슜??
    PGPASSWORD      : DB 鍮꾨?踰덊샇
    PGDATABASE      : DB ?대쫫
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ?꾨줈?앺듃 猷⑦듃瑜?PYTHONPATH??異붽?
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _build_dsn() -> str:
    """?섍꼍蹂?섏뿉??DSN??援ъ꽦?⑸땲??"""
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
    """??젣 ???寃⑸━ 罹붾뱾 嫄댁닔瑜?諛섑솚?⑸땲??

    Args:
        dsn: PostgreSQL ?곌껐 DSN
        before_days: 湲곗? ?쇱닔 (N???댁쟾 ?곗씠?????

    Returns:
        ??젣 ???????
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg 誘몄꽕移???pip install asyncpg")
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
        logger.error("嫄댁닔 議고쉶 ?ㅽ뙣: %s", exc)
        return 0


async def delete_isolated(dsn: str, before_days: int) -> int:
    """寃⑸━ 罹붾뱾 ?곗씠?곕? ?ㅼ젣濡???젣?⑸땲??

    Args:
        dsn: PostgreSQL ?곌껐 DSN
        before_days: 湲곗? ?쇱닔 (N???댁쟾 ?곗씠????젣)

    Returns:
        ??젣??????
    """
    try:
        import asyncpg  # type: ignore
    except ImportError:
        logger.error("asyncpg 誘몄꽕移???pip install asyncpg")
        return 0

    sql = """
        DELETE FROM isolated_candles
        WHERE created_at < NOW() - ($1 * INTERVAL '1 day')
    """
    try:
        conn = await asyncpg.connect(dsn)
        try:
            result = await conn.execute(sql, before_days)
            # asyncpg execute 諛섑솚媛? "DELETE N" ?뺤떇
            deleted = int(result.split()[-1]) if result else 0
            return deleted
        finally:
            await conn.close()
    except Exception as exc:
        logger.error("??젣 ?ㅽ뙣: %s", exc)
        return 0


async def main(dry_run: bool, before_days: int) -> None:
    """硫붿씤 ?ㅽ뻾 ?⑥닔.

    Args:
        dry_run: True?대㈃ 嫄댁닔留?異쒕젰?섍퀬 ?ㅼ젣 ??젣 ????
        before_days: N???댁쟾 ?곗씠?????
    """
    dsn = _build_dsn()
    # 鍮꾨?踰덊샇瑜??쒖쇅???곌껐 ?뺣낫留?濡쒓퉭 (蹂댁븞)
    try:
        import urllib.parse as _urlparse
        parsed = _urlparse.urlparse(dsn)
        safe_dsn = f"{parsed.hostname}:{parsed.port}{parsed.path}"
    except Exception:
        safe_dsn = "(?곌껐 ?뺣낫 ?뚯떛 ?ㅽ뙣)"
    logger.info("DB ?곌껐: %s", safe_dsn)
    logger.info("湲곗?: %d???댁쟾 ?곗씠??, before_days)

    count = await count_isolated(dsn, before_days)
    logger.info("??젣 ???嫄댁닔: %d嫄?, count)

    if dry_run:
        logger.info("[dry-run] ?ㅼ젣 ??젣瑜??섑뻾?섏? ?딆뒿?덈떎.")
        return

    if count == 0:
        logger.info("??젣???곗씠?곌? ?놁뒿?덈떎.")
        return

    deleted = await delete_isolated(dsn, before_days)
    logger.info("??젣 ?꾨즺: %d嫄?, deleted)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="isolated_candles ?뚯씠釉??곗씠???뺣━ ?좏떥由ы떚"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="??젣 ???嫄댁닔留?異쒕젰?섍퀬 ?ㅼ젣 ??젣???섑뻾?섏? ?딆쓬",
    )
    p.add_argument(
        "--before-days",
        type=int,
        default=30,
        metavar="N",
        help="N???댁쟾 寃⑸━ ?곗씠?곕쭔 ??젣 (湲곕낯媛? 30??",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(dry_run=args.dry_run, before_days=args.before_days))

