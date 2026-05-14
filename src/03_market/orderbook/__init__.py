"""
orderbook package: Displays order book (호가창).

[Purpose]
- orderbook(호가창) 기능 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- OrderbookWidget 심볼을 외부에서 import 하기 쉽게 재노출한다.

Exports:
- OrderbookWidget (main widget)
"""

from .ui.widget_orderbook import OrderbookWidget

__all__ = ["OrderbookWidget"]