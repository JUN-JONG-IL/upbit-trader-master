#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap ?먯? ?듯빀 ?쒕퉬??(v1.0)

梨낆엫:
- ML 紐⑤뜽 ?쒖꽦???곹깭 ?뺤씤 (MongoDB ml_model_settings)
- ?쒖꽦?? AI/ML Gap ?덉륫 (gap_predictor.py)
- 鍮꾪솢?깊솕: Rule-based Gap 泥댄겕 (gap_detector.py)
- ?듯빀 ?명꽣?섏씠???쒓났

蹂寃??대젰:
- v1.0: 珥덇린 ?앹꽦 - ML ?쒖꽦???곹깭???곕Ⅸ 遺꾧린 濡쒖쭅
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
# ?꾨줈?앺듃 猷⑦듃(src ?대뜑)瑜?sys.path ??異붽? (?몄쓽??
# - ???덊룷?먯꽌???붾젆?좊━ ?대쫫???レ옄媛 ?ы븿?섏뼱 ?덉뼱 ?뺢퇋 import 媛
#   ??긽 ?숈옉?섏? ?딆쓣 ???덉쑝誘濡? ?뚯씪 寃쎈줈瑜?吏곸젒 濡쒕뱶?섎뒗 諛⑹떇???ъ슜?⑸땲??
# ---------------------------------------------------------------------
def _find_repo_src_dir(start_path: Optional[str] = None) -> Optional[str]:
    """
    ?꾩옱 ?뚯씪 ?꾩튂?먯꽌 ?꾨줈 ?щ씪媛硫?'src' ?붾젆?좊━瑜?李얠뒿?덈떎.
    李얠쑝硫??대떦 ?덈? 寃쎈줈瑜?諛섑솚?⑸땲??
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
    logger.debug("[GapService] src 寃쎈줈瑜?sys.path??異붽?: %s", _SRC_DIR)


# ---------------------------------------------------------------------
# ?좏떥: ?뚯씪 寃쎈줈 ?꾨낫?먯꽌 紐⑤뱢 濡쒕뱶 諛??щ낵 異붿텧
# ---------------------------------------------------------------------
def _load_symbol_from_paths(
    candidates: List[str],
    symbol_name: str,
    mod_name_hint: str,
) -> Optional[Any]:
    """
    ?뚯씪 寃쎈줈 ?꾨낫 紐⑸줉???쒗쉶?섎ŉ, 二쇱뼱吏??щ낵(symbol_name)??李얠븘 諛섑솚?⑸땲??
    媛??꾨낫??src ?붾젆?좊━(李얠? 寃쎌슦) 湲곗????곷? 寃쎈줈(?? "data_01/workers/gap_detector.py")
    ?먮뒗 ?덈? 寃쎈줈?????덉뒿?덈떎.
    """
    for p in candidates:
        # ?덈? 寃쎈줈?쇰줈 蹂??
        if not os.path.isabs(p) and _SRC_DIR:
            path = os.path.join(_SRC_DIR, p)
        else:
            path = p

        if not os.path.isfile(path):
            logger.debug("[GapService] ?꾨낫 ?뚯씪 ?놁쓬: %s", path)
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"gapservice_{mod_name_hint}", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                sym = getattr(mod, symbol_name, None)
                if sym is not None:
                    logger.debug("[GapService] 濡쒕뱶 ?깃났: %s -> %s", path, symbol_name)
                    return sym
                else:
                    logger.debug("[GapService] ?щ낵 誘몃컻寃? %s in %s", symbol_name, path)
        except Exception as exc:
            logger.warning("[GapService] 紐⑤뱢 濡쒕뱶 ?ㅻ쪟: %s (%s)", path, exc)
            continue
    return None


# ---------------------------------------------------------------------
# Rule-based gap detection ?⑥닔 ?먯깋 (鍮꾨룞湲?detect_gaps)
# ?꾨낫 ?뚯씪?? ?ㅼ젣 ?덊룷由ъ뿉 議댁옱?섎뒗 寃쎈줈?ㅼ쓣 ?곗꽑?쒗븿
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
    logger.warning("[GapService] Rule-based gap detector 濡쒕뱶 ?ㅽ뙣 (?꾨낫?ㅼ쓣 ?뺤씤?섏꽭??")


# ---------------------------------------------------------------------
# ML gap predictor ?⑺넗由??먯깋
# ?꾨낫: src/06_ai/priority/models/gap_predictor.py
# ---------------------------------------------------------------------
_ML_FACTORY_SYMBOL = "create_gap_predictor"
_ML_CANDIDATES = [
    "06_ai/priority/models/gap_predictor.py",
    "06_ai/priority/models/gap_predictor/__init__.py",
]

_create_gap_predictor = _load_symbol_from_paths(_ML_CANDIDATES, _ML_FACTORY_SYMBOL, "ml")
_ML_PREDICTOR_AVAILABLE = _create_gap_predictor is not None
if not _ML_PREDICTOR_AVAILABLE:
    logger.info("[GapService] ML gap_predictor 誘몃컻寃?- ML 紐⑤뱶 ?ъ슜 遺덇? (?꾨낫寃???꾩슂)")


# ---------------------------------------------------------------------
# pymongo (?ㅼ젙 議고쉶??
# ---------------------------------------------------------------------
try:
    from pymongo import MongoClient  # type: ignore
    _PYMONGO_AVAILABLE = True
except Exception:
    MongoClient = None  # type: ignore
    _PYMONGO_AVAILABLE = False
    logger.info("[GapService] pymongo 誘몄꽕移?- ML ?ㅼ젙 議고쉶 鍮꾪솢?깊솕")

_MONGO_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@localhost:27017")
_DB_NAME = os.getenv("MONGODB_DB", "upbit_trader")


# ---------------------------------------------------------------------
# GapDetectionService
# ---------------------------------------------------------------------
class GapDetectionService:
    """
    Gap ?먯? ?듯빀 ?쒕퉬??

    ML 紐⑤뜽 ?쒖꽦???곹깭???곕씪:
      - ?쒖꽦?? AI/ML 湲곕컲 Gap ?덉륫 (gap_predictor)
      - 鍮꾪솢?깊솕: Rule-based Gap 泥댄겕 (gap_detector)
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
        Gap ?먯? (ML ?쒖꽦???곹깭???곕씪 ?먮룞 遺꾧린)

        Returns:
            ?먯???Gap 紐⑸줉
        """
        await self._load_ml_settings()

        if self._ml_enabled and _ML_PREDICTOR_AVAILABLE and _create_gap_predictor:
            logger.info("[GapService] AI/ML Gap ?덉륫 紐⑤뱶")
            return await self._detect_with_ml(symbols, timeframes, max_gaps)
        else:
            logger.info("[GapService] Rule-based Gap 泥댄겕 紐⑤뱶")
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

    async def _load_ml_settings(self) -> None:
        """MongoDB?먯꽌 ML ?ㅼ젙 濡쒕뱶 (?ㅽ뙣 ??ML 鍮꾪솢?깊솕)"""
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
                logger.debug("[GapService] ML ?ㅼ젙 濡쒕뱶: enabled=%s model=%s", self._ml_enabled, self._ml_model_type)
                return
        except Exception as exc:
            logger.warning("[GapService] ML ?ㅼ젙 濡쒕뱶 ?ㅽ뙣: %s", exc)

        self._ml_enabled = False

    async def _detect_with_rules(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """Rule-based Gap 泥댄겕 (湲곗〈 濡쒖쭅)"""
        if not _RULE_BASED_AVAILABLE or _rule_based_detect is None:
            logger.error("[GapService] Rule-based gap detector ?ъ슜 遺덇?")
            return []

        try:
            # 濡쒕뱶???щ낵??肄붾（???⑥닔?몄? ?뺤씤
            if hasattr(_rule_based_detect, "__call__"):
                # _rule_based_detect??async ?⑥닔??寃쎌슦媛 留롮쓬 -> await
                try:
                    result = _rule_based_detect(symbols=symbols, timeframes=timeframes, max_gaps=max_gaps)
                    if hasattr(result, "__await__"):
                        return await result  # async coroutine
                    else:
                        # ?숆린 ?⑥닔?쇰㈃ 洹몃?濡?諛섑솚
                        return result
                except TypeError:
                    # ?몄텧 諛⑹떇???ㅻⅤ硫?positional?쇰줈 ?쒕룄
                    result = _rule_based_detect(symbols, timeframes, max_gaps)
                    if hasattr(result, "__await__"):
                        return await result
                    else:
                        return result
            return []
        except Exception as exc:
            logger.exception("[GapService] Rule-based Gap 泥댄겕 ?ㅽ뙣: %s", exc)
            return []

    async def _detect_with_ml(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """AI/ML 湲곕컲 Gap ?덉륫 (?뚮젅?댁뒪???"""
        if not _ML_PREDICTOR_AVAILABLE or _create_gap_predictor is None:
            logger.error("[GapService] ML gap_predictor ?ъ슜 遺덇? - Rule-based濡??泥?)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        try:
            # predictor ?몄뒪?댁뒪 以鍮?
            if self._ml_predictor is None:
                # create_gap_predictor(factory) ?몄텧 (?숆린)
                try:
                    self._ml_predictor = _create_gap_predictor(self._ml_model_type or "lightgbm")
                    logger.info("[GapService] ML 紐⑤뜽 ?몄뒪?댁뒪 ?앹꽦: %s", self._ml_model_type)
                except Exception as exc:
                    logger.warning("[GapService] ML 紐⑤뜽 ?앹꽦 ?ㅽ뙣: %s - Rule-based濡??泥?, exc)
                    return await self._detect_with_rules(symbols, timeframes, max_gaps)

            # TODO: ?ㅼ젣 ?덉륫 濡쒖쭅 援ы쁽 ?꾩슂
            logger.warning("[GapService] ML Gap ?덉륫 濡쒖쭅 誘멸뎄??- Rule-based濡??泥?)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        except Exception as exc:
            logger.exception("[GapService] ML Gap ?덉륫 ?ㅽ뙣: %s - Rule-based濡??泥?, exc)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)


# ?꾩뿭 ?쒕퉬???몄뒪?댁뒪 (?깃???
_gap_service: Optional[GapDetectionService] = None


def get_gap_service(user_id: str = "default") -> GapDetectionService:
    """Gap ?먯? ?쒕퉬???몄뒪?댁뒪 諛섑솚 (?깃???"""
    global _gap_service
    if _gap_service is None:
        _gap_service = GapDetectionService(user_id=user_id)
    return _gap_service


__all__ = ["GapDetectionService", "get_gap_service"]
