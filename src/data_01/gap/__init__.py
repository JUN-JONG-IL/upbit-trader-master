# -*- coding: utf-8 -*-
"""
Timescale ?ŒìŠ¤???¤í‚¤ë§?& ?˜í”Œ ?°ì´???ì„±ê¸?(PoC)

ëª©ì :
- detectorê°€ ê¸°ë??˜ëŠ” market_ticks ?Œì´ë¸”ì´ ?†ì„ ???ŒìŠ¤?¸ìš©?¼ë¡œ ?Œì´ë¸”ì„ ?ì„±?©ë‹ˆ??
- exchange_tsë¥??Œí‹°?”ë‹ ì»¬ëŸ¼?¼ë¡œ ?¬ìš©?˜ëŠ” hypertable ?ì„± ??
  'partitioning column must be part of primary/composite key' ?œì•½??ë§Œì¡±?˜ë„ë¡?
  PRIMARY KEYë¥?(trade_id, exchange_ts)ë¡??•ì˜?©ë‹ˆ??
- ?´ì˜ ?˜ê²½?ì„œ??collectorê°€ ?°ì´?°ë? ?½ì…?˜ë?ë¡????¤í¬ë¦½íŠ¸???ŒìŠ¤??ê°œë°œ ?„ìš©?…ë‹ˆ??

?¬ìš© ??
1) ?Œì´ë¸”ë§Œ ?ì„±:
    python -m src.data_01.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --create-only

2) ?Œì´ë¸??ì„± + ?˜í”Œ ?¬ë³¼ 1ê°??½ì…(ë§ˆì?ë§?tsë¥?now - hours_ago):
    python -m src.data_01.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --seed-symbols "KRW-BTC" --hours-ago 48

ì£¼ì˜:
- ???¤í¬ë¦½íŠ¸??ï¿½ï¿½ï¿½ë°œ?©ì´ë©? ?´ì˜ DB???¤í–‰?˜ê¸° ??DSN??ë°˜ë“œ???•ì¸?˜ì„¸??
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

logger = logging.getLogger("gap.init_schema")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(ch)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


# ?Œì´ë¸??ì„± DDL: PRIMARY KEYë¥?(trade_id, exchange_ts)ë¡??˜ì—¬ hypertable ?œì•½ ì¶©ì¡±
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_ticks (
  trade_id TEXT NOT NULL,
  exchange_ts TIMESTAMPTZ NOT NULL,
  symbol TEXT NOT NULL,
  price NUMERIC,
  qty NUMERIC,
  side TEXT,
  ingest_ts TIMESTAMPTZ DEFAULT now(),
  trace_id TEXT,
  PRIMARY KEY (trade_id, exchange_ts)
);
"""

# hypertable ?ì„± SQL (Timescaleê°€ ?¤ì¹˜?˜ì–´ ?ˆìœ¼ë©??¤í–‰)
CREATE_HYPERTABLE_SQL = "SELECT create_hypertable('market_ticks', 'exchange_ts', if_not_exists => TRUE);"

INSERT_SAMPLE_SQL = """
INSERT INTO market_ticks (trade_id, symbol, exchange_ts, price, qty, side, trace_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (trade_id, exchange_ts) DO NOTHING;
"""


async def _create_pool(dsn: str):
    try:
        import asyncpg  # type: ignore
    except ModuleNotFoundError:
        logger.error("asyncpg ëª¨ë“ˆ???„ìš”?©ë‹ˆ?? ?¤ì¹˜: pip install asyncpg")
        raise
    try:
        pool = await asyncpg.create_pool(dsn)
        logger.info("[init_schema] asyncpg pool ?ì„± ?±ê³µ")
        return pool
    except Exception:
        logger.exception("[init_schema] asyncpg pool ?ì„± ?¤íŒ¨")
        raise


async def create_schema(pool: Any) -> bool:
    """
    market_ticks ?Œì´ë¸??ì„± ë°?hypertable ?ì„± ?œë„.
    ?¤íŒ¨ ???ˆì™¸ë¥??˜ì?ì§€ ?Šê³  False ë°˜í™˜(?¸í™˜??ëª©ì ).
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            # hypertable ?ì„± ?œë„: Timescale???¤ì¹˜?˜ì–´ ?ˆì–´???±ê³µ
            try:
                await conn.execute(CREATE_HYPERTABLE_SQL)
                logger.info("[init_schema] hypertable ?ì„±/?•ì¸ ?„ë£Œ")
            except Exception as e:
                # hypertable ?ì„± ?¤íŒ¨??ì¹˜ëª…?ì´ì§€ ?ŠìŒ(?? extension ë¯¸ì„¤ì¹?
                logger.warning("[init_schema] create_hypertable ?¤íŒ¨(ë¬´ì‹œ): %s", e)
        logger.info("[init_schema] market_ticks ?¤í‚¤ë§??ì„±/?•ì¸ ?„ë£Œ")
        return True
    except Exception:
        logger.exception("[init_schema] ?¤í‚¤ë§??ì„± ?¤íŒ¨")
        return False


async def seed_samples(pool: Any, symbols: List[str], hours_ago: int = 48, price: float = 1000.0, qty: float = 0.001):
    """
    ê°??¬ë³¼???€???¨ì¼ ?˜í”Œ tick???½ì….
    exchange_ts = now - hours_ago
    """
    now = datetime.now(timezone.utc)
    sample_ts = now - timedelta(hours=hours_ago)
    try:
        async with pool.acquire() as conn:
            for sym in symbols:
                trade_id = f"seed-{sym}-{int(sample_ts.timestamp())}"
                side = "bid"
                trace_id = f"seed-{sym}"
                await conn.execute(INSERT_SAMPLE_SQL, trade_id, sym, sample_ts, price, qty, side, trace_id)
                logger.info("[init_schema] ?˜í”Œ ?½ì…: symbol=%s trade_id=%s exchange_ts=%s", sym, trade_id, sample_ts.isoformat())
    except Exception:
        logger.exception("[init_schema] ?˜í”Œ ?½ì… ?¤íŒ¨")
        raise


async def _main_async(args):
    if not args.timescale_dsn:
        logger.error("timescale-dsn???„ìš”?©ë‹ˆ?? --timescale-dsn ?¸ì ?ëŠ” TIMESCALE_DSN ?˜ê²½ë³€?˜ë? ?¬ìš©?˜ì„¸??")
        return

    pool = await _create_pool(args.timescale_dsn)
    try:
        ok = await create_schema(pool)
        if not ok:
            logger.error("?¤í‚¤ë§??ì„± ?¤íŒ¨, ì¢…ë£Œ")
            return

        if args.seed_symbols:
            symbols = [s.strip() for s in args.seed_symbols.split(",") if s.strip()]
            if symbols:
                await seed_samples(pool, symbols, hours_ago=args.hours_ago, price=args.price, qty=args.qty)
            else:
                logger.warning("seed_symbols ê°€ ë¹„ì–´?ˆìŒ - ?˜í”Œ ?½ì… ?ëµ")
        else:
            logger.info("?˜í”Œ ?½ì… ?µì…˜ ë¯¸ì???(--seed-symbols) - ?¤í‚¤ë§??ì„±ë§??˜í–‰")
    finally:
        try:
            await pool.close()
        except Exception:
            logger.debug("pool ì¢…ë£Œ ì¤??ˆì™¸", exc_info=True)


def main():
    p = argparse.ArgumentParser(description="Timescale market_ticks ?¤í‚¤ë§??ì„± ë°??˜í”Œ ?½ì… (ê°œë°œ??")
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""), help="Timescale/Postgres DSN")
    p.add_argument("--create-only", action="store_true", help="?¤í‚¤ë§ˆë§Œ ?ì„± (seed ë¬´ì‹œ)")
    p.add_argument("--seed-symbols", type=str, default="", help="ì½¤ë§ˆë¡?êµ¬ë¶„???¬ë³¼ ë¦¬ìŠ¤??(?? KRW-BTC,KRW-ETH)")
    p.add_argument("--hours-ago", type=int, default=48, help="?½ì…???˜í”Œ??exchange_ts ë¥??„ì¬?ì„œ ëª??œê°„ ?´ì „?¼ë¡œ ? ì?")
    p.add_argument("--price", type=float, default=50000.0, help="?˜í”Œ price")
    p.add_argument("--qty", type=float, default=0.001, help="?˜í”Œ qty")
    args = p.parse_args()

    # create-only?´ë©´ seed ë¬´ì‹œ
    if args.create_only:
        args.seed_symbols = ""

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
