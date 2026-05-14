# -*- coding: utf-8 -*-
"""
Sync Manager - 멀티차트 동기화 관리

[Features]
- 시간 범위 동기화
- 심볼 동기화
- 크로스헤어 동기화

Unified from widgets/multi/logic/sync_manager.py → chart/multi/sync_manager.py
"""
from typing import List, Optional

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    from utils.qt_stub import QtCore as QtCore  # type: ignore[assignment]
    QThread = QtCore.QThread  # type: ignore[attr-defined]
    pyqtSignal = QtCore.pyqtSignal  # type: ignore[attr-defined]


class SyncManager(QThread):
    """
    멀티차트 동기화 관리자 (QThread)
    시간/크로스헤어/줌/심볼 동기화
    """
    sync_event = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.time_sync_enabled: bool = True
        self.symbol_sync_enabled: bool = False
        self.crosshair_sync_enabled: bool = True
        self.charts: List = []

    def add_chart(self, chart) -> None:
        """차트 추가"""
        if chart not in self.charts:
            self.charts.append(chart)

    def remove_chart(self, chart) -> None:
        """차트 제거"""
        if chart in self.charts:
            self.charts.remove(chart)

    def sync_time(self, start_ts: float, end_ts: float, zoom_level: float) -> None:
        """시간 범위 동기화"""
        if not self.time_sync_enabled:
            return
        self.sync_event.emit({
            'type': 'time_sync',
            'start': start_ts,
            'end': end_ts,
            'zoom': zoom_level,
        })

    def sync_symbol(self, symbol: str) -> None:
        """심볼 동기화"""
        if not self.symbol_sync_enabled:
            return
        self.sync_event.emit({'type': 'symbol_sync', 'symbol': symbol})

    def sync_crosshair(self, x: float, y: float) -> None:
        """크로스헤어 동기화"""
        if not self.crosshair_sync_enabled:
            return
        self.sync_event.emit({'type': 'crosshair_sync', 'x': x, 'y': y})
