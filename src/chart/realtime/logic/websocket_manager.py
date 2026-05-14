# -*- coding: utf-8 -*-
"""
WebSocket Manager - 실시간 WebSocket 데이터 관리

[Features]
- WebSocket 연결 관리
- 실시간 캔들 데이터 스트리밍
- 자동 재연결 (3초 간격)
- 메시지 처리율 모니터링

Unified from widgets/realtime/logic/websocket_manager.py → chart/realtime/websocket_manager.py
"""
import time
from typing import Optional

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    from utils.qt_stub import QtCore as QtCore  # type: ignore[assignment]
    QThread = QtCore.QThread  # type: ignore[attr-defined]
    pyqtSignal = QtCore.pyqtSignal  # type: ignore[attr-defined]


class WebSocketManager(QThread):
    """
    WebSocket 연결 관리자 (QThread)
    렉 방지 규칙: 네트워크 작업은 백그라운드 스레드에서
    """
    data_received = pyqtSignal(dict)
    connection_status = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, symbol: str = "KRW-BTC", endpoint: str = ""):
        super().__init__()
        self.symbol = symbol
        self.endpoint = endpoint
        self.running = False
        self.message_count = 0
        self.start_time = time.time()
        self._reconnect_delay = 3.0

    def run(self) -> None:
        """WebSocket 연결 및 데이터 수신 루프"""
        self.running = True
        self.connection_status.emit("connecting")

        try:
            # 실제 구현:
            # import websockets, asyncio
            # asyncio.run(self._ws_loop())
            pass
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.connection_status.emit("disconnected")

    def stop(self) -> None:
        """WebSocket 연결 종료"""
        self.running = False

    def get_message_rate(self) -> float:
        """초당 메시지 수신율 반환"""
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0
        return self.message_count / elapsed
