#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ì´ˆê¸° ?°ì´??ë°±í•„ ?¤í¬ë¦½íŠ¸

ê¸°ëŠ¥:
- staging_candles ??candles ?„ì²´ flush (ë¯¸ì²˜ë¦??°ì´???´ê?)
- Gap ê²€ì¶????ë™ ë°±í•„

?¤í–‰ ë°©ë²•:
    python src/data_01/scripts/backfill_initial_data.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# ?„ë¡œ?íŠ¸ ë£¨íŠ¸ë¥?PYTHONPATH??ì¶”ê?
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "data_01"))

logger = logging.getLogger(__name__)


async def flush_all_staging() -> int:
    """
    staging_candles ??candles ?„ì²´ flush

    staging_candles.processed = FALSE ???ˆì½”?œë? ëª¨ë‘ candlesë¡??´ê??©ë‹ˆ??
    Returns:
        ?´ê???ì´??ˆì½”????
    """
    try:
        import importlib.util

        # timescale connector ë¡œë“œ
        ts_path = _ROOT / "src" / "data_01" / "timescale" / "connector.py"
        if not ts_path.exists():
            logger.error("TimescaleDB connectorë¥?ì°¾ì„ ???†ìŠµ?ˆë‹¤: %s", ts_path)
            return 0

        spec = importlib.util.spec_from_file_location("timescale_connector", str(ts_path))
        ts_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts_mod)  # type: ignore

        connector_cls = getattr(ts_mod, "TimescaleConnector", None)
        if connector_cls is None:
            logger.error("TimescaleConnector ?´ë˜?¤ë? ì°¾ì„ ???†ìŠµ?ˆë‹¤.")
            return 0

        connector = connector_cls()
        pool = await connector.create_pool()
        if pool is None:
            logger.error("TimescaleDB ?°ê²° ?€ ?ì„± ?¤íŒ¨")
            return 0

        from pipeline.finalizer import CandlesFinalizer

        finalizer = CandlesFinalizer(pool=pool)
        total = await finalizer.flush_all_staging()
        await pool.close()

        logger.info("??staging_candles ??candles flush ?„ë£Œ: %dê±?, total)
        return total

    except Exception as exc:
        logger.error("flush_all_staging ?¤íŒ¨: %s", exc, exc_info=True)
        return 0


async def main() -> None:
    """ë©”ì¸ ?¤í–‰"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("ì´ˆê¸° ?°ì´??ë°±í•„ ?œì‘")
    logger.info("=" * 60)

    # 1. staging_candles ?„ì²´ flush
    flushed = await flush_all_staging()
    logger.info("1. staging flush ?„ë£Œ: %dê±?, flushed)

    logger.info("=" * 60)
    logger.info("ì´ˆê¸° ?°ì´??ë°±í•„ ?„ë£Œ")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

