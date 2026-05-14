#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit KRW 심볼 MongoDB 초기화 스크립트

MongoDB 의 upbit_trader.metadata 컬렉션에 Upbit KRW 마켓 심볼 정보를 저장합니다.
심볼이 이미 존재하면 upsert 로 갱신합니다.

실행:
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
    """환경 변수에서 MongoDB URI 를 구성합니다."""
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
    Upbit KRW 마켓 전체 심볼 목록을 조회합니다.

    pyupbit 를 우선 사용하고, 없으면 Upbit REST API 를 직접 호출합니다.
    """
    # 1. pyupbit 사용 시도
    try:
        import pyupbit  # type: ignore
        tickers = pyupbit.get_tickers(fiat="KRW")
        if tickers:
            logger.info("[init_upbit_symbols] pyupbit에서 %d개 심볼 조회", len(tickers))
            return list(tickers)
    except Exception as e:
        logger.debug("[init_upbit_symbols] pyupbit 조회 실패: %s", e)

    # 2. Upbit REST API 직접 호출 (pyupbit 없을 때)
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
        logger.info("[init_upbit_symbols] Upbit API에서 %d개 심볼 조회", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("[init_upbit_symbols] Upbit API 조회 실패: %s", e)

    return []


def _get_korean_name(ticker: str, market_info: Optional[dict] = None) -> str:
    """심볼에서 한글명(또는 기본 이름)을 추출합니다."""
    if market_info and "korean_name" in market_info:
        return market_info["korean_name"]
    # "KRW-BTC" → "BTC"
    return ticker.replace("KRW-", "")


def init_upbit_metadata(dry_run: bool = False) -> int:
    """
    Upbit KRW 심볼 메타데이터를 MongoDB 에 저장합니다.

    Args:
        dry_run: True 이면 MongoDB 에 쓰지 않고 로그만 출력합니다.

    Returns:
        저장(또는 시뮬레이션)된 심볼 수
    """
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError:
        logger.error("[init_upbit_symbols] pymongo 미설치 — 초기화 불가")
        return 0

    # 심볼 조회 (최대 3회 재시도)
    tickers: List[str] = []
    market_map: dict = {}

    # 먼저 상세 정보 포함 API 로 한글명 함께 조회 시도
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
        logger.debug("[init_upbit_symbols] 상세 API 호출 실패: %s — fallback 시도", e)
        tickers = _fetch_upbit_tickers()

    if not tickers:
        logger.error("[init_upbit_symbols] 심볼 목록 조회 실패 — MongoDB 초기화 중단")
        return 0

    if dry_run:
        logger.info("[init_upbit_symbols] dry_run=True — %d개 심볼 (쓰기 생략)", len(tickers))
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
                        # first_seen_at: DB에 최초로 기록된 시각 (Upbit 실제 상장일 아님)
                        "first_seen_at": now,
                    },
                },
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                upserted += 1

        logger.info(
            "[init_upbit_symbols] ✅ %d개 심볼 초기화 완료 (변경: %d개)",
            len(tickers),
            upserted,
        )
        client.close()
        return len(tickers)

    except Exception as e:
        logger.error("[init_upbit_symbols] MongoDB 저장 실패: %s", e)
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # src/ 경로 추가 (직접 실행 시)
    _here = os.path.dirname(os.path.abspath(__file__))
    _src_02 = os.path.normpath(os.path.join(_here, ".."))  # src/data_01/
    if _src_02 not in sys.path:
        sys.path.insert(0, _src_02)

    count = init_upbit_metadata()
    if count:
        print(f"✅ {count}개 심볼 초기화 완료")
    else:
        print("❌ 심볼 초기화 실패")
        sys.exit(1)
