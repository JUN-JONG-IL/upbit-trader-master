# -*- coding: utf-8 -*-
"""
검증(validator)에서 실패한 캔들/레코드를 보존하는 유틸리티.
우선순위:
 - MongoDB에 연결해 'invalid_candles' 컬렉션에 저장(권장)
 - MongoDB가 없으면 logs/invalid_candles.jsonl 파일에 JSONL 형태로 append
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict

def _get_mongo_client():
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        return None
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        # quick ping
        client.admin.command("ping")
        return client
    except Exception:
        return None

def store_invalid_candle(candle: Dict[str, Any], reason: str) -> None:
    """
    candle: dict 형태(원본 입력)
    reason: 검증 실패 사유 문자열
    동작: MongoDB에 넣고 실패하면 로컬 파일로 append
    """
    doc = {
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "candle": candle,
    }
    client = _get_mongo_client()
    if client:
        try:
            db_name = os.getenv("MONGO_DBNAME", "upbit_trader")
            db = client[db_name]
            coll = db.get_collection("invalid_candles")
            coll.insert_one(doc)
            return
        except Exception:
            # fall through to file
            pass
    # fallback to local file
    try:
        logdir = os.path.join(os.getcwd(), "logs")
        os.makedirs(logdir, exist_ok=True)
        path = os.path.join(logdir, "invalid_candles.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    except Exception:
        # swallow errors to avoid raising during validator
        pass