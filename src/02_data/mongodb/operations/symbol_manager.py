#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
심볼 메타데이터 관리자

컬렉션: metadata
인덱스: symbol (unique), exchange
"""
import logging
from typing import Optional, List, Dict, Any

from ..models.metadata import SymbolMetadata

LOG = logging.getLogger("mongo.operations.symbol_manager")

COLLECTION = "metadata"


class SymbolManager:
    """심볼 메타데이터 CRUD"""

    def __init__(self, db=None):
        self.db = db

    @property
    def _col(self):
        return self.db[COLLECTION] if self.db is not None else None

    async def ensure_indexes(self):
        """인덱스 생성 (idempotent)"""
        if self._col is None:
            return
        try:
            await self._col.create_index([("symbol", 1), ("exchange", 1)], unique=True)
            await self._col.create_index([("active", 1)])
            await self._col.create_index([("volume_24h", -1)])
            LOG.info("✅ metadata 인덱스 생성 완료")
        except Exception as e:
            LOG.debug("인덱스 생성 무시: %s", e)

    async def upsert(self, meta: SymbolMetadata) -> bool:
        """심볼 메타데이터 저장/갱신"""
        if self._col is None:
            return False
        try:
            doc = meta.to_dict()
            await self._col.update_one(
                {"symbol": meta.symbol, "exchange": meta.exchange},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:
            LOG.error("심볼 upsert 실패: %s", e)
            return False

    async def upsert_batch(self, symbols: List[SymbolMetadata]) -> int:
        """배치 upsert"""
        count = 0
        for s in symbols:
            if await self.upsert(s):
                count += 1
        return count

    async def get(self, symbol: str, exchange: str = "upbit") -> Optional[SymbolMetadata]:
        """심볼 조회"""
        if self._col is None:
            return None
        try:
            doc = await self._col.find_one({"symbol": symbol, "exchange": exchange})
            if doc:
                return SymbolMetadata.from_dict(doc)
        except Exception as e:
            LOG.error("심볼 조회 실패: %s", e)
        return None

    async def get_all_active(self, exchange: str = "upbit") -> List[SymbolMetadata]:
        """활성 심볼 전체 조회"""
        if self._col is None:
            return []
        try:
            cursor = self._col.find({"active": True, "exchange": exchange}).sort("volume_24h", -1)
            return [SymbolMetadata.from_dict(d) async for d in cursor]
        except Exception as e:
            LOG.error("활성 심볼 조회 실패: %s", e)
            return []

    async def search(self, query: str, limit: int = 20) -> List[SymbolMetadata]:
        """
        심볼 검색 (빠른 인덱스 조회).
        symbol 또는 korean_name 부분 매칭.
        """
        if self._col is None:
            return []
        try:
            cursor = self._col.find({
                "$or": [
                    {"symbol": {"$regex": query, "$options": "i"}},
                    {"korean_name": {"$regex": query, "$options": "i"}},
                    {"english_name": {"$regex": query, "$options": "i"}},
                ]
            }).limit(limit)
            return [SymbolMetadata.from_dict(d) async for d in cursor]
        except Exception as e:
            LOG.error("심볼 검색 실패: %s", e)
            return []

    async def deactivate(self, symbol: str, exchange: str = "upbit") -> bool:
        """심볼 비활성화"""
        if self._col is None:
            return False
        try:
            await self._col.update_one(
                {"symbol": symbol, "exchange": exchange},
                {"$set": {"active": False}},
            )
            return True
        except Exception as e:
            LOG.error("심볼 비활성화 실패: %s", e)
            return False
