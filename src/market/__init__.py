# -*- coding: utf-8 -*-
"""
market 패키지 초기화 파일 (안전화된 lazy import)

설명:
- 이 파일은 패키지 import 시 서브모듈의 전역 초기화(부작용)를 즉시 발생시키지 않도록
  모든 위젯 클래스를 지연 로드(lazy import) 방식으로 노출합니다.
- widget_factory 등에서 "import src.market" 형태로 패키지를 로드할 때
  하위 패키지의 __init__.py 코드가 실행되어 문제를 일으키는 것을 방지합니다.
- 실제 클래스를 사용하려 할 때(예: from src.market import CoinlistWidget 또는
  import src.market; src.market.CoinlistWidget) 해당 서브모듈을 동적으로 import 합니다.

구현 원칙:
- 런타임에는 importlib.import_module을 사용해 필요한 서브모듈만 로드합니다.
- 타입 검사/IDE 편의는 typing.TYPE_CHECKING 블록에서만 정적으로 import 합니다(실행 시 영향 없음).
- 실패 시 logger.exception으로 상세 로그를 남기고 AttributeError를 발생시켜 호출자에게 알립니다.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

# 노출할 클래스 -> 서브모듈 매핑 (패키지 내부 상대 경로, 점(.) 포함 없이 표기)
# 예: "coinlist.ui.widget_coin_list"는 상대 import로 ".coinlist.ui.widget_coin_list"에 해당
_EXPORT_MODULES = {
    "CoinlistWidget": "coinlist.ui.widget_coin_list",
    "OrderbookWidget": "orderbook.ui.widget_orderbook",
    "TradeWidget": "trades.ui.widget_trade",
}

# 정적 타입 검사 및 IDE 편의성: 런타임에는 실행되지 않음 (부작용 방지)
if TYPE_CHECKING:
    # 타입 검사용 임포트 (실행 시점에는 무시됨)
    from .coinlist.ui.widget_coin_list import CoinlistWidget  # type: ignore
    from .orderbook.ui.widget_orderbook import OrderbookWidget  # type: ignore
    from .trades.ui.widget_trade import TradeWidget  # type: ignore

# __all__을 명시하여 from src.market import * 동작을 제어
__all__ = list(_EXPORT_MODULES.keys())


def __getattr__(name: str) -> Any:
    """
    PEP 562 방식의 lazy attribute 로더.
    - 요청된 이름(name)이 _EXPORT_MODULES에 있으면 해당 모듈을 상대 import로 로드하여
      속성(클래스)을 반환합니다.
    - 성공 시 패키지 전역(globals)에 캐싱하여 이후 호출 시 재사용합니다.
    - 실패 시 AttributeError를 발생시켜 정상 파이썬 동작과 호환되게 합니다.
    """
    if name in _EXPORT_MODULES:
        module_rel = f".{_EXPORT_MODULES[name]}"
        try:
            # 상대 import: package는 현재 패키지명(__name__) 사용
            mod = importlib.import_module(module_rel, package=__name__)
            attr = getattr(mod, name)
            # 캐시하여 다음 접근 시 재로딩을 방지
            globals()[name] = attr
            return attr
        except Exception:
            # 문제 발생 시 상세 로그 남기고 AttributeError로 전환
            logger.exception("market 패키지에서 '%s' 로드 실패", name)
            raise AttributeError(f"cannot import name '{name}' from '{__name__}'")
    # 존재하지 않는 속성이면 표준 동작
    raise AttributeError(name)


def __dir__() -> list[str]:
    """
    패키지에 대해 dir() 호출 시 노출될 이름 목록에 _EXPORT_MODULES를 포함시킵니다.
    """
    return sorted(list(globals().keys()) + __all__)