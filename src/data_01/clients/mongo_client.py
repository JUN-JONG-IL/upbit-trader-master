"""
src/data_01/clients/mongo_client.py
MongoDB 비동기 클라이언트 (motor 기반)

컬렉션:
    metadata          - 심볼 메타데이터
    priority_settings - 데이터 수집 우선순위
    user_favorites    - 사용자 관심 종목
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_db = None


def _build_uri() -> str:
    """환경 변수에서 MongoDB URI를 구성합니다."""
    uri = os.getenv("MONGO_URI")
    if uri:
        return uri
    host     = os.getenv("MONGO_HOST", "localhost")
    port     = os.getenv("MONGO_PORT", "27017")
    user     = os.getenv("MONGO_INITDB_ROOT_USERNAME", "")
    password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "")
    db_name  = os.getenv("MONGO_DB", "upbit_trader")
    if user and password:
        return f"mongodb://{user}:{password}@{host}:{port}/{db_name}"
    return f"mongodb://{host}:{port}/{db_name}"


async def get_mongo_db():
    """싱글턴 MongoDB 데이터베이스 객체를 반환합니다."""
    global _db
    if _db is None:
        try:
            import motor.motor_asyncio as motor  # type: ignore
        except ImportError as exc:
            raise ImportError("motor 패키지가 필요합니다: pip install motor") from exc

        uri     = _build_uri()
        db_name = os.getenv("MONGO_DB", "upbit_trader")
        client  = motor.AsyncIOMotorClient(uri)
        _db     = client[db_name]
        logger.info("MongoDB 연결 완료 (db=%s)", db_name)
    return _db


async def close_mongo_client() -> None:
    """MongoDB 연결을 닫습니다."""
    global _db
    if _db is not None:
        _db.client.close()
        _db = None
        logger.info("MongoDB 연결 종료")


class MongoClient:
    """MongoDB CRUD 헬퍼 클래스."""

    def __init__(self, db) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------
    async def get_symbol_metadata(self, symbol: str, exchange: str = "upbit") -> Optional[dict]:
        """심볼 메타데이터를 조회합니다."""
        return await self._db.metadata.find_one(
            {"symbol": symbol, "exchange": exchange},
            {"_id": 0},
        )

    async def get_active_symbols(self, exchange: str = "upbit") -> list[dict]:
        """활성 심볼 목록을 조회합니다."""
        cursor = self._db.metadata.find(
            {"active": True, "exchange": exchange},
            {"symbol": 1, "base_tf": 1, "_id": 0},
        ).sort("volume_24h", -1)
        return await cursor.to_list(length=None)

    async def upsert_metadata(self, doc: dict) -> None:
        """심볼 메타데이터를 업서트합니다."""
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        doc["updated_at"] = now
        await self._db.metadata.update_one(
            {"symbol": doc["symbol"], "exchange": doc.get("exchange", "upbit")},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    # ------------------------------------------------------------------
    # priority_settings
    # ------------------------------------------------------------------
    async def get_priority_settings(self, user_id: str = "default") -> Optional[dict]:
        """우선순위 설정을 조회합니다."""
        return await self._db.priority_settings.find_one(
            {"user_id": user_id},
            {"_id": 0},
        )

    async def update_priority_settings(self, user_id: str, settings: dict[str, Any]) -> None:
        """우선순위 설정을 업데이트합니다."""
        from datetime import datetime, timezone
        await self._db.priority_settings.update_one(
            {"user_id": user_id},
            {"$set": {"settings": settings, "updated_at": datetime.now(tz=timezone.utc)}},
            upsert=True,
        )

    # ------------------------------------------------------------------
    # user_favorites
    # ------------------------------------------------------------------
    async def get_favorites(self, user_id: str = "default") -> list[str]:
        """사용자 관심 종목 목록을 조회합니다."""
        doc = await self._db.user_favorites.find_one(
            {"user_id": user_id},
            {"symbols": 1, "_id": 0},
        )
        return doc.get("symbols", []) if doc else []

    async def update_favorites(self, user_id: str, symbols: list[str]) -> None:
        """관심 종목을 업데이트합니다."""
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        await self._db.user_favorites.update_one(
            {"user_id": user_id},
            {
                "$set":         {"symbols": symbols, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
