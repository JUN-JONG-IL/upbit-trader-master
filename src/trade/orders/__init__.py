"""
[Purpose]
주문 타입 및 트레이드 UI 패키지의 공개 진입점

[Responsibilities]
- 주문 타입별 파라미터 빌더 클래스 노출 (order/ 통합)
- TradeWidget 하위 호환성 shim 유지

[Structure]
- market_order.py: 시장가 주문 빌더
- limit_order.py: 지정가 주문 빌더
- stop_order.py: 스탑 주문 빌더
- trailing_stop.py: 트레일링 스탑 빌더
- ui/: 트레이드 UI 위젯 (TradeWidget)
"""
from .market_order import MarketOrder
from .limit_order import LimitOrder
from .stop_order import StopOrder
from .trailing_stop import TrailingStop

try:
    from .ui.widget_trade import TradeWidget  # noqa: F401
    __all__ = ['MarketOrder', 'LimitOrder', 'StopOrder', 'TrailingStop', 'TradeWidget']
except ImportError:
    __all__ = ['MarketOrder', 'LimitOrder', 'StopOrder', 'TrailingStop']