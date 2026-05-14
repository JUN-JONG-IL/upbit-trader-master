#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap ?ì? ?µí•© ?œë¹„??(v1.0)

ì±…ì„:
- ML ëª¨ë¸ ?œì„±???íƒœ ?•ì¸ (MongoDB ml_model_settings)
- ?œì„±?? AI/ML Gap ?ˆì¸¡ (gap_predictor.py)
- ë¹„í™œ?±í™”: Rule-based Gap ì²´í¬ (gap_detector.py)
- ?µí•© ?¸í„°?˜ì´???œê³µ

ë³€ê²??´ë ¥:
- v1.0: ì´ˆê¸° ?ì„± - ML ?œì„±???íƒœ???°ë¥¸ ë¶„ê¸° ë¡œì§
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from types import ModuleType
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# ?„ë¡œ?íŠ¸ ë£¨íŠ¸(src ?´ë”)ë¥?sys.path ??ì¶”ê? (?¸ì˜??
# - ???ˆí¬?ì„œ???”ë ‰? ë¦¬ ?´ë¦„???«ìê°€ ?¬í•¨?˜ì–´ ?ˆì–´ ?•ê·œ import ê°€
#   ??ƒ ?™ì‘?˜ì? ?Šì„ ???ˆìœ¼ë¯€ë¡? ?Œì¼ ê²½ë¡œë¥?ì§ì ‘ ë¡œë“œ?˜ëŠ” ë°©ì‹???¬ìš©?©ë‹ˆ??
# ---------------------------------------------------------------------
def _find_repo_src_dir(start_path: Optional[str] = None) -> Optional[str]:
    """
    ?„ì¬ ?Œì¼ ?„ì¹˜?ì„œ ?„ë¡œ ?¬ë¼ê°€ë©?'src' ?”ë ‰? ë¦¬ë¥?ì°¾ìŠµ?ˆë‹¤.
    ì°¾ìœ¼ë©??´ë‹¹ ?ˆë? ê²½ë¡œë¥?ë°˜í™˜?©ë‹ˆ??
    """
    path = os.path.abspath(start_path or os.path.dirname(__file__))
    for _ in range(8):
        candidate = os.path.join(path, "src")
        if os.path.isdir(candidate):
            return candidate
        path = os.path.dirname(path)
    return None


_SRC_DIR = _find_repo_src_dir()
if _SRC_DIR and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
    logger.debug("[GapService] src ê²½ë¡œë¥?sys.path??ì¶”ê?: %s", _SRC_DIR)


# ---------------------------------------------------------------------
# ? í‹¸: ?Œì¼ ê²½ë¡œ ?„ë³´?ì„œ ëª¨ë“ˆ ë¡œë“œ ë°??¬ë³¼ ì¶”ì¶œ
# ---------------------------------------------------------------------
def _load_symbol_from_paths(
    candidates: List[str],
    symbol_name: str,
    mod_name_hint: str,
) -> Optional[Any]:
    """
    ?Œì¼ ê²½ë¡œ ?„ë³´ ëª©ë¡???œíšŒ?˜ë©°, ì£¼ì–´ì§??¬ë³¼(symbol_name)??ì°¾ì•„ ë°˜í™˜?©ë‹ˆ??
    ê°??„ë³´??src ?”ë ‰? ë¦¬(ì°¾ì? ê²½ìš°) ê¸°ì????ë? ê²½ë¡œ(?? "data_01/workers/gap_detector.py")
    ?ëŠ” ?ˆë? ê²½ë¡œ?????ˆìŠµ?ˆë‹¤.
    """
    for p in candidates:
        # ?ˆë? ê²½ë¡œ?¼ë¡œ ë³€??
        if not os.path.isabs(p) and _SRC_DIR:
            path = os.path.join(_SRC_DIR, p)
        else:
            path = p

        if not os.path.isfile(path):
            logger.debug("[GapService] ?„ë³´ ?Œì¼ ?†ìŒ: %s", path)
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"gapservice_{mod_name_hint}", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                sym = getattr(mod, symbol_name, None)
                if sym is not None:
                    logger.debug("[GapService] ë¡œë“œ ?±ê³µ: %s -> %s", path, symbol_name)
                    return sym
                else:
                    logger.debug("[GapService] ?¬ë³¼ ë¯¸ë°œê²? %s in %s", symbol_name, path)
        except Exception as exc:
            logger.warning("[GapService] ëª¨ë“ˆ ë¡œë“œ ?¤ë¥˜: %s (%s)", path, exc)
            continue
    return None


# ---------------------------------------------------------------------
# Rule-based gap detection ?¨ìˆ˜ ?ìƒ‰ (ë¹„ë™ê¸?detect_gaps)
# ?„ë³´ ?Œì¼?? ?¤ì œ ?ˆí¬ë¦¬ì— ì¡´ì¬?˜ëŠ” ê²½ë¡œ?¤ì„ ?°ì„ ?œí•¨
# ---------------------------------------------------------------------
_RULE_BASED_SYMBOL = "detect_gaps"
_RULE_BASED_CANDIDATES = [
    "data_01/workers/gap_detector.py",
    "data_01/gap/gap_detector.py",
    "data_01/timescale/operations/gap_detector.py",
    "11_server/workers/gap_detector.py",
]

_rule_based_detect = _load_symbol_from_paths(_RULE_BASED_CANDIDATES, _RULE_BASED_SYMBOL, "rule")
_RULE_BASED_AVAILABLE = _rule_based_detect is not None
if not _RULE_BASED_AVAILABLE:
    logger.warning("[GapService] Rule-based gap detector ë¡œë“œ ?¤íŒ¨ (?„ë³´?¤ì„ ?•ì¸?˜ì„¸??")


# ---------------------------------------------------------------------
# ML gap predictor ?©í† ë¦??ìƒ‰
# ?„ë³´: src/06_ai/priority/models/gap_predictor.py
# ---------------------------------------------------------------------
_ML_FACTORY_SYMBOL = "create_gap_predictor"
_ML_CANDIDATES = [
    "06_ai/priority/models/gap_predictor.py",
    "06_ai/priority/models/gap_predictor/__init__.py",
]

_create_gap_predictor = _load_symbol_from_paths(_ML_CANDIDATES, _ML_FACTORY_SYMBOL, "ml")
_ML_PREDICTOR_AVAILABLE = _create_gap_predictor is not None
if not _ML_PREDICTOR_AVAILABLE:
    logger.info("[GapService] ML gap_predictor ë¯¸ë°œê²?- ML ëª¨ë“œ ?¬ìš© ë¶ˆê? (?„ë³´ê²€???„ìš”)")


# ---------------------------------------------------------------------
# pymongo (?¤ì • ì¡°íšŒ??
# ---------------------------------------------------------------------
try:
    from pymongo import MongoClient  # type: ignore
    _PYMONGO_AVAILABLE = True
except Exception:
    MongoClient = None  # type: ignore
    _PYMONGO_AVAILABLE = False
    logger.info("[GapService] pymongo ë¯¸ì„¤ì¹?- ML ?¤ì • ì¡°íšŒ ë¹„í™œ?±í™”")

_MONGO_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@localhost:27017")
_DB_NAME = os.getenv("MONGODB_DB", "upbit_trader")


# ---------------------------------------------------------------------
# GapDetectionService
# ---------------------------------------------------------------------
class GapDetectionService:
    """
    Gap ?ì? ?µí•© ?œë¹„??

    ML ëª¨ë¸ ?œì„±???íƒœ???°ë¼:
      - ?œì„±?? AI/ML ê¸°ë°˜ Gap ?ˆì¸¡ (gap_predictor)
      - ë¹„í™œ?±í™”: Rule-based Gap ì²´í¬ (gap_detector)
    """

    def __init__(self, user_id: str = "default") -> None:
        self.user_id = user_id
        self._ml_enabled: Optional[bool] = None
        self._ml_model_type: Optional[str] = None
        self._ml_predictor: Optional[Any] = None

    async def detect_gaps(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: tuple = ("1m", "5m", "15m"),
        max_gaps: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Gap ?ì? (ML ?œì„±???íƒœ???°ë¼ ?ë™ ë¶„ê¸°)

        Returns:
            ?ì???Gap ëª©ë¡
        """
        await self._load_ml_settings()

        if self._ml_enabled and _ML_PREDICTOR_AVAILABLE and _create_gap_predictor:
            logger.info("[GapService] AI/ML Gap ?ˆì¸¡ ëª¨ë“œ")
            return await self._detect_with_ml(symbols, timeframes, max_gaps)
        else:
            logger.info("[GapService] Rule-based Gap ì²´í¬ ëª¨ë“œ")
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

    async def _load_ml_settings(self) -> None:
        """MongoDB?ì„œ ML ?¤ì • ë¡œë“œ (?¤íŒ¨ ??ML ë¹„í™œ?±í™”)"""
        if not _PYMONGO_AVAILABLE or MongoClient is None:
            self._ml_enabled = False
            return

        try:
            client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
            db = client[_DB_NAME]
            settings = db.ml_model_settings.find_one({"user_id": self.user_id})
            if settings:
                self._ml_enabled = bool(settings.get("gap_model_enabled", False))
                self._ml_model_type = settings.get("gap_model_type", "lightgbm")
                logger.debug("[GapService] ML ?¤ì • ë¡œë“œ: enabled=%s model=%s", self._ml_enabled, self._ml_model_type)
                return
        except Exception as exc:
            logger.warning("[GapService] ML ?¤ì • ë¡œë“œ ?¤íŒ¨: %s", exc)

        self._ml_enabled = False

    async def _detect_with_rules(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """Rule-based Gap ì²´í¬ (ê¸°ì¡´ ë¡œì§)"""
        if not _RULE_BASED_AVAILABLE or _rule_based_detect is None:
            logger.error("[GapService] Rule-based gap detector ?¬ìš© ë¶ˆê?")
            return []

        try:
            # ë¡œë“œ???¬ë³¼??ì½”ë£¨???¨ìˆ˜?¸ì? ?•ì¸
            if hasattr(_rule_based_detect, "__call__"):
                # _rule_based_detect??async ?¨ìˆ˜??ê²½ìš°ê°€ ë§ìŒ -> await
                try:
                    result = _rule_based_detect(symbols=symbols, timeframes=timeframes, max_gaps=max_gaps)
                    if hasattr(result, "__await__"):
                        return await result  # async coroutine
                    else:
                        # ?™ê¸° ?¨ìˆ˜?¼ë©´ ê·¸ë?ë¡?ë°˜í™˜
                        return result
                except TypeError:
                    # ?¸ì¶œ ë°©ì‹???¤ë¥´ë©?positional?¼ë¡œ ?œë„
                    result = _rule_based_detect(symbols, timeframes, max_gaps)
                    if hasattr(result, "__await__"):
                        return await result
                    else:
                        return result
            return []
        except Exception as exc:
            logger.exception("[GapService] Rule-based Gap ì²´í¬ ?¤íŒ¨: %s", exc)
            return []

    async def _detect_with_ml(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """AI/ML ê¸°ë°˜ Gap ?ˆì¸¡ (?Œë ˆ?´ìŠ¤?€??"""
        if not _ML_PREDICTOR_AVAILABLE or _create_gap_predictor is None:
            logger.error("[GapService] ML gap_predictor ?¬ìš© ë¶ˆê? - Rule-basedë¡??€ì²?)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        try:
            # predictor ?¸ìŠ¤?´ìŠ¤ ì¤€ë¹?
            if self._ml_predictor is None:
                # create_gap_predictor(factory) ?¸ì¶œ (?™ê¸°)
                try:
                    self._ml_predictor = _create_gap_predictor(self._ml_model_type or "lightgbm")
                    logger.info("[GapService] ML ëª¨ë¸ ?¸ìŠ¤?´ìŠ¤ ?ì„±: %s", self._ml_model_type)
                except Exception as exc:
                    logger.warning("[GapService] ML ëª¨ë¸ ?ì„± ?¤íŒ¨: %s - Rule-basedë¡??€ì²?, exc)
                    return await self._detect_with_rules(symbols, timeframes, max_gaps)

            # TODO: ?¤ì œ ?ˆì¸¡ ë¡œì§ êµ¬í˜„ ?„ìš”
            logger.warning("[GapService] ML Gap ?ˆì¸¡ ë¡œì§ ë¯¸êµ¬??- Rule-basedë¡??€ì²?)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        except Exception as exc:
            logger.exception("[GapService] ML Gap ?ˆì¸¡ ?¤íŒ¨: %s - Rule-basedë¡??€ì²?, exc)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)


# ?„ì—­ ?œë¹„???¸ìŠ¤?´ìŠ¤ (?±ê???
_gap_service: Optional[GapDetectionService] = None


def get_gap_service(user_id: str = "default") -> GapDetectionService:
    """Gap ?ì? ?œë¹„???¸ìŠ¤?´ìŠ¤ ë°˜í™˜ (?±ê???"""
    global _gap_service
    if _gap_service is None:
        _gap_service = GapDetectionService(user_id=user_id)
    return _gap_service


__all__ = ["GapDetectionService", "get_gap_service"]
