# -*- coding: utf-8 -*-
"""
static 모듈 탐색, RealtimeManager / AutoBackfillManager 검색 (v1.0)

sys.modules 기반으로 서버 static 모듈을 찾고,
그 안에서 RealtimeManager / AutoBackfillManager 인스턴스를 반환합니다.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Optional

from .constants import STATIC_MODULE_KEYS

logger = logging.getLogger(__name__)


def _find_static_module() -> Optional[Any]:
    """sys.modules에서 static 모듈 찾기 (없으면 importlib으로 시도).

    Returns:
        발견된 static 모듈 객체 또는 None
    """
    logger.debug("[UI Utils] === sys.modules static 관련 모듈 검색 시작 ===")
    static_modules = [key for key in sys.modules.keys() if "static" in key.lower()]
    logger.debug("[UI Utils] sys.modules에 등록된 static 관련 모듈: %s", static_modules)

    for _key in STATIC_MODULE_KEYS:
        _mod = sys.modules.get(_key)
        if _mod is not None:
            logger.info(
                "[UI Utils] ✅ static 모듈 발견: %s (파일: %s)",
                _key,
                getattr(_mod, "__file__", "unknown"),
            )
            return _mod
        else:
            logger.debug("[UI Utils] static 모듈 없음: %s", _key)

    logger.warning("[UI Utils] ⚠️ sys.modules에서 static 모듈 못 찾음 - importlib 시도")
    try:
        import importlib

        for _mod_path in ("src._11_server.app.static", "static", "app.static"):
            try:
                mod = importlib.import_module(_mod_path)
                logger.info("[UI Utils] ✅ static 모듈 import 성공: %s", _mod_path)
                return mod
            except Exception as e:
                logger.debug("[UI Utils] import 실패: %s (%s)", _mod_path, e)
    except Exception as e:
        logger.warning("[UI Utils] importlib 시도 실패: %s", e)

    logger.warning("[UI Utils] ⚠️ static 모듈을 찾을 수 없습니다")
    return None


def get_realtime_manager() -> Optional[Any]:
    """RealtimeManager 전역 인스턴스 가져오기 (완전한 폴백 체인).

    Returns:
        RealtimeManager 인스턴스 또는 None
    """
    _static = _find_static_module()
    if _static is None:
        logger.warning("[UI Utils] ⚠️ static 모듈을 찾을 수 없습니다")
        return None

    logger.debug(
        "[UI Utils] === RealtimeManager 검색 시작: %s ===",
        getattr(_static, "__name__", "unknown"),
    )

    # 1단계: 표준 속성 검색
    for attr_name in ("realtime_manager", "rt_manager", "manager", "chart"):
        try:
            mgr = getattr(_static, attr_name, None)
            if mgr is not None:
                type_name = type(mgr).__name__
                logger.debug("[UI Utils] 속성 발견: static.%s = %s", attr_name, type_name)

                if (
                    "RealtimeManager" in type_name
                    or "RTManager" in type_name
                    or hasattr(mgr, "active_symbols")
                    or hasattr(mgr, "codes")
                ):
                    logger.info(
                        "[UI Utils] ✅ RealtimeManager found: static.%s (%s)",
                        attr_name,
                        type_name,
                    )
                    return mgr
        except Exception as e:
            logger.debug("[UI Utils] Error checking static.%s: %s", attr_name, e)

    # 2단계: 모듈 전체 스캔
    logger.debug("[UI Utils] ⚠️ 표준 속성에서 못 찾음 - 모듈 전체 스캔 시작")
    for attr_name in dir(_static):
        if attr_name.startswith("_"):
            continue
        try:
            attr_val = getattr(_static, attr_name, None)
            if attr_val is None:
                continue

            type_name = type(attr_val).__name__

            if type_name == "Config":
                continue

            if "RealtimeManager" in type_name or "RTManager" in type_name:
                logger.info(
                    "[UI Utils] ✅ RealtimeManager found (scan): static.%s (%s)",
                    attr_name,
                    type_name,
                )
                return attr_val

            if hasattr(attr_val, "codes") and hasattr(attr_val, "coins"):
                logger.info(
                    "[UI Utils] ✅ RealtimeManager found (attributes): static.%s (%s)",
                    attr_name,
                    type_name,
                )
                return attr_val
        except Exception as e:
            logger.debug("[UI Utils] Error scanning attribute %s: %s", attr_name, e)

    # 3단계: 다른 static 모듈 검색
    logger.debug("[UI Utils] ⚠️ 현재 static 모듈에서 실패 - 다른 static 모듈 검색 시작")
    for _key in STATIC_MODULE_KEYS:
        _other = sys.modules.get(_key)
        if _other is None or _other is _static:
            continue

        logger.debug("[UI Utils] 다른 static 모듈 검색: %s", _key)

        for attr_name in ("realtime_manager", "rt_manager", "manager", "chart"):
            try:
                mgr = getattr(_other, attr_name, None)
                if mgr is None:
                    continue

                type_name = type(mgr).__name__
                if (
                    "RealtimeManager" in type_name
                    or "RTManager" in type_name
                    or hasattr(mgr, "active_symbols")
                    or hasattr(mgr, "codes")
                ):
                    logger.info(
                        "[UI Utils] ✅ RealtimeManager found in %s.%s (%s)",
                        _key,
                        attr_name,
                        type_name,
                    )
                    return mgr
            except Exception as e:
                logger.debug("[UI Utils] Error checking %s.%s: %s", _key, attr_name, e)

    logger.warning("[UI Utils] ⚠️ RealtimeManager가 아직 초기화되지 않음 (정상)")
    return None


def get_auto_backfill_manager() -> Optional[Any]:
    """AutoBackfillManager 전역 인스턴스 가져오기.

    Returns:
        AutoBackfillManager 인스턴스 또는 None
    """
    _static = _find_static_module()
    if _static is not None:
        return getattr(_static, "auto_backfill_manager", None)
    return None
