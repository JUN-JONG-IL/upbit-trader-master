"""
[Purpose]
core/ - 핵심 서버 로직 패키지

[Responsibilities]
- FastAPI 앱, WebSocket, 세션 관리 re-export

[Components]
- fastapi_app: FastAPI 애플리케이션
- websocket_manager: WebSocket 연결 관리
- session_manager: 세션 관리
"""

from .fastapi_app import app, create_app
from .websocket_manager import WebSocketManager
from .session_manager import SessionManager

__all__ = [
    "app",
    "create_app",
    "WebSocketManager",
    "SessionManager",
]
