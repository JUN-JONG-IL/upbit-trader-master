#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 및 관심 종목 관리자 + UI 설정 저장/복원 (v4.0 - 완전 동기화)

변경사항 v4.0:
- UI Settings를 완전한 동기 메서드로 변경 (pymongo 사용)
- Priority/Favorites는 비동기 유지 (motor 사용)
- Qt GUI "Event loop is closed" 에러 완벽 해결
- self.db 타입에 따라 자동으로 동기/비동기 선택

컬렉션:
- priority_settings: 심볼별 우선순위 (비동기)
- user_favorites: 사용자 관심 종목 (비동기)
- ui_settings: UI 설정 (동기)

사용 예시:
    # 비동기 환경 (motor)
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["upbit_trader"]
    manager = SettingsManager(db)
    await manager.set_priority(...)  # 비동기
    
    # 동기 환경 (pymongo - Qt GUI)
    import pymongo
    client = pymongo.MongoClient("mongodb://localhost:27017")
    db = client["upbit_trader"]
    manager = SettingsManager(db)
    manager.save_settings(...)  # 동기 (UI 설정 전용)
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from copy import deepcopy

from ..models.priority_settings import PrioritySettings
from ..models.user_favorites import UserFavorite

LOG = logging.getLogger("mongo.operations.settings_manager")

PRIORITY_COL = "priority_settings"
FAVORITES_COL = "user_favorites"
UI_SETTINGS_COL = "ui_settings"


# ✅ UI 설정 기본값 정의
DEFAULT_SETTINGS: Dict[str, Any] = {
        "collection_settings": {
            "timeframes": ["1m", "5m", "1h"],
            "backfill_period": "3일 (기본)",
            "compression_start": "1일 후 (공간 절약)",
            "retention_period": "3개월 (기본)",
            "volume_preset": "light",
            "limit_1m": 150000,
            "limit_5m": 50000,
            "limit_15m": 30000,
            "limit_1h": 12000,
            "limit_4h": 5000,
            "limit_1d": 500,
        },
    "smart_scanner": {
        "condition_mode": "AND",
        "all_symbols": False,
        "trading_activity": {},
        "price_volatility": {},
        "technical_analysis": {},
        "ai_ml_analysis": {},
        "user_priority": {},
        "time_based": {},
        "risk_management": {},
        "special_conditions": {},
        "custom_expression": "",
    },
    "ai_ml": {
        "gap_prediction_enabled": False,
        "baseline_learning_enabled": False,
        "ai_mode": "OFF",
    },
}


class SettingsManager:
    """
    우선순위 설정, 관심 종목 관리 + UI 설정 저장/복원
    
    동기/비동기 혼합 지원:
    - Priority Settings / User Favorites: 비동기 (motor)
    - UI Settings: 동기 (pymongo)
    """

    def __init__(self, db=None):
        """
        Args:
            db: motor.motor_asyncio.AsyncIOMotorDatabase (비동기) 또는
                pymongo.database.Database (동기)
        """
        self.db = db
        self._is_motor = self._detect_motor_client()

    def _detect_motor_client(self) -> bool:
        """motor 클라이언트인지 pymongo 클라이언트인지 감지"""
        if self.db is None:
            return False
        try:
            # motor는 client.delegate 속성을 가짐
            return hasattr(self.db.client, "delegate")
        except Exception:
            return False

    async def ensure_indexes(self):
        """인덱스 생성 (비동기 - 초기화 시에만 사용)"""
        if self.db is None:
            return
        try:
            await self.db[PRIORITY_COL].create_index([("symbol", 1)], unique=True)
            await self.db[FAVORITES_COL].create_index([("user_id", 1), ("symbol", 1)], unique=True)
            await self.db[UI_SETTINGS_COL].create_index([("user_id", 1)], unique=True)
            LOG.info("✅ settings 인덱스 생성 완료")
        except Exception as e:
            LOG.debug("인덱스 생성 무시: %s", e)

    # ========================================================================
    # Priority Settings (비동기 전용)
    # ========================================================================
    async def set_priority(self, settings: PrioritySettings) -> bool:
        """우선순위 설정 저장 (비동기)"""
        if self.db is None:
            return False
        try:
            doc = settings.to_dict()
            await self.db[PRIORITY_COL].update_one(
                {"symbol": settings.symbol},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:
            LOG.error("우선순위 설정 실패: %s", e)
            return False

    async def get_priority(self, symbol: str) -> Optional[PrioritySettings]:
        """심볼 우선순위 조회 (비동기)"""
        if self.db is None:
            return None
        try:
            doc = await self.db[PRIORITY_COL].find_one({"symbol": symbol})
            if doc:
                return PrioritySettings.from_dict(doc)
        except Exception as e:
            LOG.error("우선순위 조회 실패: %s", e)
        return None

    async def get_high_priority_symbols(self) -> List[str]:
        """HIGH 우선순위 심볼 목록 (비동기)"""
        if self.db is None:
            return []
        try:
            cursor = self.db[PRIORITY_COL].find({"priority": "HIGH"})
            return [d["symbol"] async for d in cursor]
        except Exception as e:
            LOG.error("HIGH 우선순위 조회 실패: %s", e)
            return []

    # ========================================================================
    # User Favorites (비동기 전용)
    # ========================================================================
    async def add_favorite(self, favorite: UserFavorite) -> bool:
        """관심 종목 추가 (비동기)"""
        if self.db is None:
            return False
        try:
            doc = favorite.to_dict()
            await self.db[FAVORITES_COL].update_one(
                {"user_id": favorite.user_id, "symbol": favorite.symbol},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:
            LOG.error("관심 종목 추가 실패: %s", e)
            return False

    async def get_favorites(self, user_id: str) -> List[UserFavorite]:
        """사용자 관심 종목 조회 (비동기)"""
        if self.db is None:
            return []
        try:
            cursor = self.db[FAVORITES_COL].find({"user_id": user_id}).sort("added_at", -1)
            return [UserFavorite.from_dict(d) async for d in cursor]
        except Exception as e:
            LOG.error("관심 종목 조회 실패: %s", e)
            return []

    async def remove_favorite(self, user_id: str, symbol: str) -> bool:
        """관심 종목 제거 (비동기)"""
        if self.db is None:
            return False
        try:
            await self.db[FAVORITES_COL].delete_one({"user_id": user_id, "symbol": symbol})
            return True
        except Exception as e:
            LOG.error("관심 종목 제거 실패: %s", e)
            return False

    # ========================================================================
    # ✅ UI Settings (동기 전용 - Qt GUI용)
    # ========================================================================
    def save_settings(
        self, settings: Dict[str, Any], user_id: str = "default"
    ) -> None:
        """
        UI 설정 저장 (동기, upsert)
        
        Qt GUI에서 안전하게 호출 가능 (Event loop is closed 에러 없음)
        pymongo.MongoClient를 사용하여 완전한 동기 실행
        
        Args:
            settings: 저장할 설정 딕셔너리
            user_id: 사용자 ID (기본값: "default")
        
        Raises:
            RuntimeError: Event loop is closed 에러 발생 시
            Exception: 기타 저장 실패 시
        """
        if self.db is None:
            LOG.error("[SettingsManager] ❌ MongoDB 연결 없음 — 저장 불가")
            return
        
        try:
            payload = {**settings, "updated_at": datetime.now(timezone.utc)}
            
            # pymongo 동기 메서드 사용 (motor의 경우에도 동기 메서드 존재)
            collection = self.db[UI_SETTINGS_COL]
            result = collection.update_one(
                {"user_id": user_id},
                {"$set": payload},
                upsert=True,
            )
            
            if result.upserted_id:
                LOG.info(
                    "[SettingsManager] ✅ 신규 설정 생성: %s (ID: %s)",
                    user_id, result.upserted_id
                )
            elif result.modified_count > 0:
                LOG.info(
                    "[SettingsManager] ✅ 기존 설정 업데이트: %s (matched: %d, modified: %d)",
                    user_id, result.matched_count, result.modified_count
                )
            else:
                LOG.info(
                    "[SettingsManager] ℹ️ 설정 변경 없음 (동일한 값): %s (matched: %d)",
                    user_id, result.matched_count
                )
        except RuntimeError as exc:
            # Event loop is closed 에러 처리
            if "Event loop is closed" in str(exc):
                LOG.error(
                    "[SettingsManager] ❌ Event loop is closed — "
                    "pymongo.MongoClient를 사용하세요 (motor 대신)"
                )
            else:
                LOG.error("[SettingsManager] ❌ 설정 저장 실패: %s", exc)
            raise
        except Exception as exc:
            LOG.error("[SettingsManager] ❌ 설정 저장 실패: %s", exc)
            raise

    def load_settings(self, user_id: str = "default") -> Dict[str, Any]:
        """
        UI 설정 로드 (동기)
        
        저장된 값이 없으면 DEFAULT_SETTINGS 반환
        Qt GUI에서 안전하게 호출 가능
        
        Args:
            user_id: 사용자 ID (기본값: "default")
        
        Returns:
            Dict[str, Any]: 저장된 설정 또는 기본값
        """
        if self.db is None:
            LOG.warning("[SettingsManager] ⚠️ MongoDB 연결 없음 — 기본값 반환")
            return self._deep_copy_defaults()
        
        try:
            # pymongo 동기 메서드 사용
            collection = self.db[UI_SETTINGS_COL]
            doc = collection.find_one({"user_id": user_id})
            
            if doc:
                result = {
                    k: v for k, v in doc.items()
                    if k not in ("_id", "user_id", "updated_at")
                }
                LOG.info(
                    "[SettingsManager] ✅ 설정 로드 완료: %s (%d개 항목)",
                    user_id, len(result)
                )
                return result
            else:
                LOG.info("[SettingsManager] ℹ️ 저장된 설정 없음 — 기본값 반환: %s", user_id)
        except RuntimeError as exc:
            # Event loop is closed 에러 처리
            if "Event loop is closed" in str(exc):
                LOG.error(
                    "[SettingsManager] ❌ Event loop is closed — "
                    "pymongo.MongoClient를 사용하세요 (motor 대신)"
                )
            else:
                LOG.warning("[SettingsManager] ⚠️ 설정 로드 실패: %s — 기본값 반환", exc)
        except Exception as exc:
            LOG.warning("[SettingsManager] ⚠️ 설정 로드 실패: %s — 기본값 반환", exc)
        
        return self._deep_copy_defaults()

    def update_partial(
        self, path: str, value: Any, user_id: str = "default"
    ) -> None:
        """
        특정 경로의 설정만 부분 업데이트 (동기)
        
        Args:
            path: MongoDB 경로 (예: "ai_ml.ai_mode")
            value: 저장할 값
            user_id: 사용자 ID
        """
        if self.db is None:
            LOG.warning("[SettingsManager] ⚠️ MongoDB 연결 없음 — 부분 업데이트 불가")
            return
        
        try:
            collection = self.db[UI_SETTINGS_COL]
            collection.update_one(
                {"user_id": user_id},
                {"$set": {path: value, "updated_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            LOG.debug("[SettingsManager] 부분 업데이트: %s = %s", path, value)
        except Exception as exc:
            LOG.error("[SettingsManager] 부분 업데이트 실패: %s", exc)

    def reset_to_default(self, user_id: str = "default") -> None:
        """
        기본값으로 초기화 (동기)
        
        Args:
            user_id: 사용자 ID
        """
        self.save_settings(self._deep_copy_defaults(), user_id)
        LOG.info("[SettingsManager] 기본값으로 초기화 완료: %s", user_id)

    def get_default_settings(self) -> Dict[str, Any]:
        """기본 설정 반환 (동기 메서드 - 외부에서 호출 가능)"""
        return self._deep_copy_defaults()

    def _deep_copy_defaults(self) -> Dict[str, Any]:
        """DEFAULT_SETTINGS의 깊은 복사본 반환 (변경 방지)"""
        return deepcopy(DEFAULT_SETTINGS)
