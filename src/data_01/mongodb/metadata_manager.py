# -*- coding: utf-8 -*-
"""
MongoDB 메타데이터 관리자 (Metadata Manager)

목적:
    DB설계.md §3 MongoDB 설계에 따라 심볼 메타데이터 컬렉션을 관리합니다.
    - metadata 컬렉션: 심볼 정보 (한글명, 거래소, 활성 여부 등)
    - priority_settings: 데이터 수집 우선순위 설정
    - user_favorites: 관심 종목
    - latest_snapshot: 갭 감지용 최신 상태

변경사항 요약:
    - 사용자별 표시 타임존 저장/조회 메서드 추가 (get_user_timezone / set_user_timezone)
    - snapshot 갱신 시 UTC 표준화 적용
    - 원자적 최신화용 update_snapshot_if_new 추가 ($max 연산 사용)
    - create_metadata_manager(...) 팩토리 확장: 다양한 인자 이름 허용(db/mongo_db/mongo/data_manager/static 등),
      내부적으로 src.data_01.mongodb.init_mongodb.get_db()를 시도해 동기 DB 획득을 지원하도록 보강.
    - pymongo/motor Database 객체의 명시적 None 검사 적용(불린 테스트 제거) — NotImplementedError 예방
    - event-loop 충돌("attached to a different loop") 감지 시 안전하게 동기(pymongo) 폴백 경로 추가:
      get_snapshot, get_symbol, get_active_symbols 등에서 motor 예외 발생 시 동기 조회로 재시도합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import importlib
import importlib.util
import os
import traceback

logger = logging.getLogger(__name__)

# 에러 로그 속도 제한 유틸리티 로드 (core 디렉터리명이 숫자로 시작하므로 파일 기반 로드)
_log_error_throttled = None
try:
    _et_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "utils", "error_throttler.py")
    )
    if os.path.isfile(_et_path):
        _et_spec = importlib.util.spec_from_file_location("_error_throttler_mm", _et_path)
        if _et_spec and _et_spec.loader:
            _et_mod = importlib.util.module_from_spec(_et_spec)
            _et_spec.loader.exec_module(_et_mod)
            _log_error_throttled = getattr(_et_mod, "log_error_throttled", None)
except Exception:
    pass

# RateLimitedErrorFilter 폴백 (error_throttler 로드 실패 시)
_RateLimitedErrorFilter = None
try:
    _lc_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core", "config", "logging_config.py")
    )
    if os.path.isfile(_lc_path):
        _lc_spec = importlib.util.spec_from_file_location("_logging_config", _lc_path)
        if _lc_spec and _lc_spec.loader:
            _lc_mod = importlib.util.module_from_spec(_lc_spec)
            _lc_spec.loader.exec_module(_lc_mod)
            _RateLimitedErrorFilter = getattr(_lc_mod, "RateLimitedErrorFilter", None)
except Exception:
    pass

if _RateLimitedErrorFilter is not None:
    try:
        logger.addFilter(_RateLimitedErrorFilter(interval_seconds=300))
    except Exception:
        pass

# 컬렉션 이름
_COL_META = "metadata"
_COL_PRIORITY = "priority_settings"
_COL_FAVORITES = "user_favorites"
_COL_SNAPSHOT = "latest_snapshot"
_COL_STRATEGIES = "strategies"
_COL_ML_MODELS = "ml_models"

# 기본 표시 타임존 (UI에서 변경 가능)
_DEFAULT_DISPLAY_TZ = "Asia/Seoul"


# Event Loop 오류 패턴 목록 (update_snapshot_if_new에서 동기 fallback 전환 시 사용)
_EVENT_LOOP_ERROR_KEYWORDS = (
    "event loop",
    "closed",
    "different event loop",
    "bound to a different",
    "attached to a different",
)


def _ensure_dt_utc(dt: datetime) -> datetime:
    """
    datetime을 받아 UTC timezone-aware datetime으로 반환.
    naive datetime이면 tzinfo=UTC로 지정, 다른 tz면 UTC로 변환.
    """
    if dt is None:
        raise ValueError("datetime 값이 필요합니다.")
    if not isinstance(dt, datetime):
        raise ValueError("datetime 인스턴스가 필요합니다.")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _should_fallback_to_sync(exc: Exception) -> bool:
    """
    발생한 예외에서 'event loop 관련' 패턴이 보이면 동기 폴백을 권장.
    """
    try:
        s = str(exc).lower()
        for kw in _EVENT_LOOP_ERROR_KEYWORDS:
            if kw in s:
                return True
    except Exception:
        pass
    return False


class MetadataManager:
    """MongoDB 메타데이터 컬렉션 통합 관리자.

    모든 메서드는 motor (비동기 MongoDB 드라이버)를 사용합니다.
    DB 연결이 None이면 조작 없이 빈 값을 반환합니다.
    """

    def __init__(self, db) -> None:
        """
        Args:
            db: motor AsyncIOMotorDatabase 인스턴스.
        """
        self._db = db

    # ------------------------------------------------------------------
    # metadata 컬렉션 (심볼 정보)
    # ------------------------------------------------------------------

    async def upsert_symbol(
        self,
        symbol: str,
        *_,
        exchange: str = "upbit",
        korean_name: str = "",
        english_name: str = "",
        is_active: bool = True,
        market_cap: Optional[float] = None,
        volume_24h: Optional[float] = None,
        base_tf: str = "1m",
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """심볼 메타데이터를 upsert합니다."""
        if self._db is None:
            return False
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "symbol": symbol,
            "exchange": exchange,
            "korean_name": korean_name,
            "english_name": english_name,
            "is_active": is_active,
            "base_tf": base_tf,
            "updated_at": now,
        }
        if market_cap is not None:
            doc["market_cap"] = market_cap
        if volume_24h is not None:
            doc["volume_24h"] = volume_24h
        if extra:
            doc.update(extra)

        try:
            await self._db[_COL_META].update_one(
                {"symbol": symbol, "exchange": exchange},
                {
                    "$set": doc,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            # 예외 메시지에 따라 동기 폴백 고려 (업데이트는 중요하므로 동기 폴백 시도하지 않음)
            logger.error("upsert_symbol 실패 (%s): %s", symbol, exc)
            return False

    def update_symbol_metadata(self, symbol: str, metadata: Dict[str, Any]) -> bool:
        """심볼 메타데이터를 동기 방식으로 업데이트합니다 (UI 스레드/PyQt5 안전)."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] 동기 MongoDB 연결 없음 — 메타데이터 업데이트 건너뜀")
                return False
            now = datetime.now(timezone.utc)
            update_doc = dict(metadata)
            update_doc["updated_at"] = now
            result = connector.db[_COL_META].update_one(
                {"symbol": symbol},
                {
                    "$set": update_doc,
                    "$currentDate": {"updated_at": True},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            return result.modified_count > 0 or result.upserted_id is not None or result.matched_count > 0
        except Exception as exc:
            logger.error("[MetadataManager] 메타데이터 업데이트 실패 (%s): %s", symbol, exc)
            return False

    async def get_symbol(self, symbol: str, exchange: str = "upbit") -> Optional[Dict[str, Any]]:
        """단일 심볼 메타데이터를 조회합니다."""
        if self._db is None:
            return None
        try:
            doc = await self._db[_COL_META].find_one(
                {"symbol": symbol, "exchange": exchange},
                {"_id": 0},
            )
            return doc
        except Exception as exc:
            # 이벤트 루프 관련 예외 감지 시 동기 폴백
            if _should_fallback_to_sync(exc):
                try:
                    # 동기 조회 시도
                    return self._sync_get_symbol(symbol, exchange)
                except Exception:
                    logger.debug("[MetadataManager] 동기 get_symbol 폴백 실패: %s", exc)
            logger.error("get_symbol 실패 (%s): %s", symbol, exc)
            return None

    def _sync_get_symbol(self, symbol: str, exchange: str = "upbit") -> Optional[Dict[str, Any]]:
        """동기 pymongo를 통한 get_symbol 폴백."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] 동기 MongoDB 연결 없음 — get_symbol 건너뜀")
                return None
            doc = connector.db[_COL_META].find_one({"symbol": symbol, "exchange": exchange}, {"_id": 0})
            return doc
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_symbol 실패 (%s): %s", symbol, exc)
            return None

    async def get_active_symbols(
        self,
        exchange: str = "upbit",
        limit: int = 10_000,
    ) -> List[str]:
        """활성 심볼 목록을 반환합니다."""
        if self._db is None:
            return []
        try:
            cursor = (
                self._db[_COL_META]
                .find({"exchange": exchange, "is_active": True}, {"symbol": 1, "_id": 0})
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return [d["symbol"] for d in docs if "symbol" in d]
        except Exception as exc:
            if _should_fallback_to_sync(exc):
                try:
                    return self._sync_get_active_symbols(exchange, limit)
                except Exception:
                    logger.debug("[MetadataManager] 동기 get_active_symbols 폴백 실패: %s", exc)
            logger.error("get_active_symbols 실패: %s", exc)
            return []

    def _sync_get_active_symbols(self, exchange: str = "upbit", limit: int = 10_000) -> List[str]:
        """동기 pymongo를 통한 get_active_symbols 폴백."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] 동기 MongoDB 연결 없음 — get_active_symbols 건너뜀")
                return []
            cursor = connector.db[_COL_META].find({"exchange": exchange, "is_active": True}, {"symbol": 1, "_id": 0}).limit(limit)
            return [d["symbol"] for d in cursor]
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_active_symbols 실패: %s", exc)
            return []

    async def deactivate_symbol(self, symbol: str, exchange: str = "upbit") -> bool:
        """심볼을 비활성화합니다."""
        if self._db is None:
            return False
        try:
            await self._db[_COL_META].update_one(
                {"symbol": symbol, "exchange": exchange},
                {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
            )
            return True
        except Exception as exc:
            logger.error("deactivate_symbol 실패 (%s): %s", symbol, exc)
            return False

    # ------------------------------------------------------------------
    # latest_snapshot 컬렉션 (Gap Detection용)
    # ------------------------------------------------------------------

    async def update_snapshot(
        self,
        symbol: str,
        timeframe: str,
        last_candle_time: datetime,
    ) -> bool:
        """갭 감지용 최신 스냅샷을 갱신합니다. (단순 덮어쓰기)"""
        if self._db is None:
            return False
        try:
            last_candle_time = _ensure_dt_utc(last_candle_time)
            await self._db[_COL_SNAPSHOT].update_one(
                {"symbol": symbol, "timeframe": timeframe},
                {
                    "$set": {
                        "last_candle_time": last_candle_time,
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$setOnInsert": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "created_at": datetime.now(timezone.utc),
                    },
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.error("update_snapshot 실패 (%s/%s): %s", symbol, timeframe, exc)
            return False

    async def update_snapshot_if_new(
        self,
        symbol: str,
        timeframe: str,
        candidate_time: datetime,
    ) -> bool:
        """
        candidate_time이 기존 last_candle_time보다 최신인 경우에만 갱신합니다.
        동시성 상황에서 안전하게 최신 값만 보존하려면 이 메서드를 사용하세요.
        MongoDB의 $max 연산자를 사용하여 원자적으로 최신값을 유지합니다.
        Event Loop 오류 감지 시 동기 방식으로 자동 전환합니다.
        PyQt5 메인 스레드 등 비동기 컨텍스트 밖에서 호출 시 즉시 동기 방식으로 처리합니다.
        """
        # Event Loop 상태 선제 확인: 실행 중인 루프가 없으면 동기 방식으로 처리
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None or not loop.is_running():
            return self._sync_update_snapshot_if_new(symbol, timeframe, candidate_time)

        if self._db is None:
            # DB가 없으면 동기 방식으로 전환 시도
            return self._sync_update_snapshot_if_new(symbol, timeframe, candidate_time)
        try:
            candidate_time = _ensure_dt_utc(candidate_time)
            await self._db[_COL_SNAPSHOT].update_one(
                {"symbol": symbol, "timeframe": timeframe},
                {
                    "$max": {"last_candle_time": candidate_time},
                    "$setOnInsert": {"symbol": symbol, "timeframe": timeframe, "created_at": datetime.now(timezone.utc)},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            _exc_str = str(exc).lower()
            if any(kw in _exc_str for kw in _EVENT_LOOP_ERROR_KEYWORDS) or _should_fallback_to_sync(exc):
                logger.debug("[MetadataManager] Event Loop 오류 감지, 동기 방식으로 전환: %s", exc)
                return self._sync_update_snapshot_if_new(symbol, timeframe, candidate_time)
            if _log_error_throttled is not None:
                _log_error_throttled(logger, "update_snapshot_if_new_failed",
                                     f"update_snapshot_if_new 실패 ({symbol}/{timeframe}): {exc}")
            else:
                logger.error("update_snapshot_if_new 실패 (%s/%s): %s", symbol, timeframe, exc)
            return False

    def _sync_update_snapshot_if_new(
        self,
        symbol: str,
        timeframe: str,
        candidate_time: datetime,
    ) -> bool:
        """
        동기 방식으로 최신 스냅샷 갱신 (pymongo 사용, Event Loop 없이 호출 가능).
        MongoConnector 싱글톤을 통해 동기 pymongo 연결을 재사용합니다.
        """
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] 동기 MongoDB 연결 없음 — 스냅샷 갱신 건너뜀")
                return False
            candidate_time = _ensure_dt_utc(candidate_time)
            connector.db[_COL_SNAPSHOT].update_one(
                {"symbol": symbol, "timeframe": timeframe},
                {
                    "$max": {"last_candle_time": candidate_time},
                    "$setOnInsert": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "created_at": datetime.now(timezone.utc),
                    },
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            logger.debug("[MetadataManager] 동기 스냅샷 갱신: %s/%s", symbol, timeframe)
            return True
        except Exception as exc:
            logger.error("[MetadataManager] 동기 스냅샷 갱신 실패 (%s/%s): %s", symbol, timeframe, exc)
            return False

    async def get_snapshot(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[datetime]:
        """최신 스냅샷 시각을 반환합니다 (UTC-aware datetime)."""
        if self._db is None:
            return None
        try:
            doc = await self._db[_COL_SNAPSHOT].find_one(
                {"symbol": symbol, "timeframe": timeframe},
                {"last_candle_time": 1, "_id": 0},
            )
            if not doc:
                return None
            ts = doc.get("last_candle_time")
            if ts is None:
                return None
            if isinstance(ts, datetime):
                return _ensure_dt_utc(ts)
            try:
                return _ensure_dt_utc(datetime.fromisoformat(str(ts)))
            except Exception:
                logger.warning("get_snapshot: last_candle_time 파싱 실패, raw=%s", ts)
                return None
        except Exception as exc:
            # 이벤트 루프 충돌 등 motor 관련 에러 감지 시 동기 폴백
            if _should_fallback_to_sync(exc):
                try:
                    return self._sync_get_snapshot(symbol, timeframe)
                except Exception:
                    logger.debug("[MetadataManager] 동기 get_snapshot 폴백 실패: %s", exc)
            if "event loop is closed" in str(exc).lower():
                logger.debug("get_snapshot: event loop closed, returning None (%s/%s)", symbol, timeframe)
                return None
            if _log_error_throttled is not None:
                _log_error_throttled(logger, "get_snapshot_failed",
                                     f"get_snapshot 실패 ({symbol}/{timeframe}): {exc}")
            else:
                logger.error("get_snapshot 실패 (%s/%s): %s", symbol, timeframe, exc)
            return None

    def _sync_get_snapshot(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """동기 pymongo를 통한 get_snapshot 폴백."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] 동기 MongoDB 연결 없음 — get_snapshot 건너뜀")
                return None
            doc = connector.db[_COL_SNAPSHOT].find_one({"symbol": symbol, "timeframe": timeframe}, {"last_candle_time": 1, "_id": 0})
            if not doc:
                return None
            ts = doc.get("last_candle_time")
            if ts is None:
                return None
            if isinstance(ts, datetime):
                return _ensure_dt_utc(ts)
            try:
                return _ensure_dt_utc(datetime.fromisoformat(str(ts)))
            except Exception:
                logger.warning("[MetadataManager] _sync_get_snapshot last_candle_time 파싱 실패, raw=%s", ts)
                return None
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_snapshot 실패 (%s/%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # 안전권 진행률 (Phase 4 — TF Progress Widget 데이터 소스)
    # ------------------------------------------------------------------

    # TF별 1캔들 길이(초)
    _TF_SECONDS = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "1d": 86400,
    }

    # TF별 'SAFE' 판정 신선도 임계 (배수). 마지막 캔들이 N×TF 이내면 SAFE.
    _SAFE_FRESHNESS_FACTOR = 3

    async def compute_safe_zone_pct(
        self,
        symbol: str,
        timeframe: str,
        target_candles: int = 1000,
    ) -> Dict[str, Any]:
        """타임프레임별 '안전권' 진행률을 계산해 반환한다."""
        result: Dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "coverage_pct": 0.0,
            "last_safe_at": None,
            "status": "UNKNOWN",
        }
        try:
            tf_sec = self._TF_SECONDS.get(str(timeframe), 60)
            last = await self.get_snapshot(symbol, timeframe)
            if last is None:
                result["status"] = "STALE"
                return result
            now = datetime.now(timezone.utc)
            age_sec = max(0.0, (now - last).total_seconds())
            safe_threshold = tf_sec * self._SAFE_FRESHNESS_FACTOR
            stale_threshold = tf_sec * (self._SAFE_FRESHNESS_FACTOR * 5)
            if age_sec <= safe_threshold:
                status = "SAFE"
                pct = 100.0 * (1.0 - (age_sec / max(1.0, safe_threshold)) * 0.05)
            elif age_sec <= stale_threshold:
                status = "SYNCING"
                pct = 100.0 * max(0.0, 1.0 - (age_sec / max(1.0, stale_threshold)))
            else:
                status = "STALE"
                pct = 0.0
            result["coverage_pct"] = round(max(0.0, min(100.0, pct)), 2)
            result["status"] = status
            result["last_safe_at"] = last if status == "SAFE" else None
            return result
        except Exception as exc:
            logger.debug("compute_safe_zone_pct 실패 (%s/%s): %s", symbol, timeframe, exc)
            return result

    # ------------------------------------------------------------------
    # priority_settings 컬렉션
    # ------------------------------------------------------------------

    async def get_priority_settings(self, user_id: str = "default") -> Optional[Dict[str, Any]]:
        """우선순위 설정을 조회합니다."""
        if self._db is None:
            return None
        try:
            doc = await self._db[_COL_PRIORITY].find_one({"user_id": user_id}, {"_id": 0})
            return doc
        except Exception as exc:
            logger.error("get_priority_settings 실패: %s", exc)
            return None

    async def set_priority_settings(
        self,
        settings: Dict[str, Any],
        user_id: str = "default",
    ) -> bool:
        """우선순위 설정을 저장합니다."""
        if self._db is None:
            return False
        try:
            await self._db[_COL_PRIORITY].update_one(
                {"user_id": user_id},
                {
                    "$set": {"settings": settings, "updated_at": datetime.now(timezone.utc)},
                    "$setOnInsert": {"user_id": user_id},
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.error("set_priority_settings 실패: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 사용자 타임존 설정 (UI에서 선택 가능)
    # ------------------------------------------------------------------

    async def get_user_timezone(self, user_id: str = "default") -> str:
        """
        사용자별 표시 타임존을 반환합니다.
        - DB에 설정이 없으면 기본값 _DEFAULT_DISPLAY_TZ 반환.
        """
        if self._db is None:
            return _DEFAULT_DISPLAY_TZ
        try:
            doc = await self._db[_COL_PRIORITY].find_one({"user_id": user_id}, {"timezone": 1, "_id": 0})
            if doc and "timezone" in doc and doc["timezone"]:
                return doc["timezone"]
            return _DEFAULT_DISPLAY_TZ
        except Exception as exc:
            logger.error("get_user_timezone 실패: %s", exc)
            return _DEFAULT_DISPLAY_TZ

    async def set_user_timezone(self, tz_name: str, user_id: str = "default") -> bool:
        """
        사용자별 표시 타임존을 저장합니다. (예: 'Asia/Seoul', 'UTC')
        UI에서 변경 요청을 받으면 이 메서드를 호출하세요.
        """
        if self._db is None:
            return False
        try:
            await self._db[_COL_PRIORITY].update_one(
                {"user_id": user_id},
                {"$set": {"timezone": tz_name, "updated_at": datetime.now(timezone.utc)}, "$setOnInsert": {"user_id": user_id}},
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.error("set_user_timezone 실패: %s", exc)
            return False

    # ------------------------------------------------------------------
    # user_favorites 컬렉션
    # ------------------------------------------------------------------

    async def get_favorites(self, user_id: str = "default") -> List[str]:
        """관심 종목 목록을 반환합니다."""
        if self._db is None:
            return []
        try:
            doc = await self._db[_COL_FAVORITES].find_one({"user_id": user_id}, {"symbols": 1})
            return doc.get("symbols", []) if doc else []
        except Exception as exc:
            logger.error("get_favorites 실패: %s", exc)
            return []

    async def set_favorites(self, symbols: List[str], user_id: str = "default") -> bool:
        """관심 종목 목록을 저장합니다."""
        if self._db is None:
            return False
        try:
            await self._db[_COL_FAVORITES].update_one(
                {"user_id": user_id},
                {
                    "$set": {"symbols": symbols, "updated_at": datetime.now(timezone.utc)},
                    "$setOnInsert": {"user_id": user_id, "created_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.error("set_favorites 실패: %s", exc)
            return False


# -------------------------------------------------------------------------
# Noop 대체자: DB 미존재/테스트 환경에서 안전하게 사용 가능
# -------------------------------------------------------------------------
class NoopMetadataManager:
    """데이터베이스가 없을 때 사용하는 Noop 구현 — 동일한 비동기 API를 제공."""

    def __init__(self, *args, **kwargs):
        # DB 없음
        pass

    async def upsert_symbol(self, *args, **kwargs) -> bool:
        return False

    async def get_symbol(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        return None

    async def get_active_symbols(self, *args, **kwargs) -> List[str]:
        return []

    async def deactivate_symbol(self, *args, **kwargs) -> bool:
        return False

    async def update_snapshot(self, *args, **kwargs) -> bool:
        return False

    async def update_snapshot_if_new(self, *args, **kwargs) -> bool:
        return False

    def _sync_update_snapshot_if_new(self, *args, **kwargs) -> bool:
        """동기 방식 스냅샷 갱신 — Noop 구현"""
        return False

    async def get_snapshot(self, *args, **kwargs) -> Optional[datetime]:
        return None

    async def compute_safe_zone_pct(self, symbol: str = "", timeframe: str = "", **kwargs) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "coverage_pct": 0.0,
            "last_safe_at": None,
            "status": "UNKNOWN",
        }

    async def get_priority_settings(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        return None

    async def set_priority_settings(self, *args, **kwargs) -> bool:
        return False

    async def get_user_timezone(self, *args, **kwargs) -> str:
        return _DEFAULT_DISPLAY_TZ

    async def set_user_timezone(self, *args, **kwargs) -> bool:
        return False

    async def get_favorites(self, *args, **kwargs) -> List[str]:
        return []

    async def set_favorites(self, *args, **kwargs) -> bool:
        return False


# -------------------------------------------------------------------------
# 모듈 팩토리: loader/외부 코드가 일관된 방식으로 인스턴스 얻도록 함
# -------------------------------------------------------------------------
def _try_get_db_via_init_module() -> Optional[Any]:
    """
    가능한 init_mongodb 모듈을 찾아 get_db()를 호출해 동기 DB를 얻어 반환.
    실패하면 None.
    """
    candidates = ("src.data_01.mongodb.init_mongodb", "data_01.mongodb.init_mongodb", "data_01.mongodb.init_mongodb")
    for modname in candidates:
        try:
            mod = importlib.import_module(modname)
            get_db = getattr(mod, "get_db", None)
            if callable(get_db):
                try:
                    db = get_db()
                    if db is not None:
                        logger.debug("[metadata_manager] acquired db via %s.get_db()", modname)
                        return db
                except Exception:
                    logger.debug("[metadata_manager] %s.get_db() call failed: %s", modname, traceback.format_exc())
        except Exception:
            continue
    # 파일-level fallback: attempt loading by path relative to this file
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.abspath(os.path.join(here, "..", "mongodb", "init_mongodb.py"))
        if os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location("init_mongodb_file", candidate)
            if spec and spec.loader:
                mmod = importlib.util.module_from_spec(spec)  # type: ignore
                spec.loader.exec_module(mmod)  # type: ignore
                get_db = getattr(mmod, "get_db", None)
                if callable(get_db):
                    try:
                        db = get_db()
                        if db is not None:
                            logger.debug("[metadata_manager] acquired db via file init_mongodb.get_db()")
                            return db
                    except Exception:
                        logger.debug("[metadata_manager] file get_db() failed: %s", traceback.format_exc())
    except Exception:
        logger.debug("[metadata_manager] fallback file-level get_db attempt failed: %s", traceback.format_exc())
    return None


def create_metadata_manager(*args, **kwargs) -> Any:
    """
    보다 범용적으로 MetadataManager 인스턴스를 생성합니다.

    허용되는 인자(우선순위):
      - db, mongo_db, mongo, database (DB 객체 직접)
      - data_manager (객체) -> data_manager.db 또는 data_manager.mongo 등을 시도
      - static (부트스트랩된 static 모듈) -> static.data_manager 등에서 DB를 추출

    위 모든 방법으로 DB를 얻지 못하면 내부적으로 init_mongodb.get_db()를 시도합니다.
    최종적으로 DB를 얻지 못하면 NoopMetadataManager를 반환합니다.
    """
    db = None

    # 1) positional first arg (종종 db를 직접 전달하는 경우)
    if args:
        try:
            maybe = args[0]
            if maybe is not None:
                db = maybe
        except Exception:
            pass

    # 2) common kw names
    for k in ("db", "mongo_db", "mongo", "database"):
        if k in kwargs and kwargs[k] is not None:
            db = kwargs[k]
            break

    # 3) data_manager/static extraction
    if db is None:
        dm = kwargs.get("data_manager") or None
        if dm is None:
            static_obj = kwargs.get("static") or None
            if static_obj is None:
                # Try runtime import of bootstrap static if available
                try:
                    smod = importlib.import_module("src.server.app.static.static")
                    static_obj = getattr(smod, "static", None) or getattr(smod, "log", None) or static_obj
                except Exception:
                    try:
                        smod = importlib.import_module("static")
                        static_obj = getattr(smod, "static", None) or getattr(smod, "log", None) or static_obj
                    except Exception:
                        static_obj = None
        if static_obj is not None:
            try:
                dm = getattr(static_obj, "data_manager", None) or dm
            except Exception:
                dm = dm
        if dm is not None:
            # try common attributes
            for attr in ("db", "mongo_db", "database", "client"):
                try:
                    dval = getattr(dm, attr, None)
                    if dval is not None:
                        db = dval
                        break
                except Exception:
                    continue

    # 4) try init_mongodb.get_db() helper (sync)
    if db is None:
        try:
            db = _try_get_db_via_init_module()
        except Exception:
            db = None

    # 5) final decision
    try:
        if db is not None:
            try:
                logger.info("[metadata_manager] Creating MetadataManager with DB")
                return MetadataManager(db)
            except Exception:
                logger.exception("[metadata_manager] MetadataManager init failed; falling back to Noop")
                return NoopMetadataManager()
    except Exception:
        logger.exception("[metadata_manager] Unexpected error while creating MetadataManager: %s", traceback.format_exc())
        return NoopMetadataManager()

    logger.info("[metadata_manager] No DB available — returning NoopMetadataManager")
    return NoopMetadataManager()


# backward-compat convenience name
get_metadata_manager = create_metadata_manager

__all__ = ["MetadataManager", "NoopMetadataManager", "create_metadata_manager", "get_metadata_manager"]