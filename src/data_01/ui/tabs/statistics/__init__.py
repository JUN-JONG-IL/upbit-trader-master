# -*- coding: utf-8 -*-
"""
statistics 서브패키지 초기화
- 이 파일은 statistics 폴더를 명시적 파이썬 패키지로 만들고,
  외부에서 주요 클래스/함수를 안전하게 import 할 수 있게 공개합니다.
- 최소한의 방어적 래핑만 포함하여 임포트 실패가 전체 앱을 중단시키지 않도록 합니다.
"""

from __future__ import annotations

# 가능한 한 ImportError를 전파하지 않도록 try/except 래핑
try:
    from .statistics_tab import StatisticsTab
except Exception:  # pragma: no cover
    StatisticsTab = None

try:
    from .statistics_tab_controller import StatisticsTabController
except Exception:  # pragma: no cover
    StatisticsTabController = None

try:
    from .statistics_tab_persistence import Persistence
except Exception:  # pragma: no cover
    Persistence = None

try:
    from .statistics_tab_buffer import BufferManager
except Exception:  # pragma: no cover
    BufferManager = None

try:
    from .statistics_tab_forwarding import ForwardingRegistrar
except Exception:  # pragma: no cover
    ForwardingRegistrar = None

try:
    from .statistics_model import StatisticsModel, LogFilterProxyModel
except Exception:  # pragma: no cover
    StatisticsModel = None
    LogFilterProxyModel = None

__all__ = [
    "StatisticsTab",
    "StatisticsTabController",
    "Persistence",
    "BufferManager",
    "ForwardingRegistrar",
    "StatisticsModel",
    "LogFilterProxyModel",
]