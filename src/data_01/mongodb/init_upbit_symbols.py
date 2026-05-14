#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit KRW ?¬ë³¼ MongoDB ì´ˆê¸°???¤í¬ë¦½íŠ¸

MongoDB ??upbit_trader.metadata ì»¬ë ‰?˜ì— Upbit KRW ë§ˆì¼“ ?¬ë³¼ ?•ë³´ë¥??€?¥í•©?ˆë‹¤.
?¬ë³¼???´ë? ì¡´ì¬?˜ë©´ upsert ë¡?ê°±ì‹ ?©ë‹ˆ??

?¤í–‰:
    python src/data_01/mongodb/init_upbit_symbols.py
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def _build_mongo_uri() -> str:
    """?˜ê²½ ë³€?˜ì—??MongoDB URI ë¥?êµ¬ì„±?©ë‹ˆ??"""
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    db_name = os.getenv("MONGO_DB", "upbit_trader")

    user = (
        os.getenv("MONGO_INITDB_ROOT_USERNAME")
        or os.getenv("MONGO_USER")
    )
    password = (
        os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        or os.getenv("MONGO_PASSWORD")
    )

    if user and password:
        return (
            f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{db_name}?authSource=admin"
        )
    return os.getenv("MONGO_URI") or f"mongodb://{host}:{port}/{db_name}"


def _fetch_upbit_tickers() -> List[str]:
    """
    Upbit KRW ë§ˆì¼“ ?„ì²´ ?¬ë³¼ ëª©ë¡??ì¡°íšŒ?©ë‹ˆ??

    pyupbit ë¥??°ì„  ?¬ìš©?˜ê³ , ?†ìœ¼ë©?Upbit REST API ë¥?ì§ì ‘ ?¸ì¶œ?©ë‹ˆ??
    """
    # 1. pyupbit ?¬ìš© ?œë„
    try:
        import pyupbit  # type: ignore
        tickers = pyupbit.get_tickers(fiat="KRW")
        if tickers:
            logger.info("[init_upbit_symbols] pyupbit?ì„œ %dê°??¬ë³¼ ì¡°íšŒ", len(tickers))
            return list(tickers)
    except Exception as e:
        logger.debug("[init_upbit_symbols] pyupbit ì¡°íšŒ ?¤íŒ¨: %s", e)

    # 2. Upbit REST API ì§ì ‘ ?¸ì¶œ (pyupbit ?†ì„ ??
    try:
        import urllib.request
        import json

        url = "https://api.upbit.com/v1/market/all?isDetails=false"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        tickers = [
            item["market"]
            for item in data
            if item.get("market", "").startswith("KRW-")
        ]
        logger.info("[init_upbit_symbols] Upbit API?ì„œ %dê°??¬ë³¼ ì¡°íšŒ", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("[init_upbit_symbols] Upbit API ì¡°íšŒ ?¤íŒ¨: %s", e)

    return []


def _get_korean_name(ticker: str, market_info: Optional[dict] = None) -> str:
    """?¬ë³¼?ì„œ ?œê?ëª??ëŠ” ê¸°ë³¸ ?´ë¦„)??ì¶”ì¶œ?©ë‹ˆ??"""
    if market_info and "korean_name" in market_info:
        return market_info["korean_name"]
    # "KRW-BTC" ??"BTC"
    return ticker.replace("KRW-", "")


def init_upbit_metadata(dry_run: bool = False) -> int:
    """
    Upbit KRW ?¬ë³¼ ë©”í??°ì´?°ë? MongoDB ???€?¥í•©?ˆë‹¤.

    Args:
        dry_run: True ?´ë©´ MongoDB ???°ì? ?Šê³  ë¡œê·¸ë§?ì¶œë ¥?©ë‹ˆ??

    Returns:
        ?€???ëŠ” ?œë??ˆì´?????¬ë³¼ ??
    """
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError:
        logger.error("[init_upbit_symbols] pymongo ë¯¸ì„¤ì¹???ì´ˆê¸°??ë¶ˆê?")
        return 0

    # ?¬ë³¼ ì¡°íšŒ (ìµœë? 3???¬ì‹œ??
    tickers: List[str] = []
    market_map: dict = {}

    # ë¨¼ì? ?ì„¸ ?•ë³´ ?¬í•¨ API ë¡??œê?ëª??¨ê»˜ ì¡°íšŒ ?œë„
    try:
        import urllib.request
        import json

        url = "https://api.upbit.com/v1/market/all?isDetails=true"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        for item in data:
            mkt = item.get("market", "")
            if mkt.startswith("KRW-"):
                tickers.append(mkt)
                market_map[mkt] = {
                    "korean_name": item.get("korean_name", mkt.replace("KRW-", "")),
                    "english_name": item.get("english_name", mkt.replace("KRW-", "")),
                }
    except Exception as e:
        logger.debug("[init_upbit_symbols] ?ì„¸ API ?¸ì¶œ ?¤íŒ¨: %s ??fallback ?œë„", e)
        tickers = _fetch_upbit_tickers()

    if not tickers:
        logger.error("[init_upbit_symbols] ?¬ë³¼ ëª©ë¡ ì¡°íšŒ ?¤íŒ¨ ??MongoDB ì´ˆê¸°??ì¤‘ë‹¨")
        return 0

    if dry_run:
        logger.info("[init_upbit_symbols] dry_run=True ??%dê°??¬ë³¼ (?°ê¸° ?ëµ)", len(tickers))
        return len(tickers)

    uri = _build_mongo_uri()
    db_name = os.getenv("MONGO_DB", "upbit_trader")
    now = datetime.now(tz=timezone.utc)

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        metadata = db["metadata"]

        upserted = 0
        for ticker in tickers:
            info = market_map.get(ticker, {})
            base_currency = ticker.replace("KRW-", "")
            korean_name = info.get("korean_name", base_currency)
            english_name = info.get("english_name", base_currency)

            result = metadata.update_one(
                {"symbol": ticker, "exchange": "upbit"},
                {
                    "$set": {
                        "symbol": ticker,
                        "exchange": "upbit",
                        "korean_name": korean_name,
                        "english_name": english_name,
                        "base_currency": base_currency,
                        "quote_currency": "KRW",
                        "active": True,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        # first_seen_at: DB??ìµœì´ˆë¡?ê¸°ë¡???œê° (Upbit ?¤ì œ ?ì¥???„ë‹˜)
                        "first_seen_at": now,
                    },
                },
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                upserted += 1

        logger.info(
            "[init_upbit_symbols] ??%dê°??¬ë³¼ ì´ˆê¸°???„ë£Œ (ë³€ê²? %dê°?",
            len(tickers),
            upserted,
        )
        client.close()
        return len(tickers)

    except Exception as e:
        logger.error("[init_upbit_symbols] MongoDB ?€???¤íŒ¨: %s", e)
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # src/ ê²½ë¡œ ì¶”ê? (ì§ì ‘ ?¤í–‰ ??
    _here = os.path.dirname(os.path.abspath(__file__))
    _src_02 = os.path.normpath(os.path.join(_here, ".."))  # src/data_01/
    if _src_02 not in sys.path:
        sys.path.insert(0, _src_02)

    count = init_upbit_metadata()
    if count:
        print(f"??{count}ê°??¬ë³¼ ì´ˆê¸°???„ë£Œ")
    else:
        print("???¬ë³¼ ì´ˆê¸°???¤íŒ¨")
        sys.exit(1)

