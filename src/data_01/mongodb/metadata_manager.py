# -*- coding: utf-8 -*-
"""
MongoDB 硫뷀??곗씠??愿由ъ옄 (Metadata Manager)

紐⑹쟻:
    DB?ㅺ퀎.md 짠3 MongoDB ?ㅺ퀎???곕씪 ?щ낵 硫뷀??곗씠??而щ젆?섏쓣 愿由ы빀?덈떎.
    - metadata 而щ젆?? ?щ낵 ?뺣낫 (?쒓?紐? 嫄곕옒?? ?쒖꽦 ?щ? ??
    - priority_settings: ?곗씠???섏쭛 ?곗꽑?쒖쐞 ?ㅼ젙
    - user_favorites: 愿??醫낅ぉ
    - latest_snapshot: 媛?媛먯???理쒖떊 ?곹깭

蹂寃쎌궗???붿빟:
    - ?ъ슜?먮퀎 ?쒖떆 ??꾩〈 ???議고쉶 硫붿꽌??異붽? (get_user_timezone / set_user_timezone)
    - snapshot 媛깆떊 ??UTC ?쒖????곸슜
    - ?먯옄??理쒖떊?붿슜 update_snapshot_if_new 異붽? ($max ?곗궛 ?ъ슜)
    - create_metadata_manager(...) ?⑺넗由??뺤옣: ?ㅼ뼇???몄옄 ?대쫫 ?덉슜(db/mongo_db/mongo/data_manager/static ??,
      ?대??곸쑝濡?src.data_01.mongodb.init_mongodb.get_db()瑜??쒕룄???숆린 DB ?띾뱷??吏?먰븯?꾨줉 蹂닿컯.
    - pymongo/motor Database 媛앹껜??紐낆떆??None 寃???곸슜(遺덈┛ ?뚯뒪???쒓굅) ??NotImplementedError ?덈갑
    - event-loop 異⑸룎("attached to a different loop") 媛먯? ???덉쟾?섍쾶 ?숆린(pymongo) ?대갚 寃쎈줈 異붽?:
      get_snapshot, get_symbol, get_active_symbols ?깆뿉??motor ?덉쇅 諛쒖깮 ???숆린 議고쉶濡??ъ떆?꾪빀?덈떎.
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

# ?먮윭 濡쒓렇 ?띾룄 ?쒗븳 ?좏떥由ы떚 濡쒕뱶 (01_core ?붾젆?곕━紐낆씠 ?レ옄濡??쒖옉?섎?濡??뚯씪 湲곕컲 濡쒕뱶)
_log_error_throttled = None
try:
    _et_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "01_core", "utils", "error_throttler.py")
    )
    if os.path.isfile(_et_path):
        _et_spec = importlib.util.spec_from_file_location("_error_throttler_mm", _et_path)
        if _et_spec and _et_spec.loader:
            _et_mod = importlib.util.module_from_spec(_et_spec)
            _et_spec.loader.exec_module(_et_mod)
            _log_error_throttled = getattr(_et_mod, "log_error_throttled", None)
except Exception:
    pass

# RateLimitedErrorFilter ?대갚 (error_throttler 濡쒕뱶 ?ㅽ뙣 ??
_RateLimitedErrorFilter = None
try:
    _lc_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "01_core", "config", "logging_config.py")
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

# 而щ젆???대쫫
_COL_META = "metadata"
_COL_PRIORITY = "priority_settings"
_COL_FAVORITES = "user_favorites"
_COL_SNAPSHOT = "latest_snapshot"
_COL_STRATEGIES = "strategies"
_COL_ML_MODELS = "ml_models"

# 湲곕낯 ?쒖떆 ??꾩〈 (UI?먯꽌 蹂寃?媛??
_DEFAULT_DISPLAY_TZ = "Asia/Seoul"


# Event Loop ?ㅻ쪟 ?⑦꽩 紐⑸줉 (update_snapshot_if_new?먯꽌 ?숆린 fallback ?꾪솚 ???ъ슜)
_EVENT_LOOP_ERROR_KEYWORDS = (
    "event loop",
    "closed",
    "different event loop",
    "bound to a different",
    "attached to a different",
)


def _ensure_dt_utc(dt: datetime) -> datetime:
    """
    datetime??諛쏆븘 UTC timezone-aware datetime?쇰줈 諛섑솚.
    naive datetime?대㈃ tzinfo=UTC濡?吏?? ?ㅻⅨ tz硫?UTC濡?蹂??
    """
    if dt is None:
        raise ValueError("datetime 媛믪씠 ?꾩슂?⑸땲??")
    if not isinstance(dt, datetime):
        raise ValueError("datetime ?몄뒪?댁뒪媛 ?꾩슂?⑸땲??")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _should_fallback_to_sync(exc: Exception) -> bool:
    """
    諛쒖깮???덉쇅?먯꽌 'event loop 愿?? ?⑦꽩??蹂댁씠硫??숆린 ?대갚??沅뚯옣.
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
    """MongoDB 硫뷀??곗씠??而щ젆???듯빀 愿由ъ옄.

    紐⑤뱺 硫붿꽌?쒕뒗 motor (鍮꾨룞湲?MongoDB ?쒕씪?대쾭)瑜??ъ슜?⑸땲??
    DB ?곌껐??None?대㈃ 議곗옉 ?놁씠 鍮?媛믪쓣 諛섑솚?⑸땲??
    """

    def __init__(self, db) -> None:
        """
        Args:
            db: motor AsyncIOMotorDatabase ?몄뒪?댁뒪.
        """
        self._db = db

    # ------------------------------------------------------------------
    # metadata 而щ젆??(?щ낵 ?뺣낫)
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
        """?щ낵 硫뷀??곗씠?곕? upsert?⑸땲??"""
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
            # ?덉쇅 硫붿떆吏???곕씪 ?숆린 ?대갚 怨좊젮 (?낅뜲?댄듃??以묒슂?섎?濡??숆린 ?대갚 ?쒕룄?섏? ?딆쓬)
            logger.error("upsert_symbol ?ㅽ뙣 (%s): %s", symbol, exc)
            return False

    def update_symbol_metadata(self, symbol: str, metadata: Dict[str, Any]) -> bool:
        """?щ낵 硫뷀??곗씠?곕? ?숆린 諛⑹떇?쇰줈 ?낅뜲?댄듃?⑸땲??(UI ?ㅻ젅??PyQt5 ?덉쟾)."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] ?숆린 MongoDB ?곌껐 ?놁쓬 ??硫뷀??곗씠???낅뜲?댄듃 嫄대꼫?")
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
            logger.error("[MetadataManager] 硫뷀??곗씠???낅뜲?댄듃 ?ㅽ뙣 (%s): %s", symbol, exc)
            return False

    async def get_symbol(self, symbol: str, exchange: str = "upbit") -> Optional[Dict[str, Any]]:
        """?⑥씪 ?щ낵 硫뷀??곗씠?곕? 議고쉶?⑸땲??"""
        if self._db is None:
            return None
        try:
            doc = await self._db[_COL_META].find_one(
                {"symbol": symbol, "exchange": exchange},
                {"_id": 0},
            )
            return doc
        except Exception as exc:
            # ?대깽??猷⑦봽 愿???덉쇅 媛먯? ???숆린 ?대갚
            if _should_fallback_to_sync(exc):
                try:
                    # ?숆린 議고쉶 ?쒕룄
                    return self._sync_get_symbol(symbol, exchange)
                except Exception:
                    logger.debug("[MetadataManager] ?숆린 get_symbol ?대갚 ?ㅽ뙣: %s", exc)
            logger.error("get_symbol ?ㅽ뙣 (%s): %s", symbol, exc)
            return None

    def _sync_get_symbol(self, symbol: str, exchange: str = "upbit") -> Optional[Dict[str, Any]]:
        """?숆린 pymongo瑜??듯븳 get_symbol ?대갚."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] ?숆린 MongoDB ?곌껐 ?놁쓬 ??get_symbol 嫄대꼫?")
                return None
            doc = connector.db[_COL_META].find_one({"symbol": symbol, "exchange": exchange}, {"_id": 0})
            return doc
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_symbol ?ㅽ뙣 (%s): %s", symbol, exc)
            return None

    async def get_active_symbols(
        self,
        exchange: str = "upbit",
        limit: int = 10_000,
    ) -> List[str]:
        """?쒖꽦 ?щ낵 紐⑸줉??諛섑솚?⑸땲??"""
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
                    logger.debug("[MetadataManager] ?숆린 get_active_symbols ?대갚 ?ㅽ뙣: %s", exc)
            logger.error("get_active_symbols ?ㅽ뙣: %s", exc)
            return []

    def _sync_get_active_symbols(self, exchange: str = "upbit", limit: int = 10_000) -> List[str]:
        """?숆린 pymongo瑜??듯븳 get_active_symbols ?대갚."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] ?숆린 MongoDB ?곌껐 ?놁쓬 ??get_active_symbols 嫄대꼫?")
                return []
            cursor = connector.db[_COL_META].find({"exchange": exchange, "is_active": True}, {"symbol": 1, "_id": 0}).limit(limit)
            return [d["symbol"] for d in cursor]
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_active_symbols ?ㅽ뙣: %s", exc)
            return []

    async def deactivate_symbol(self, symbol: str, exchange: str = "upbit") -> bool:
        """?щ낵??鍮꾪솢?깊솕?⑸땲??"""
        if self._db is None:
            return False
        try:
            await self._db[_COL_META].update_one(
                {"symbol": symbol, "exchange": exchange},
                {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
            )
            return True
        except Exception as exc:
            logger.error("deactivate_symbol ?ㅽ뙣 (%s): %s", symbol, exc)
            return False

    # ------------------------------------------------------------------
    # latest_snapshot 而щ젆??(Gap Detection??
    # ------------------------------------------------------------------

    async def update_snapshot(
        self,
        symbol: str,
        timeframe: str,
        last_candle_time: datetime,
    ) -> bool:
        """媛?媛먯???理쒖떊 ?ㅻ깄?룹쓣 媛깆떊?⑸땲?? (?⑥닚 ??뼱?곌린)"""
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
            logger.error("update_snapshot ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return False

    async def update_snapshot_if_new(
        self,
        symbol: str,
        timeframe: str,
        candidate_time: datetime,
    ) -> bool:
        """
        candidate_time??湲곗〈 last_candle_time蹂대떎 理쒖떊??寃쎌슦?먮쭔 媛깆떊?⑸땲??
        ?숈떆???곹솴?먯꽌 ?덉쟾?섍쾶 理쒖떊 媛믩쭔 蹂댁〈?섎젮硫???硫붿꽌?쒕? ?ъ슜?섏꽭??
        MongoDB??$max ?곗궛?먮? ?ъ슜?섏뿬 ?먯옄?곸쑝濡?理쒖떊媛믪쓣 ?좎??⑸땲??
        Event Loop ?ㅻ쪟 媛먯? ???숆린 諛⑹떇?쇰줈 ?먮룞 ?꾪솚?⑸땲??
        PyQt5 硫붿씤 ?ㅻ젅????鍮꾨룞湲?而⑦뀓?ㅽ듃 諛뽰뿉???몄텧 ??利됱떆 ?숆린 諛⑹떇?쇰줈 泥섎━?⑸땲??
        """
        # Event Loop ?곹깭 ?좎젣 ?뺤씤: ?ㅽ뻾 以묒씤 猷⑦봽媛 ?놁쑝硫??숆린 諛⑹떇?쇰줈 泥섎━
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None or not loop.is_running():
            return self._sync_update_snapshot_if_new(symbol, timeframe, candidate_time)

        if self._db is None:
            # DB媛 ?놁쑝硫??숆린 諛⑹떇?쇰줈 ?꾪솚 ?쒕룄
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
                logger.debug("[MetadataManager] Event Loop ?ㅻ쪟 媛먯?, ?숆린 諛⑹떇?쇰줈 ?꾪솚: %s", exc)
                return self._sync_update_snapshot_if_new(symbol, timeframe, candidate_time)
            if _log_error_throttled is not None:
                _log_error_throttled(logger, "update_snapshot_if_new_failed",
                                     f"update_snapshot_if_new ?ㅽ뙣 ({symbol}/{timeframe}): {exc}")
            else:
                logger.error("update_snapshot_if_new ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return False

    def _sync_update_snapshot_if_new(
        self,
        symbol: str,
        timeframe: str,
        candidate_time: datetime,
    ) -> bool:
        """
        ?숆린 諛⑹떇?쇰줈 理쒖떊 ?ㅻ깄??媛깆떊 (pymongo ?ъ슜, Event Loop ?놁씠 ?몄텧 媛??.
        MongoConnector ?깃??ㅼ쓣 ?듯빐 ?숆린 pymongo ?곌껐???ъ궗?⑺빀?덈떎.
        """
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] ?숆린 MongoDB ?곌껐 ?놁쓬 ???ㅻ깄??媛깆떊 嫄대꼫?")
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
            logger.debug("[MetadataManager] ?숆린 ?ㅻ깄??媛깆떊: %s/%s", symbol, timeframe)
            return True
        except Exception as exc:
            logger.error("[MetadataManager] ?숆린 ?ㅻ깄??媛깆떊 ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return False

    async def get_snapshot(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[datetime]:
        """理쒖떊 ?ㅻ깄???쒓컖??諛섑솚?⑸땲??(UTC-aware datetime)."""
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
                logger.warning("get_snapshot: last_candle_time ?뚯떛 ?ㅽ뙣, raw=%s", ts)
                return None
        except Exception as exc:
            # ?대깽??猷⑦봽 異⑸룎 ??motor 愿???먮윭 媛먯? ???숆린 ?대갚
            if _should_fallback_to_sync(exc):
                try:
                    return self._sync_get_snapshot(symbol, timeframe)
                except Exception:
                    logger.debug("[MetadataManager] ?숆린 get_snapshot ?대갚 ?ㅽ뙣: %s", exc)
            if "event loop is closed" in str(exc).lower():
                logger.debug("get_snapshot: event loop closed, returning None (%s/%s)", symbol, timeframe)
                return None
            if _log_error_throttled is not None:
                _log_error_throttled(logger, "get_snapshot_failed",
                                     f"get_snapshot ?ㅽ뙣 ({symbol}/{timeframe}): {exc}")
            else:
                logger.error("get_snapshot ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return None

    def _sync_get_snapshot(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """?숆린 pymongo瑜??듯븳 get_snapshot ?대갚."""
        try:
            from .mongo_db import MongoConnector
            connector = MongoConnector()
            if connector.db is None:
                connector.connect()
            if connector.db is None:
                logger.warning("[MetadataManager] ?숆린 MongoDB ?곌껐 ?놁쓬 ??get_snapshot 嫄대꼫?")
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
                logger.warning("[MetadataManager] _sync_get_snapshot last_candle_time ?뚯떛 ?ㅽ뙣, raw=%s", ts)
                return None
        except Exception as exc:
            logger.error("[MetadataManager] _sync_get_snapshot ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------
    # ?덉쟾沅?吏꾪뻾瑜?(Phase 4 ??TF Progress Widget ?곗씠???뚯뒪)
    # ------------------------------------------------------------------

    # TF蹂?1罹붾뱾 湲몄씠(珥?
    _TF_SECONDS = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "1d": 86400,
    }

    # TF蹂?'SAFE' ?먯젙 ?좎꽑???꾧퀎 (諛곗닔). 留덉?留?罹붾뱾??N횞TF ?대궡硫?SAFE.
    _SAFE_FRESHNESS_FACTOR = 3

    async def compute_safe_zone_pct(
        self,
        symbol: str,
        timeframe: str,
        target_candles: int = 1000,
    ) -> Dict[str, Any]:
        """??꾪봽?덉엫蹂?'?덉쟾沅? 吏꾪뻾瑜좎쓣 怨꾩궛??諛섑솚?쒕떎."""
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
            logger.debug("compute_safe_zone_pct ?ㅽ뙣 (%s/%s): %s", symbol, timeframe, exc)
            return result

    # ------------------------------------------------------------------
    # priority_settings 而щ젆??
    # ------------------------------------------------------------------

    async def get_priority_settings(self, user_id: str = "default") -> Optional[Dict[str, Any]]:
        """?곗꽑?쒖쐞 ?ㅼ젙??議고쉶?⑸땲??"""
        if self._db is None:
            return None
        try:
            doc = await self._db[_COL_PRIORITY].find_one({"user_id": user_id}, {"_id": 0})
            return doc
        except Exception as exc:
            logger.error("get_priority_settings ?ㅽ뙣: %s", exc)
            return None

    async def set_priority_settings(
        self,
        settings: Dict[str, Any],
        user_id: str = "default",
    ) -> bool:
        """?곗꽑?쒖쐞 ?ㅼ젙????ν빀?덈떎."""
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
            logger.error("set_priority_settings ?ㅽ뙣: %s", exc)
            return False

    # ------------------------------------------------------------------
    # ?ъ슜????꾩〈 ?ㅼ젙 (UI?먯꽌 ?좏깮 媛??
    # ------------------------------------------------------------------

    async def get_user_timezone(self, user_id: str = "default") -> str:
        """
        ?ъ슜?먮퀎 ?쒖떆 ??꾩〈??諛섑솚?⑸땲??
        - DB???ㅼ젙???놁쑝硫?湲곕낯媛?_DEFAULT_DISPLAY_TZ 諛섑솚.
        """
        if self._db is None:
            return _DEFAULT_DISPLAY_TZ
        try:
            doc = await self._db[_COL_PRIORITY].find_one({"user_id": user_id}, {"timezone": 1, "_id": 0})
            if doc and "timezone" in doc and doc["timezone"]:
                return doc["timezone"]
            return _DEFAULT_DISPLAY_TZ
        except Exception as exc:
            logger.error("get_user_timezone ?ㅽ뙣: %s", exc)
            return _DEFAULT_DISPLAY_TZ

    async def set_user_timezone(self, tz_name: str, user_id: str = "default") -> bool:
        """
        ?ъ슜?먮퀎 ?쒖떆 ??꾩〈????ν빀?덈떎. (?? 'Asia/Seoul', 'UTC')
        UI?먯꽌 蹂寃??붿껌??諛쏆쑝硫???硫붿꽌?쒕? ?몄텧?섏꽭??
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
            logger.error("set_user_timezone ?ㅽ뙣: %s", exc)
            return False

    # ------------------------------------------------------------------
    # user_favorites 而щ젆??
    # ------------------------------------------------------------------

    async def get_favorites(self, user_id: str = "default") -> List[str]:
        """愿??醫낅ぉ 紐⑸줉??諛섑솚?⑸땲??"""
        if self._db is None:
            return []
        try:
            doc = await self._db[_COL_FAVORITES].find_one({"user_id": user_id}, {"symbols": 1})
            return doc.get("symbols", []) if doc else []
        except Exception as exc:
            logger.error("get_favorites ?ㅽ뙣: %s", exc)
            return []

    async def set_favorites(self, symbols: List[str], user_id: str = "default") -> bool:
        """愿??醫낅ぉ 紐⑸줉????ν빀?덈떎."""
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
            logger.error("set_favorites ?ㅽ뙣: %s", exc)
            return False


# -------------------------------------------------------------------------
# Noop ?泥댁옄: DB 誘몄〈???뚯뒪???섍꼍?먯꽌 ?덉쟾?섍쾶 ?ъ슜 媛??
# -------------------------------------------------------------------------
class NoopMetadataManager:
    """?곗씠?곕쿋?댁뒪媛 ?놁쓣 ???ъ슜?섎뒗 Noop 援ы쁽 ???숈씪??鍮꾨룞湲?API瑜??쒓났."""

    def __init__(self, *args, **kwargs):
        # DB ?놁쓬
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
        """?숆린 諛⑹떇 ?ㅻ깄??媛깆떊 ??Noop 援ы쁽"""
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
# 紐⑤뱢 ?⑺넗由? loader/?몃? 肄붾뱶媛 ?쇨???諛⑹떇?쇰줈 ?몄뒪?댁뒪 ?삳룄濡???
# -------------------------------------------------------------------------
def _try_get_db_via_init_module() -> Optional[Any]:
    """
    媛?ν븳 init_mongodb 紐⑤뱢??李얠븘 get_db()瑜??몄텧???숆린 DB瑜??살뼱 諛섑솚.
    ?ㅽ뙣?섎㈃ None.
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
    # ?뚯씪-level fallback: attempt loading by path relative to this file
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
    蹂대떎 踰붿슜?곸쑝濡?MetadataManager ?몄뒪?댁뒪瑜??앹꽦?⑸땲??

    ?덉슜?섎뒗 ?몄옄(?곗꽑?쒖쐞):
      - db, mongo_db, mongo, database (DB 媛앹껜 吏곸젒)
      - data_manager (媛앹껜) -> data_manager.db ?먮뒗 data_manager.mongo ?깆쓣 ?쒕룄
      - static (遺?몄뒪?몃옪??static 紐⑤뱢) -> static.data_manager ?깆뿉??DB瑜?異붿텧

    ??紐⑤뱺 諛⑸쾿?쇰줈 DB瑜??살? 紐삵븯硫??대??곸쑝濡?init_mongodb.get_db()瑜??쒕룄?⑸땲??
    理쒖쥌?곸쑝濡?DB瑜??살? 紐삵븯硫?NoopMetadataManager瑜?諛섑솚?⑸땲??
    """
    db = None

    # 1) positional first arg (醫낆쥌 db瑜?吏곸젒 ?꾨떖?섎뒗 寃쎌슦)
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
                    smod = importlib.import_module("src.11_server.app.static.static")
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

    logger.info("[metadata_manager] No DB available ??returning NoopMetadataManager")
    return NoopMetadataManager()


# backward-compat convenience name
get_metadata_manager = create_metadata_manager

__all__ = ["MetadataManager", "NoopMetadataManager", "create_metadata_manager", "get_metadata_manager"]
