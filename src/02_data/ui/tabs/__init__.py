# -*- coding: utf-8 -*-
"""탭별 UI + 로직 패키지 (10개 탭, 프로세스 흐름 순서)"""
from .dashboard_tab import DashboardTab
from .websocket_tab import WebSocketTab   # Tab 2: WebSocket 수신 (Process 1)
from .dataflow_tab import DataFlowTab
from .gap_tab import GapTab
from .error_tab import ErrorTab
from .resource_tab import ResourceTab
from .collection_tab import CollectionTab  # Tab 7: 수집 설정
from .statistics_tab import StatisticsTab
from .scanner_tab import ScannerTab
from .aiml_tab import AIMLTab
from .db_data_viewer_tab import DBDataViewerTab

__all__ = [
    "DashboardTab",
    "WebSocketTab",
    "DataFlowTab",
    "GapTab",
    "ErrorTab",
    "ResourceTab",
    "CollectionTab",
    "StatisticsTab",
    "ScannerTab",
    "AIMLTab",
    "DBDataViewerTab",
]
