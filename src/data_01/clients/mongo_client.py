"""
src/data_01/clients/mongo_client.py
MongoDB 鍮꾨룞湲??대씪?댁뼵??(motor 湲곕컲)

而щ젆??
    metadata          - ?щ낵 硫뷀??곗씠??
    priority_settings - ?곗씠???섏쭛 ?곗꽑?쒖쐞
    user_favorites    - ?ъ슜??愿??醫낅ぉ
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_db = None


def _build_uri() -> str:
    """?섍꼍 蹂?섏뿉??MongoDB URI瑜?援ъ꽦?⑸땲??"""
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
    """?깃???MongoDB ?곗씠?곕쿋?댁뒪 媛앹껜瑜?諛섑솚?⑸땲??"""
    global _db
    if _db is None:
        try:
            import motor.motor_asyncio as motor  # type: ignore
        except ImportError as exc:
            raise ImportError("motor ?⑦궎吏媛 ?꾩슂?⑸땲?? pip install motor") from exc

        uri     = _build_uri()
        db_name = os.getenv("MONGO_DB", "upbit_trader")
        client  = motor.AsyncIOMotorClient(uri)
        _db     = client[db_name]
        logger.info("MongoDB ?곌껐 ?꾨즺 (db=%s)", db_name)
    return _db


async def close_mongo_client() -> None:
    """MongoDB ?곌껐???レ뒿?덈떎."""
    global _db
    if _db is not None:
        _db.client.close()
        _db = None
        logger.info("MongoDB ?곌껐 醫낅즺")


class MongoClient:
    """MongoDB CRUD ?ы띁 ?대옒??"""

    def __init__(self, db) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------
    async def get_symbol_metadata(self, symbol: str, exchange: str = "upbit") -> Optional[dict]:
        """?щ낵 硫뷀??곗씠?곕? 議고쉶?⑸땲??"""
        return await self._db.metadata.find_one(
            {"symbol": symbol, "exchange": exchange},
            {"_id": 0},
        )

    async def get_active_symbols(self, exchange: str = "upbit") -> list[dict]:
        """?쒖꽦 ?щ낵 紐⑸줉??議고쉶?⑸땲??"""
        cursor = self._db.metadata.find(
            {"active": True, "exchange": exchange},
            {"symbol": 1, "base_tf": 1, "_id": 0},
        ).sort("volume_24h", -1)
        return await cursor.to_list(length=None)

    async def upsert_metadata(self, doc: dict) -> None:
        """?щ낵 硫뷀??곗씠?곕? ?낆꽌?명빀?덈떎."""
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
        """?곗꽑?쒖쐞 ?ㅼ젙??議고쉶?⑸땲??"""
        return await self._db.priority_settings.find_one(
            {"user_id": user_id},
            {"_id": 0},
        )

    async def update_priority_settings(self, user_id: str, settings: dict[str, Any]) -> None:
        """?곗꽑?쒖쐞 ?ㅼ젙???낅뜲?댄듃?⑸땲??"""
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
        """?ъ슜??愿??醫낅ぉ 紐⑸줉??議고쉶?⑸땲??"""
        doc = await self._db.user_favorites.find_one(
            {"user_id": user_id},
            {"symbols": 1, "_id": 0},
        )
        return doc.get("symbols", []) if doc else []

    async def update_favorites(self, user_id: str, symbols: list[str]) -> None:
        """愿??醫낅ぉ???낅뜲?댄듃?⑸땲??"""
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

