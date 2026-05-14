# -*- coding: utf-8 -*-
"""
[Purpose]
MongoDB 컬렉션 수집 설정 저장/로드 관리자

[Responsibilities]
- 수집 타임프레임, 백필 기간, 압축/보존 정책 설정을 MongoDB에 영구 저장
- 재시작 후에도 설정 유지
- 기본값(용량 절약 모드) 제공

[Collection] upbit_trader.collection_settings
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CollectionSettingsManager:
    """MongoDB 기반 수집 설정 관리자."""

    DEFAULT_SETTINGS: Dict[str, Any] = {
        "enabled_timeframes": ["1m", "5m", "1h"],
        "lookback_days": 3,
        "compression_days": 1,
        "retention_days": 90,
        "preset": "save_disk",
    }

    def __init__(self, mongo_client: Any) -> None:
        """
        Args:
            mongo_client: motor.motor_asyncio.AsyncIOMotorClient 인스턴스
        """
        self._client = mongo_client

    def _collection(self) -> Any:
        return self._client["upbit_trader"]["collection_settings"]

    async def load_settings(self, user_id: str = "default") -> Dict[str, Any]:
        """설정 로드. 저장된 값이 없으면 DEFAULT_SETTINGS 반환."""
        try:
            doc = await self._collection().find_one({"user_id": user_id})
            if doc:
                return {k: v for k, v in doc.items() if k not in ("_id", "user_id")}
        except Exception as exc:
            logger.warning("[CollectionSettings] 설정 로드 실패: %s", exc)
        return self.DEFAULT_SETTINGS.copy()

    async def save_settings(
        self, settings: Dict[str, Any], user_id: str = "default"
    ) -> None:
        """설정 저장 (upsert)."""
        try:
            payload = {**settings, "updated_at": datetime.now(timezone.utc)}
            await self._collection().update_one(
                {"user_id": user_id},
                {"$set": payload},
                upsert=True,
            )
            logger.info("[CollectionSettings] 설정 저장 완료: %s", settings)
        except Exception as exc:
            logger.error("[CollectionSettings] 설정 저장 실패: %s", exc)
            raise

    async def reset_to_default(self, user_id: str = "default") -> None:
        """기본값으로 초기화."""
        await self.save_settings(self.DEFAULT_SETTINGS.copy(), user_id)
        logger.info("[CollectionSettings] 기본값으로 초기화 완료")
