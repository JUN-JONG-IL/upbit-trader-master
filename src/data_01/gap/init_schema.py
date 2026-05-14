# -*- coding: utf-8 -*-
"""
Timescale ?뚯뒪???ㅽ궎留?& ?섑뵆 ?곗씠???앹꽦湲?(PoC)

紐⑹쟻:
- detector媛 湲곕??섎뒗 market_ticks ?뚯씠釉붿씠 ?놁쓣 ???뚯뒪?몄슜?쇰줈 ?뚯씠釉붿쓣 ?앹꽦?⑸땲??
- exchange_ts瑜??뚰떚?붾떇 而щ읆?쇰줈 ?ъ슜?섎뒗 hypertable ?앹꽦 ??
  'partitioning column must be part of primary/composite key' ?쒖빟??留뚯”?섎룄濡?
  PRIMARY KEY瑜?(trade_id, exchange_ts)濡??뺤쓽?⑸땲??
- ?댁쁺 ?섍꼍?먯꽌??collector媛 ?곗씠?곕? ?쎌엯?섎?濡????ㅽ겕由쏀듃???뚯뒪??媛쒕컻 ?꾩슜?낅땲??

?ъ슜 ??
1) ?뚯씠釉붾쭔 ?앹꽦:
    python -m src.data_01.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --create-only

2) ?뚯씠釉??앹꽦 + ?섑뵆 ?щ낵 1媛??쎌엯(留덉?留?ts瑜?now - hours_ago):
    python -m src.data_01.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --seed-symbols "KRW-BTC" --hours-ago 48

二쇱쓽:
- ???ㅽ겕由쏀듃??占쏙옙占쎈컻?⑹씠硫? ?댁쁺 DB???ㅽ뻾?섍린 ??DSN??諛섎뱶???뺤씤?섏꽭??
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


# ?뚯씠釉??앹꽦 DDL: PRIMARY KEY瑜?(trade_id, exchange_ts)濡??섏뿬 hypertable ?쒖빟 異⑹”
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

# hypertable ?앹꽦 SQL (Timescale媛 ?ㅼ튂?섏뼱 ?덉쑝硫??ㅽ뻾)
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
        logger.error("asyncpg 紐⑤뱢???꾩슂?⑸땲?? ?ㅼ튂: pip install asyncpg")
        raise
    try:
        pool = await asyncpg.create_pool(dsn)
        logger.info("[init_schema] asyncpg pool ?앹꽦 ?깃났")
        return pool
    except Exception:
        logger.exception("[init_schema] asyncpg pool ?앹꽦 ?ㅽ뙣")
        raise


async def create_schema(pool: Any) -> bool:
    """
    market_ticks ?뚯씠釉??앹꽦 諛?hypertable ?앹꽦 ?쒕룄.
    ?ㅽ뙣 ???덉쇅瑜??섏?吏 ?딄퀬 False 諛섑솚(?명솚??紐⑹쟻).
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            # hypertable ?앹꽦 ?쒕룄: Timescale???ㅼ튂?섏뼱 ?덉뼱???깃났
            try:
                await conn.execute(CREATE_HYPERTABLE_SQL)
                logger.info("[init_schema] hypertable ?앹꽦/?뺤씤 ?꾨즺")
            except Exception as e:
                # hypertable ?앹꽦 ?ㅽ뙣??移섎챸?곸씠吏 ?딆쓬(?? extension 誘몄꽕移?
                logger.warning("[init_schema] create_hypertable ?ㅽ뙣(臾댁떆): %s", e)
        logger.info("[init_schema] market_ticks ?ㅽ궎留??앹꽦/?뺤씤 ?꾨즺")
        return True
    except Exception:
        logger.exception("[init_schema] ?ㅽ궎留??앹꽦 ?ㅽ뙣")
        return False


async def seed_samples(pool: Any, symbols: List[str], hours_ago: int = 48, price: float = 1000.0, qty: float = 0.001):
    """
    媛??щ낵??????⑥씪 ?섑뵆 tick???쎌엯.
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
                logger.info("[init_schema] ?섑뵆 ?쎌엯: symbol=%s trade_id=%s exchange_ts=%s", sym, trade_id, sample_ts.isoformat())
    except Exception:
        logger.exception("[init_schema] ?섑뵆 ?쎌엯 ?ㅽ뙣")
        raise


async def _main_async(args):
    if not args.timescale_dsn:
        logger.error("timescale-dsn???꾩슂?⑸땲?? --timescale-dsn ?몄옄 ?먮뒗 TIMESCALE_DSN ?섍꼍蹂?섎? ?ъ슜?섏꽭??")
        return

    pool = await _create_pool(args.timescale_dsn)
    try:
        ok = await create_schema(pool)
        if not ok:
            logger.error("?ㅽ궎留??앹꽦 ?ㅽ뙣, 醫낅즺")
            return

        if args.seed_symbols:
            symbols = [s.strip() for s in args.seed_symbols.split(",") if s.strip()]
            if symbols:
                await seed_samples(pool, symbols, hours_ago=args.hours_ago, price=args.price, qty=args.qty)
            else:
                logger.warning("seed_symbols 媛 鍮꾩뼱?덉쓬 - ?섑뵆 ?쎌엯 ?앸왂")
        else:
            logger.info("?섑뵆 ?쎌엯 ?듭뀡 誘몄???(--seed-symbols) - ?ㅽ궎留??앹꽦留??섑뻾")
    finally:
        try:
            await pool.close()
        except Exception:
            logger.debug("pool 醫낅즺 以??덉쇅", exc_info=True)


def main():
    p = argparse.ArgumentParser(description="Timescale market_ticks ?ㅽ궎留??앹꽦 諛??섑뵆 ?쎌엯 (媛쒕컻??")
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""), help="Timescale/Postgres DSN")
    p.add_argument("--create-only", action="store_true", help="?ㅽ궎留덈쭔 ?앹꽦 (seed 臾댁떆)")
    p.add_argument("--seed-symbols", type=str, default="", help="肄ㅻ쭏濡?援щ텇???щ낵 由ъ뒪??(?? KRW-BTC,KRW-ETH)")
    p.add_argument("--hours-ago", type=int, default=48, help="?쎌엯???섑뵆??exchange_ts 瑜??꾩옱?먯꽌 紐??쒓컙 ?댁쟾?쇰줈 ?좎?")
    p.add_argument("--price", type=float, default=50000.0, help="?섑뵆 price")
    p.add_argument("--qty", type=float, default=0.001, help="?섑뵆 qty")
    args = p.parse_args()

    # create-only?대㈃ seed 臾댁떆
    if args.create_only:
        args.seed_symbols = ""

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
