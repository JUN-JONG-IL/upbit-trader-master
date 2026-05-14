# -*- coding: utf-8 -*-
"""
utils package entrypoint

목적:
- utils 패키지의 핵심 유틸(예: get_logger, debounce, throttle 등)을 한 곳에서 export
- 서브모듈이 없을 경우 앱 초기화 중 불필요한 ImportError 방지 및 친절한 폴백 제공
- 개발 환경에서 PyQt 미설치 등으로 인한 편집기/런타임 경고 완화

사용법 예:
    from utils import get_logger, debounce, throttle
"""
from __future__ import annotations

import importlib
import logging
import importlib.util
import sys
import os
from typing import Any, Callable, Dict

# -----------------------
# 내부 헬퍼: missing placeholder factory
# -----------------------
def _missing_func_factory(name: str, module_name: str) -> Callable[..., Any]:
    def _missing(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            f"Optional utility '{name}' is not available because the module '{module_name}' could not be imported. "
            "Install/enable the corresponding package or check the installation."
        )
    return _missing

class _MissingClass:
    def __init__(self, name: str, module_name: str) -> None:  # type: ignore[override]
        raise RuntimeError(
            f"Optional class '{name}' is not available because the module '{module_name}' could not be imported."
        )

def _missing_class_factory(name: str, module_name: str):
    def _factory(*args: Any, **kwargs: Any):
        raise RuntimeError(
            f"Optional class '{name}' is not available because the module '{module_name}' could not be imported."
        )
    return _factory

# -----------------------
# 기본적으로 시도할 import들 (안전하게 래핑)
# -----------------------
_AVAILABLE: Dict[str, bool] = {}

# utils.py (필수 수준: 폴백 제공)
try:
    from .utils import (
        get_logger,
        get_file_path,
        ui_path,
        style_path,
        set_windows_selector_event_loop_global,
        set_multiprocessing_context,
    )
    _AVAILABLE["utils"] = True
except Exception:
    # 폴백: 최소한의 get_logger 구현 제공
    def get_logger(name: str | None = None) -> logging.Logger:
        return logging.getLogger(name or "app")

    def get_file_path(*parts: str) -> str:
        raise RuntimeError("utils.get_file_path is not available in this environment")

    def ui_path(*parts: str) -> str:
        raise RuntimeError("utils.ui_path is not available in this environment")

    def style_path(*parts: str) -> str:
        raise RuntimeError("utils.style_path is not available in this environment")

    def set_windows_selector_event_loop_global() -> None:
        # best-effort no-op
        try:
            import asyncio as _aio
            if hasattr(_aio, "WindowsSelectorEventLoopPolicy"):
                _aio.set_event_loop_policy(_aio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    def set_multiprocessing_context() -> None:
        # no-op fallback
        return None

    _AVAILABLE["utils"] = False

# debounce (선택적)
try:
    from .debounce import debounce, debounce_qt, Debounce, DebounceQt  # type: ignore
    _AVAILABLE["debounce"] = True
except Exception:
    debounce = _missing_func_factory("debounce", "utils.debounce")
    debounce_qt = _missing_func_factory("debounce_qt", "utils.debounce")
    Debounce = _missing_class_factory("Debounce", "utils.debounce")
    DebounceQt = _missing_class_factory("DebounceQt", "utils.debounce")
    _AVAILABLE["debounce"] = False

# throttle (선택적)
try:
    from .throttle import throttle, throttle_qt, Throttle, ThrottleQt  # type: ignore
    _AVAILABLE["throttle"] = True
except Exception:
    throttle = _missing_func_factory("throttle", "utils.throttle")
    throttle_qt = _missing_func_factory("throttle_qt", "utils.throttle")
    Throttle = _missing_class_factory("Throttle", "utils.throttle")
    ThrottleQt = _missing_class_factory("ThrottleQt", "utils.throttle")
    _AVAILABLE["throttle"] = False

# Qt stub exposure (optional convenience)
# 코드에서 `from utils import QtCore` 같은 호출을 고려하는 경우에만 노출
try:
    # 우선 실제 PyQt5가 있으면 사용
    from PyQt5 import QtCore  # type: ignore
    _AVAILABLE["pyqt5"] = True
except Exception:
    # 프로젝트 내에 utils/qt_stub.py 가 있으면 사용
    try:
        from .qt_stub import QtCore  # type: ignore
        _AVAILABLE["qt_stub"] = True
    except Exception:
        QtCore = None  # type: ignore
        _AVAILABLE["pyqt5"] = False
        _AVAILABLE["qt_stub"] = False

# -----------------------
# Fallback: 동적 로드 (qt_stub가 다른 경로에 있을 때)
# -----------------------
# 만약 아직 QtCore가 None 이고, utils.qt_stub 를 src/01_core/... 처럼 다른 위치에 생성하셨다면
# 아래 후보 경로들에서 qt_stub.py를 찾아 동적으로 로드해 `utils.qt_stub` 이름으로 등록합니다.
if QtCore is None:
    try:
        here = os.path.dirname(os.path.abspath(__file__))  # .../src/utils
        candidate_files = [
            os.path.join(here, "qt_stub.py"),  # src/utils/qt_stub.py (preferred)
            os.path.abspath(os.path.join(here, "..", "01_core", "utils", "qt_stub.py")),  # src/01_core/utils/qt_stub.py (your created path)
            os.path.abspath(os.path.join(here, "..", "01_core", "qt_stub.py")),  # alternative guess
        ]
        for cand in candidate_files:
            try:
                if not cand:
                    continue
                cand = os.path.abspath(cand)
                if os.path.isfile(cand):
                    spec = importlib.util.spec_from_file_location("utils.qt_stub", cand)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                        # register under expected module name so existing imports work
                        sys.modules["utils.qt_stub"] = mod
                        QtCore = getattr(mod, "QtCore", None)
                        _AVAILABLE["qt_stub"] = True
                        break
            except Exception:
                # 실패해도 다음 후보로 계속 시도
                continue
    except Exception:
        # 전체 폴백 블록 실패 시 무시 (QtCore remains None)
        pass

# 노출용 가용성 정보
AVAILABLE: Dict[str, bool] = _AVAILABLE.copy()

# -----------------------
# 공개 API
# -----------------------
__all__ = [
    # utils functions
    "get_logger",
    "get_file_path",
    "ui_path",
    "style_path",
    "set_windows_selector_event_loop_global",
    "set_multiprocessing_context",
    # debounce
    "debounce",
    "debounce_qt",
    "Debounce",
    "DebounceQt",
    # throttle
    "throttle",
    "throttle_qt",
    "Throttle",
    "ThrottleQt",
    # optional QtCore namespace (may be None)
    "QtCore",
    # availability map
    "AVAILABLE",
]

# module-level logger for utils package users
_logger = get_logger(__name__)
_logger.debug("utils package loaded; availability: %s", AVAILABLE)