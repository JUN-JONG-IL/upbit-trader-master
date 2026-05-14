#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit KRW ?щ낵 MongoDB 珥덇린???ㅽ겕由쏀듃

MongoDB ??upbit_trader.metadata 而щ젆?섏뿉 Upbit KRW 留덉폆 ?щ낵 ?뺣낫瑜???ν빀?덈떎.
?щ낵???대? 議댁옱?섎㈃ upsert 濡?媛깆떊?⑸땲??

?ㅽ뻾:
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
    """?섍꼍 蹂?섏뿉??MongoDB URI 瑜?援ъ꽦?⑸땲??"""
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
    Upbit KRW 留덉폆 ?꾩껜 ?щ낵 紐⑸줉??議고쉶?⑸땲??

    pyupbit 瑜??곗꽑 ?ъ슜?섍퀬, ?놁쑝硫?Upbit REST API 瑜?吏곸젒 ?몄텧?⑸땲??
    """
    # 1. pyupbit ?ъ슜 ?쒕룄
    try:
        import pyupbit  # type: ignore
        tickers = pyupbit.get_tickers(fiat="KRW")
        if tickers:
            logger.info("[init_upbit_symbols] pyupbit?먯꽌 %d媛??щ낵 議고쉶", len(tickers))
            return list(tickers)
    except Exception as e:
        logger.debug("[init_upbit_symbols] pyupbit 議고쉶 ?ㅽ뙣: %s", e)

    # 2. Upbit REST API 吏곸젒 ?몄텧 (pyupbit ?놁쓣 ??
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
        logger.info("[init_upbit_symbols] Upbit API?먯꽌 %d媛??щ낵 議고쉶", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("[init_upbit_symbols] Upbit API 議고쉶 ?ㅽ뙣: %s", e)

    return []


def _get_korean_name(ticker: str, market_info: Optional[dict] = None) -> str:
    """?щ낵?먯꽌 ?쒓?紐??먮뒗 湲곕낯 ?대쫫)??異붿텧?⑸땲??"""
    if market_info and "korean_name" in market_info:
        return market_info["korean_name"]
    # "KRW-BTC" ??"BTC"
    return ticker.replace("KRW-", "")


def init_upbit_metadata(dry_run: bool = False) -> int:
    """
    Upbit KRW ?щ낵 硫뷀??곗씠?곕? MongoDB ????ν빀?덈떎.

    Args:
        dry_run: True ?대㈃ MongoDB ???곗? ?딄퀬 濡쒓렇留?異쒕젰?⑸땲??

    Returns:
        ????먮뒗 ?쒕??덉씠?????щ낵 ??
    """
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError:
        logger.error("[init_upbit_symbols] pymongo 誘몄꽕移???珥덇린??遺덇?")
        return 0

    # ?щ낵 議고쉶 (理쒕? 3???ъ떆??
    tickers: List[str] = []
    market_map: dict = {}

    # 癒쇱? ?곸꽭 ?뺣낫 ?ы븿 API 濡??쒓?紐??④퍡 議고쉶 ?쒕룄
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
        logger.debug("[init_upbit_symbols] ?곸꽭 API ?몄텧 ?ㅽ뙣: %s ??fallback ?쒕룄", e)
        tickers = _fetch_upbit_tickers()

    if not tickers:
        logger.error("[init_upbit_symbols] ?щ낵 紐⑸줉 議고쉶 ?ㅽ뙣 ??MongoDB 珥덇린??以묐떒")
        return 0

    if dry_run:
        logger.info("[init_upbit_symbols] dry_run=True ??%d媛??щ낵 (?곌린 ?앸왂)", len(tickers))
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
                        # first_seen_at: DB??理쒖큹濡?湲곕줉???쒓컖 (Upbit ?ㅼ젣 ?곸옣???꾨떂)
                        "first_seen_at": now,
                    },
                },
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                upserted += 1

        logger.info(
            "[init_upbit_symbols] ??%d媛??щ낵 珥덇린???꾨즺 (蹂寃? %d媛?",
            len(tickers),
            upserted,
        )
        client.close()
        return len(tickers)

    except Exception as e:
        logger.error("[init_upbit_symbols] MongoDB ????ㅽ뙣: %s", e)
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # src/ 寃쎈줈 異붽? (吏곸젒 ?ㅽ뻾 ??
    _here = os.path.dirname(os.path.abspath(__file__))
    _src_02 = os.path.normpath(os.path.join(_here, ".."))  # src/data_01/
    if _src_02 not in sys.path:
        sys.path.insert(0, _src_02)

    count = init_upbit_metadata()
    if count:
        print(f"??{count}媛??щ낵 珥덇린???꾨즺")
    else:
        print("???щ낵 珥덇린???ㅽ뙣")
        sys.exit(1)

