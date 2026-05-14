# -*- coding: utf-8 -*-
"""
11_server 모듈 인터페이스
FastAPI 서버 및 WebSocket 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

_server_dir = str(Path(__file__).parents[3] / "11_server")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


class ServerService:
    """11_server 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._app: Optional[Any] = None
        self._ws_manager: Optional[Any] = None
        self._config: Optional[Any] = None

    def get_app(self) -> Any:
        if self._app is None:
            try:
                from core.fastapi_app import create_app  # type: ignore
                self._app = create_app()
            except ImportError:
                pass
        return self._app

    def get_ws_manager(self) -> Any:
        if self._ws_manager is None:
            try:
                from core.websocket_manager import WebSocketManager  # type: ignore
                self._ws_manager = WebSocketManager()
            except ImportError:
                pass
        return self._ws_manager

    def get_config(self) -> Any:
        if self._config is None:
            try:
                from config.server_config import ServerConfig  # type: ignore
                self._config = ServerConfig()
            except ImportError:
                pass
        return self._config

    def get_server_host(self) -> str:
        cfg = self.get_config()
        if cfg and hasattr(cfg, "host"):
            return str(cfg.host)
        return "127.0.0.1"

    def get_server_port(self) -> int:
        cfg = self.get_config()
        if cfg and hasattr(cfg, "port"):
            return int(cfg.port)
        return 8000
