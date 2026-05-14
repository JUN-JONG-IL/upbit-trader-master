# -*- coding: utf-8 -*-
"""
src/10_trade 패키지 안전 초기화 (lazy import)

목적:
- 패키지 import 시 서브패키지(core, risk, orders, ui, workers, utils)의
  __init__.py가 즉시 실행되어 부작용(side-effect) 또는 예외가 발생하는 것을 방지합니다.
- 서브패키지는 실제로 접근(속성 참조)될 때 동적으로 import 됩니다 (PEP 562 스타일).
- 정적 타입 검사 및 IDE 지원을 위해 TYPE_CHECKING 블록을 유지합니다(런타임에서는 실행되지 않음).

사용:
- from src.10_trade import core  # 런타임 시 core 서브패키지가 동적으로 로드되어 globals에 캐시됨
- import src.10_trade  # 안전, 즉시 하위 모듈 로드 없음
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

# 노출할 서브패키지 매핑: 속성명 -> 상대 모듈 경로
# (상대 경로는 패키지 루트(이 파일의 위치)를 기준으로 합니다)
_EXPORT_MODULES = {
    "core": "core",
    "risk": "risk",
    "orders": "orders",
    "ui": "ui",
    "workers": "workers",
    "utils": "utils",
}

# __all__을 명시하여 from src.10_trade import * 동작 제어
__all__ = list(_EXPORT_MODULES.keys())

# 정적 타입 검사/IDE 편의: 실행 시에는 무시됨 (부작용 방지)
if TYPE_CHECKING:
    # 타입 검사용 임포트 (실행 시 이 블록 내용은 무시됨)
    from . import core  # type: ignore
    from . import risk  # type: ignore
    from . import orders  # type: ignore
    from . import ui  # type: ignore
    from . import workers  # type: ignore
    from . import utils  # type: ignore


def __getattr__(name: str) -> Any:
    """
    PEP 562 방식의 lazy attribute 로더.
    - name이 _EXPORT_MODULES에 정의되어 있으면 상대 import로 해당 서브패키지를 로드합니다.
    - 로드 성공 시 globals()에 캐시해 다음 접근에는 재사용됩니다.
    - 로드 실패 시 logger.exception으로 상세 로그를 남기고 AttributeError를 발생시킵니다.
    """
    if name in _EXPORT_MODULES:
        module_rel = f".{_EXPORT_MODULES[name]}"
        try:
            mod = importlib.import_module(module_rel, package=__name__)
            # 캐시: 패키지 속성으로 저장 (다음 접근 시 import 안 함)
            globals()[name] = mod
            return mod
        except Exception:
            # 상세한 예외는 로그에 남기고 호출자에게는 AttributeError를 알립니다.
            logger.exception("10_trade 패키지에서 '%s' 서브패키지 로드 실패", name)
            raise AttributeError(f"cannot import subpackage '{name}' from '{__name__}'")
    raise AttributeError(name)


def __dir__() -> list[str]:
    """
    패키지에 대해 dir() 호출 시 노출될 이름 목록에 _EXPORT_MODULES를 포함시킵니다.
    """
    # globals() 키와 __all__을 합쳐 중복 제거 후 정렬 반환
    keys = set(globals().keys()) | set(__all__)
    return sorted(keys)