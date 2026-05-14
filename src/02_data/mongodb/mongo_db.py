#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 연결 유틸

기능:
- connect/close/test_connection
- create_collections, create_indexes
- simple helpers for snapshots/meta

환경변수:
- MONGO_URI (예: mongodb://user:pass@host:27017/upbit_trader)
- 또는 MONGO_HOST/MONGO_PORT 등
"""

from __future__ import annotations
import os
import logging
import threading
from typing import Optional, List
from pathlib import Path

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import ConnectionFailure
except Exception:
    MongoClient = None
    ASCENDING = None
    ConnectionFailure = Exception

logger = logging.getLogger("mongo_db")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [mongo_db] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
logger.propagate = False


def _default_uri() -> str:
    from urllib.parse import quote_plus

    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    db = os.getenv("MONGO_DB", "upbit_trader")

    # Priority 1: individual plain-text credentials → encode with quote_plus
    # (avoids double-encoding if MONGO_URI already contains percent-encoded password)
    user = (
        os.getenv("MONGO_INITDB_ROOT_USERNAME")
        or os.getenv("MONGO_INITDB_ROOT_USERNAME_CONTAINER")
        or os.getenv("MONGO_USER")
        or os.getenv("MONGO_ID")
    )
    password = (
        os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        or os.getenv("MONGO_INITDB_ROOT_PASSWORD_CONTAINER")
        or os.getenv("MONGO_PASSWORD")
    )

    if user and password:
        return (
            f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{db}?authSource=admin"
        )

    # Priority 2: pre-built MONGO_URI (returned as-is)
    uri = os.getenv("MONGO_URI")
    if uri:
        return uri

    return f"mongodb://{host}:{port}/{db}"


class MongoConnector:
    """
    MongoDB 동기 연결 유틸리티 클래스.

    싱글톤 패턴 적용 (thread-safe Double-Checked Locking):
    - 동일한 프로세스 내에서 인스턴스를 하나만 생성하여 연결 고갈 방지
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # 싱글톤 인스턴스 생성 (Double-Checked Locking)
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, uri: Optional[str] = None):
        # 중복 초기화 방지
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.uri = uri or _default_uri()
        self.client = None
        self.db = None

    def connect(self, timeout_ms: int = 3000) -> bool:
        if MongoClient is None:
            logger.error("pymongo 미설치: pip install pymongo")
            return False
        # 이미 연결된 경우 ping으로 재사용
        if self.client is not None:
            try:
                self.client.admin.command("ping")
                return True
            except Exception:
                # 기존 연결 불량 → 재연결 시도
                self.client = None
                self.db = None
        try:
            # maxPoolSize=10: 연결 풀 최대 10개로 포트 고갈 방지
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=timeout_ms,
                maxPoolSize=10,
            )
            self.client.admin.command("ping")
            # URI에서 직접 파싱하지 않고 환경변수 우선 사용 (민감 정보 로깅 방지)
            dbname = os.getenv("MONGO_DB") or self._extract_dbname(self.uri)
            self.db = self.client[dbname]
            logger.info("MongoDB 연결 성공 (maxPoolSize=10): db=%s", dbname)
            return True
        except ConnectionFailure as e:
            logger.error("MongoDB 연결 실패: %s", e)
            self.client = None
            self.db = None
            return False
        except Exception as e:
            logger.exception("MongoDB 연결 중 예외: %s", e)
            self.client = None
            self.db = None
            return False

    def _extract_dbname(self, uri: str) -> str:
        # naive parse: last path segment
        parts = uri.split("/")
        if len(parts) >= 4 and parts[-1]:
            return parts[-1].split("?")[0]
        return os.getenv("MONGO_DB", "upbit_trader")

    def close(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.client = None
        self.db = None

    def test_connection(self) -> bool:
        return self.connect()

    def create_collections(self, collections: Optional[List[str]] = None):
        if not self.db and not self.connect():
            raise RuntimeError("MongoDB 연결되지 않음")
        default = ["latest_snapshot", "metadata", "candles_meta", "jobs", "logs"]
        for coll in (collections or default):
            try:
                if coll in self.db.list_collection_names():
                    logger.info("컬렉션 존재: %s", coll)
                else:
                    self.db.create_collection(coll)
                    logger.info("컬렉션 생성: %s", coll)
            except Exception as e:
                logger.exception("컬렉션 생성 실패: %s -> %s", coll, e)

    def create_indexes(self):
        if not self.db and not self.connect():
            raise RuntimeError("MongoDB 연결되지 않음")
        try:
            # latest_snapshot: (symbol, timeframe) 복합 unique
            # MetadataManager 가 {symbol, timeframe} 키로 upsert 하므로 동일하게 맞춘다.
            # 구버전 단일 (symbol,) unique 인덱스가 있으면 제거 후 복합 인덱스 재생성.
            try:
                existing = self.db.latest_snapshot.index_information()
            except Exception:
                existing = {}
            for legacy_name in ("idx_latest_snapshot_symbol", "idx_latest_symbol"):
                info = existing.get(legacy_name) if isinstance(existing, dict) else None
                if not info:
                    continue
                try:
                    key = info.get("key") or []
                    if list(key) == [("symbol", 1)] and info.get("unique"):
                        self.db.latest_snapshot.drop_index(legacy_name)
                        logger.info("구버전 latest_snapshot 단일 unique 인덱스 제거: %s", legacy_name)
                except Exception:
                    logger.debug("%s 인덱스 제거 무시", legacy_name, exc_info=True)
            self.db.latest_snapshot.create_index(
                [("symbol", ASCENDING), ("timeframe", ASCENDING)],
                unique=True,
                name="idx_latest_snapshot_symbol_tf",
            )
            logger.info("latest_snapshot 인덱스 생성/확인 (symbol, timeframe)")
        except Exception:
            logger.exception("latest_snapshot 인덱스 생성 실패")
        try:
            # jobs: job_id unique
            self.db.jobs.create_index([("job_id", ASCENDING)], unique=True, name="idx_jobs_job_id")
            logger.info("jobs 인덱스 생성/확인")
        except Exception:
            logger.exception("jobs 인덱스 생성 실패")

    # helper: save snapshot (upsert)
    def upsert_latest_snapshot(self, symbol: str, doc: dict):
        if not self.db and not self.connect():
            raise RuntimeError("MongoDB 연결되지 않음")
        try:
            self.db.latest_snapshot.update_one({"symbol": symbol}, {"$set": doc}, upsert=True)
            logger.debug("latest_snapshot upsert: %s", symbol)
        except Exception:
            logger.exception("latest_snapshot upsert 실패: %s", symbol)