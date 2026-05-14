#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
체결/미체결 주문 정보를 비동기적으로 조회하는 백그라운드 워커.

[Responsibilities]
- QThread 기반 비동기 주문 조회 루프 실행
- 조회 결과를 Qt 시그널로 UI에 전달
- 일정 간격(interval_ms)으로 반복 조회

[References]
- PyQt5 QThread: https://doc.qt.io/qt-5/qthread.html
"""
from __future__ import annotations

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    class QThread:  # type: ignore[no-redef]
        """Minimal QThread stub for non-GUI environments."""
        def __init__(self, parent=None):
            pass
        def msleep(self, ms: int) -> None:
            import time; time.sleep(ms / 1000)
        def start(self) -> None:
            pass
        def wait(self) -> None:
            pass

    def pyqtSignal(*args):  # type: ignore[misc]
        return None


class TradeWorker(QThread):
    """주문 정보 조회 백그라운드 워커."""

    orders_updated = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, interval_ms: int = 3000, parent=None) -> None:
        """
        Args:
            interval_ms: 조회 반복 간격 (밀리초).
            parent: 부모 QObject.
        """
        super().__init__(parent)
        self.interval_ms = interval_ms
        self._running = False

    def run(self) -> None:
        """백그라운드 조회 루프."""
        self._running = True
        while self._running:
            try:
                orders = self._fetch_orders()
                self.orders_updated.emit(orders)
            except Exception as exc:
                self.error_occurred.emit(str(exc))
            self.msleep(self.interval_ms)

    def stop(self) -> None:
        """워커를 정지합니다."""
        self._running = False
        self.wait()

    def _fetch_orders(self) -> list:
        """주문 목록을 조회합니다. 서브클래스에서 구현하세요.

        Returns:
            주문 딕셔너리 리스트.
        """
        return []
