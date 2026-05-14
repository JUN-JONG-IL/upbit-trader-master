# -*- coding: utf-8 -*-
"""
[Purpose]
- trade/ui 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- 트레이드 UI 컨트롤러 클래스를 외부에서 쉽게 import 할 수 있도록 재노출한다.

[Dependencies]
- .widget_trade (TradeWidget)
"""
from .widget_trade import TradeWidget

__all__ = ['TradeWidget']