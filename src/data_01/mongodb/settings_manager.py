# -*- coding: utf-8 -*-
"""
[Purpose]
MongoDB 기반 앱 전체 UI 설정 저장/복원 매니저 (v4.0 - 동기 버전)

[Responsibilities]
- 수집 설정, AI/ML 설정, 스마트 스캐너 설정을 MongoDB에 영구 저장
- 앱 재시작 후에도 설정 유지
- 기본값 제공

[변경사항 v4.0]
- motor.motor_asyncio.AsyncIOMotorClient → pymongo.MongoClient (동기)
- async/await 완전 제거
- Qt GUI에서 "Event loop is closed" 에러 완벽 해결

[Collection] upbit_trader.ui_settings
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SettingsManager:
    """MongoDB 기반 앱 설정 저장/복원 매니저 (100% 동기)."""

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

    def __init__(self, mongo_client: Any) -> None:
        """
        Args:
            mongo_client: pymongo.MongoClient 인스턴스 (동기)
                          ✅ motor AsyncIOMotorClient는 사용 불가 (Event loop is closed 에러)
        """
        self._client = mongo_client

    def _collection(self) -> Any:
        """ui_settings 컬렉션 반환 (동기)"""
        return self._client["upbit_trader"]["ui_settings"]

    def load_settings(self, user_id: str = "default") -> Dict[str, Any]:
        """
        설정 로드 (동기). 저장된 값이 없으면 DEFAULT_SETTINGS 반환.
        
        Returns:
            Dict[str, Any]: 저장된 설정 또는 기본값
        """
        try:
            # pymongo 동기 메서드 사용
            doc = self._collection().find_one({"user_id": user_id})
            if doc:
                result = {k: v for k, v in doc.items() if k not in ("_id", "user_id", "updated_at")}
                logger.info("[SettingsManager] ✅ 설정 로드 완료: %s (%d개 항목)", user_id, len(result))
                return result
            else:
                logger.info("[SettingsManager] ℹ️ 저장된 설정 없음 — 기본값 반환: %s", user_id)
        except Exception as exc:
            logger.warning("[SettingsManager] ⚠️ 설정 로드 실패: %s — 기본값 반환", exc)
        return self._deep_copy_defaults()

    def save_settings(
        self, settings: Dict[str, Any], user_id: str = "default"
    ) -> None:
        """
        설정 저장 (동기, upsert).
        
        Args:
            settings: 저장할 설정 딕셔너리
            user_id: 사용자 ID (기본값: "default")
        
        Raises:
            Exception: 저장 실패 시 예외 발생
        """
        try:
            payload = {**settings, "updated_at": datetime.now(timezone.utc)}
            # pymongo 동기 메서드 사용
            result = self._collection().update_one(
                {"user_id": user_id},
                {"$set": payload},
                upsert=True,
            )
            if result.upserted_id:
                logger.info(
                    "[SettingsManager] ✅ 신규 설정 생성 완료: %s (ID: %s)",
                    user_id, result.upserted_id,
                )
            elif result.modified_count > 0:
                logger.info(
                    "[SettingsManager] ✅ 기존 설정 업데이트 완료: %s (matched: %d, modified: %d)",
                    user_id, result.matched_count, result.modified_count,
                )
            else:
                logger.info(
                    "[SettingsManager] ℹ️ 설정 변경 없음 (동일한 값): %s (matched: %d)",
                    user_id, result.matched_count,
                )
        except Exception as exc:
            logger.error("[SettingsManager] ❌ 설정 저장 실패: %s", exc)
            raise

    def update_partial(
        self, path: str, value: Any, user_id: str = "default"
    ) -> None:
        """
        특정 경로의 설정만 부분 업데이트 (동기).
        
        Args:
            path: MongoDB 경로 (예: "ai_ml.ai_mode")
            value: 저장할 값
            user_id: 사용자 ID
        """
        try:
            # pymongo 동기 메서드 사용
            self._collection().update_one(
                {"user_id": user_id},
                {"$set": {path: value, "updated_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            logger.debug("[SettingsManager] 부분 업데이트: %s = %s", path, value)
        except Exception as exc:
            logger.error("[SettingsManager] 부분 업데이트 실패: %s", exc)

    def reset_to_default(self, user_id: str = "default") -> None:
        """
        기본값으로 초기화 (동기).
        
        Args:
            user_id: 사용자 ID
        """
        self.save_settings(self._deep_copy_defaults(), user_id)
        logger.info("[SettingsManager] 기본값으로 초기화 완료: %s", user_id)

    def _deep_copy_defaults(self) -> Dict[str, Any]:
        """기본 설정의 깊은 복사본을 반환합니다 (변경 방지)."""
        return copy.deepcopy(self.DEFAULT_SETTINGS)

    def get_default_settings(self) -> Dict[str, Any]:
        """기본 설정의 깊은 복사본을 반환합니다 (공개 API)."""
        return self._deep_copy_defaults()
