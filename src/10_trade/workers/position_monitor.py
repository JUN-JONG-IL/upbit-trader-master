#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
포지션(보유 종목) 상태를 실시간으로 모니터링하는 백그라운드 워커.

[Responsibilities]
- QThread 기반 포지션 주기적 조회 루프
- 손익 계산 결과를 Qt 시그널로 UI에 전달
- 스탑로스 조건 충족 시 경고 시그널 발생

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


class PositionMonitor(QThread):
    """포지션 모니터링 백그라운드 워커."""

    positions_updated = pyqtSignal(dict)
    stop_loss_triggered = pyqtSignal(str, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, interval_ms: int = 5000, parent=None) -> None:
        """
        Args:
            interval_ms: 모니터링 반복 간격 (밀리초).
            parent: 부모 QObject.
        """
        super().__init__(parent)
        self.interval_ms = interval_ms
        self._running = False

    def run(self) -> None:
        """백그라운드 모니터링 루프."""
        self._running = True
        while self._running:
            try:
                positions = self._fetch_positions()
                self.positions_updated.emit(positions)
                self._check_stop_loss(positions)
            except Exception as exc:
                self.error_occurred.emit(str(exc))
            self.msleep(self.interval_ms)

    def stop(self) -> None:
        """모니터를 정지합니다."""
        self._running = False
        self.wait()

    def _fetch_positions(self) -> dict:
        """포지션 데이터를 조회합니다. 서브클래스에서 구현하세요.

        Returns:
            {market: position_dict} 딕셔너리.
        """
        return {}

    def _check_stop_loss(self, positions: dict) -> None:
        """스탑로스 조건을 확인합니다. 서브클래스에서 구현하세요.

        Args:
            positions: 현재 포지션 딕셔너리.
        """
        pass
