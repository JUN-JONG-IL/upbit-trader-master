# -*- coding: utf-8 -*-
"""
[Purpose]
- 08_portfolio/userinfo/ui 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- 사용자 정보 UI 컨트롤러 클래스를 외부에서 쉽게 import 할 수 있도록 재노출한다.

[Dependencies]
- .widget_userinfo (UserinfoWidget)
- .widget_piechart (PieChartWidget)
"""
import logging

try:
    from .widget_userinfo import UserinfoWidget
except Exception as e:
    logging.warning("UserinfoWidget import failed: %s", e)
    UserinfoWidget = None  # type: ignore[assignment,misc]

try:
    from .widget_piechart import PieChartWidget
except Exception as e:
    logging.warning("PieChartWidget import failed: %s", e)
    PieChartWidget = None  # type: ignore[assignment,misc]

__all__ = ['UserinfoWidget', 'PieChartWidget']