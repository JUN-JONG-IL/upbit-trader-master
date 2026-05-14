# -*- coding: utf-8 -*-
"""
src 패키지 진입점 (shim 개선)
- 목적: 기존의 문자열에 숫자가 앞에 오는 잘못된 `from server...` 문법을 제거하고,
  importlib을 사용하여 명시적이고 안전하게 실제 구현 모듈에서 심볼을 가져옵니다.
- 동작:
  1) 후보 모듈 목록을 순서대로 시도하여 최초로 발견된 구현에서 RealtimeManager, Account, Coin을 가져옵니다.
  2) 구현을 찾지 못하면 명확한 ImportError를 발생시켜 호출부에서 문제를 즉시 알 수 있게 합니다.
- 주의:
  - 이 파일은 더 이상 "스텁 자동 배치"를 하지 않습니다. (사용자 요구: shim 제거 방향)
  - 필요한 경우 이후에 단일 구현 위치로 코드들을 일괄 정리하는 것을 권장합니다.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

_log = logging.getLogger(__name__)

__all__ = ["RealtimeManager", "Account", "Coin"]

# 후보 모듈명(우선순위). 문자열 기반으로 importlib로 로드합니다.
_CANDIDATES = [
    "server.component.component",
    "src.server.component.component",
    "server.component",
    "server.component.component",
    "component.component",
    "component",
    "src.component.component",
]

_real_mod = None
_last_exc: Optional[Exception] = None

for name in _CANDIDATES:
    try:
        mod = importlib.import_module(name)
        _real_mod = mod
        break
    except Exception as e:
        # 실패는 기록하되 콘솔에 과도하게 노출하지 않습니다.
        _last_exc = e
        continue

if _real_mod is None:
    # 구현을 찾지 못한 경우, 명확한 예외를 던져 사용자(개발자)가 바로 수정할 수 있도록 함.
    tried = ", ".join(_CANDIDATES)
    msg = (
        "필수 구현 모듈을 찾지 못했습니다. 시도한 후보: "
        f"{tried}.  \n"
        "해결 방법: src/ 디렉토리 구조가 올바른지, "
        "또는 구현 모듈(예: src/server/component/component.py)이 존재하는지 확인하세요. "
    )
    if _last_exc is not None:
        msg += f"\n마지막 예외: {_last_exc!r}"
    raise ImportError(msg)

# 실제 심볼을 명시적으로 가져옵니다. (찾지 못하면 None)
RealtimeManager: Optional[Any] = getattr(_real_mod, "RealtimeManager", None)
Account: Optional[Any] = getattr(_real_mod, "Account", None)
Coin: Optional[Any] = getattr(_real_mod, "Coin", None)

# 구현 모듈은 찾았으나 특정 심볼이 누락된 경우 명확한 에러를 발생시킵니다.
missing = [name for name, val in (("RealtimeManager", RealtimeManager), ("Account", Account), ("Coin", Coin)) if val is None]
if missing:
    raise ImportError(
        f"구현 모듈 '{_real_mod.__name__}'에서 다음 심볼이 누락되었습니다: {', '.join(missing)}. "
        "해당 모듈의 정의를 확인하세요."
    )

# 발견된 구현 모듈 이름은 진단 용도로 노출
FOUND_MODULE = getattr(_real_mod, "__name__", None)
_log.debug("src package re-exported symbols from %s", FOUND_MODULE)