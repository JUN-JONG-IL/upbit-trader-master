#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
珥덇린 ?곗씠??諛깊븘 ?ㅽ겕由쏀듃

湲곕뒫:
- staging_candles ??candles ?꾩껜 flush (誘몄쿂由??곗씠???닿?)
- Gap 寃異????먮룞 諛깊븘

?ㅽ뻾 諛⑸쾿:
    python src/data_01/scripts/backfill_initial_data.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# ?꾨줈?앺듃 猷⑦듃瑜?PYTHONPATH??異붽?
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "data_01"))

logger = logging.getLogger(__name__)


async def flush_all_staging() -> int:
    """
    staging_candles ??candles ?꾩껜 flush

    staging_candles.processed = FALSE ???덉퐫?쒕? 紐⑤몢 candles濡??닿??⑸땲??
    Returns:
        ?닿???珥??덉퐫????
    """
    try:
        import importlib.util

        # timescale connector 濡쒕뱶
        ts_path = _ROOT / "src" / "data_01" / "timescale" / "connector.py"
        if not ts_path.exists():
            logger.error("TimescaleDB connector瑜?李얠쓣 ???놁뒿?덈떎: %s", ts_path)
            return 0

        spec = importlib.util.spec_from_file_location("timescale_connector", str(ts_path))
        ts_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts_mod)  # type: ignore

        connector_cls = getattr(ts_mod, "TimescaleConnector", None)
        if connector_cls is None:
            logger.error("TimescaleConnector ?대옒?ㅻ? 李얠쓣 ???놁뒿?덈떎.")
            return 0

        connector = connector_cls()
        pool = await connector.create_pool()
        if pool is None:
            logger.error("TimescaleDB ?곌껐 ? ?앹꽦 ?ㅽ뙣")
            return 0

        from pipeline.finalizer import CandlesFinalizer

        finalizer = CandlesFinalizer(pool=pool)
        total = await finalizer.flush_all_staging()
        await pool.close()

        logger.info("??staging_candles ??candles flush ?꾨즺: %d嫄?, total)
        return total

    except Exception as exc:
        logger.error("flush_all_staging ?ㅽ뙣: %s", exc, exc_info=True)
        return 0


async def main() -> None:
    """硫붿씤 ?ㅽ뻾"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("珥덇린 ?곗씠??諛깊븘 ?쒖옉")
    logger.info("=" * 60)

    # 1. staging_candles ?꾩껜 flush
    flushed = await flush_all_staging()
    logger.info("1. staging flush ?꾨즺: %d嫄?, flushed)

    logger.info("=" * 60)
    logger.info("珥덇린 ?곗씠??諛깊븘 ?꾨즺")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

