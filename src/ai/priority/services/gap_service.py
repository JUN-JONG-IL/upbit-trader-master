#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gap 탐지 통합 서비스 (v1.0)

책임:
- ML 모델 활성화 상태 확인 (MongoDB ml_model_settings)
- 활성화: AI/ML Gap 예측 (gap_predictor.py)
- 비활성화: Rule-based Gap 체크 (gap_detector.py)
- 통합 인터페이스 제공

변경 이력:
- v1.0: 초기 생성 - ML 활성화 상태에 따른 분기 로직
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
# 프로젝트 루트(src 폴더)를 sys.path 에 추가 (편의용)
# - 이 레포에서는 디렉토리 이름에 숫자가 포함되어 있어 정규 import 가
#   항상 동작하지 않을 수 있으므로, 파일 경로를 직접 로드하는 방식을 사용합니다.
# ---------------------------------------------------------------------
def _find_repo_src_dir(start_path: Optional[str] = None) -> Optional[str]:
    """
    현재 파일 위치에서 위로 올라가며 'src' 디렉토리를 찾습니다.
    찾으면 해당 절대 경로를 반환합니다.
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
    logger.debug("[GapService] src 경로를 sys.path에 추가: %s", _SRC_DIR)


# ---------------------------------------------------------------------
# 유틸: 파일 경로 후보에서 모듈 로드 및 심볼 추출
# ---------------------------------------------------------------------
def _load_symbol_from_paths(
    candidates: List[str],
    symbol_name: str,
    mod_name_hint: str,
) -> Optional[Any]:
    """
    파일 경로 후보 목록을 순회하며, 주어진 심볼(symbol_name)을 찾아 반환합니다.
    각 후보는 src 디렉토리(찾은 경우) 기준의 상대 경로(예: "data_01/workers/gap_detector.py")
    또는 절대 경로일 수 있습니다.
    """
    for p in candidates:
        # 절대 경로으로 변환
        if not os.path.isabs(p) and _SRC_DIR:
            path = os.path.join(_SRC_DIR, p)
        else:
            path = p

        if not os.path.isfile(path):
            logger.debug("[GapService] 후보 파일 없음: %s", path)
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"gapservice_{mod_name_hint}", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                sym = getattr(mod, symbol_name, None)
                if sym is not None:
                    logger.debug("[GapService] 로드 성공: %s -> %s", path, symbol_name)
                    return sym
                else:
                    logger.debug("[GapService] 심볼 미발견: %s in %s", symbol_name, path)
        except Exception as exc:
            logger.warning("[GapService] 모듈 로드 오류: %s (%s)", path, exc)
            continue
    return None


# ---------------------------------------------------------------------
# Rule-based gap detection 함수 탐색 (비동기 detect_gaps)
# 후보 파일들: 실제 레포리에 존재하는 경로들을 우선시함
# ---------------------------------------------------------------------
_RULE_BASED_SYMBOL = "detect_gaps"
_RULE_BASED_CANDIDATES = [
    "data_01/workers/gap_detector.py",
    "data_01/gap/gap_detector.py",
    "data_01/timescale/operations/gap_detector.py",
    "server/workers/gap_detector.py",
]

_rule_based_detect = _load_symbol_from_paths(_RULE_BASED_CANDIDATES, _RULE_BASED_SYMBOL, "rule")
_RULE_BASED_AVAILABLE = _rule_based_detect is not None
if not _RULE_BASED_AVAILABLE:
    logger.warning("[GapService] Rule-based gap detector 로드 실패 (후보들을 확인하세요)")


# ---------------------------------------------------------------------
# ML gap predictor 팩토리 탐색
# 후보: src/ai/priority/models/gap_predictor.py
# ---------------------------------------------------------------------
_ML_FACTORY_SYMBOL = "create_gap_predictor"
_ML_CANDIDATES = [
    "ai/priority/models/gap_predictor.py",
    "ai/priority/models/gap_predictor/__init__.py",
]

_create_gap_predictor = _load_symbol_from_paths(_ML_CANDIDATES, _ML_FACTORY_SYMBOL, "ml")
_ML_PREDICTOR_AVAILABLE = _create_gap_predictor is not None
if not _ML_PREDICTOR_AVAILABLE:
    logger.info("[GapService] ML gap_predictor 미발견 - ML 모드 사용 불가 (후보검사 필요)")


# ---------------------------------------------------------------------
# pymongo (설정 조회용)
# ---------------------------------------------------------------------
try:
    from pymongo import MongoClient  # type: ignore
    _PYMONGO_AVAILABLE = True
except Exception:
    MongoClient = None  # type: ignore
    _PYMONGO_AVAILABLE = False
    logger.info("[GapService] pymongo 미설치 - ML 설정 조회 비활성화")

_MONGO_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@localhost:27017")
_DB_NAME = os.getenv("MONGODB_DB", "upbit_trader")


# ---------------------------------------------------------------------
# GapDetectionService
# ---------------------------------------------------------------------
class GapDetectionService:
    """
    Gap 탐지 통합 서비스

    ML 모델 활성화 상태에 따라:
      - 활성화: AI/ML 기반 Gap 예측 (gap_predictor)
      - 비활성화: Rule-based Gap 체크 (gap_detector)
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
        Gap 탐지 (ML 활성화 상태에 따라 자동 분기)

        Returns:
            탐지된 Gap 목록
        """
        await self._load_ml_settings()

        if self._ml_enabled and _ML_PREDICTOR_AVAILABLE and _create_gap_predictor:
            logger.info("[GapService] AI/ML Gap 예측 모드")
            return await self._detect_with_ml(symbols, timeframes, max_gaps)
        else:
            logger.info("[GapService] Rule-based Gap 체크 모드")
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

    async def _load_ml_settings(self) -> None:
        """MongoDB에서 ML 설정 로드 (실패 시 ML 비활성화)"""
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
                logger.debug("[GapService] ML 설정 로드: enabled=%s model=%s", self._ml_enabled, self._ml_model_type)
                return
        except Exception as exc:
            logger.warning("[GapService] ML 설정 로드 실패: %s", exc)

        self._ml_enabled = False

    async def _detect_with_rules(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """Rule-based Gap 체크 (기존 로직)"""
        if not _RULE_BASED_AVAILABLE or _rule_based_detect is None:
            logger.error("[GapService] Rule-based gap detector 사용 불가")
            return []

        try:
            # 로드된 심볼이 코루틴 함수인지 확인
            if hasattr(_rule_based_detect, "__call__"):
                # _rule_based_detect는 async 함수인 경우가 많음 -> await
                try:
                    result = _rule_based_detect(symbols=symbols, timeframes=timeframes, max_gaps=max_gaps)
                    if hasattr(result, "__await__"):
                        return await result  # async coroutine
                    else:
                        # 동기 함수라면 그대로 반환
                        return result
                except TypeError:
                    # 호출 방식이 다르면 positional으로 시도
                    result = _rule_based_detect(symbols, timeframes, max_gaps)
                    if hasattr(result, "__await__"):
                        return await result
                    else:
                        return result
            return []
        except Exception as exc:
            logger.exception("[GapService] Rule-based Gap 체크 실패: %s", exc)
            return []

    async def _detect_with_ml(
        self,
        symbols: Optional[List[str]],
        timeframes: tuple,
        max_gaps: int,
    ) -> List[Dict[str, Any]]:
        """AI/ML 기반 Gap 예측 (플레이스홀더)"""
        if not _ML_PREDICTOR_AVAILABLE or _create_gap_predictor is None:
            logger.error("[GapService] ML gap_predictor 사용 불가 - Rule-based로 대체")
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        try:
            # predictor 인스턴스 준비
            if self._ml_predictor is None:
                # create_gap_predictor(factory) 호출 (동기)
                try:
                    self._ml_predictor = _create_gap_predictor(self._ml_model_type or "lightgbm")
                    logger.info("[GapService] ML 모델 인스턴스 생성: %s", self._ml_model_type)
                except Exception as exc:
                    logger.warning("[GapService] ML 모델 생성 실패: %s - Rule-based로 대체", exc)
                    return await self._detect_with_rules(symbols, timeframes, max_gaps)

            # TODO: 실제 예측 로직 구현 필요
            logger.warning("[GapService] ML Gap 예측 로직 미구현 - Rule-based로 대체")
            return await self._detect_with_rules(symbols, timeframes, max_gaps)

        except Exception as exc:
            logger.exception("[GapService] ML Gap 예측 실패: %s - Rule-based로 대체", exc)
            return await self._detect_with_rules(symbols, timeframes, max_gaps)


# 전역 서비스 인스턴스 (싱글톤)
_gap_service: Optional[GapDetectionService] = None


def get_gap_service(user_id: str = "default") -> GapDetectionService:
    """Gap 탐지 서비스 인스턴스 반환 (싱글톤)"""
    global _gap_service
    if _gap_service is None:
        _gap_service = GapDetectionService(user_id=user_id)
    return _gap_service


__all__ = ["GapDetectionService", "get_gap_service"]