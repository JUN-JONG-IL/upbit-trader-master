#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Integrated WebSocket stream handler - /ws/stream endpoint

Notes:
- Uses REDIS_URL first, then REDIS_HOST/REDIS_PORT, and REDIS_PASSWORD if present.
- Attempts one reconnect using the alternative connection method on initial failure.
- Connection/authentication failures are logged as warnings (no full traceback).
- Listener internal errors are logged at debug level to reduce terminal noise.
- No new files are created; this file is a replacement for the original.
"""

import os
import time
import json
import asyncio
import logging
from typing import Dict, Set, Tuple, Optional, Any
from urllib.parse import urlparse

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False

# Module logger
logger = logging.getLogger("server.websocket.stream_handler")
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)


class StreamHandler:
    """
    Broadcast Redis Pub/Sub messages to WebSocket clients.
    """

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        # default values keep backward compatibility if envs absent
        self.redis_host = redis_host
        self.redis_port = redis_port

        # mapping WebSocket -> set((symbol, timeframe))
        self.connections: Dict[WebSocket, Set[Tuple[str, str]]] = {}

        # Throttle tracking
        self.last_broadcast: Dict[Tuple[str, str], float] = {}
        self.throttle_ms = 500  # 500ms throttle

        # Redis client and pubsub (use Any to avoid static-type runtime-symbol issues)
        self.redis_client: Optional[Any] = None
        self.pubsub: Optional[Any] = None

        # Background listener task
        self.listener_task: Optional[asyncio.Task] = None

    def _build_redis_params(self):
        """
        Determine Redis connection parameters using env vars:
        - Prefer REDIS_URL if present
        - Else use REDIS_HOST / REDIS_PORT
        - REDIS_PASSWORD used if present
        Returns tuple (use_url: bool, connection_arg)
        - if use_url True -> connection_arg is URL string
        - else -> connection_arg is dict with host/port/password
        """
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            return True, redis_url

        host = os.getenv("REDIS_HOST", self.redis_host)
        port_env = os.getenv("REDIS_PORT")
        try:
            port = int(port_env) if port_env else int(self.redis_port)
        except Exception:
            port = int(self.redis_port)
        password = os.getenv("REDIS_PASSWORD", None)
        return False, {"host": host, "port": port, "password": password}

    def _create_redis_client_from_url(self, url: str):
        try:
            # redis.from_url handles db/path in URL automatically
            if hasattr(redis, "Redis") and hasattr(redis.Redis, "from_url"):
                return redis.Redis.from_url(url, decode_responses=True)
            # fallback: parse and create
            p = urlparse(url)
            host = p.hostname or "localhost"
            port = p.port or 6379
            password = p.password
            return redis.Redis(host=host, port=port, password=password, decode_responses=True)
        except Exception as e:
            logger.debug("create_redis_client_from_url failed: %s", e)
            return None

    def _create_redis_client_from_params(self, params: dict):
        try:
            return redis.Redis(host=params.get("host", "localhost"),
                               port=int(params.get("port", 6379)),
                               password=params.get("password", None),
                               decode_responses=True)
        except Exception as e:
            logger.debug("create_redis_client_from_params failed: %s", e)
            return None

    async def start(self):
        """Start handler: connect to Redis and start listener."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis module not available; StreamHandler will be disabled.")
            return

        # Determine preferred connection method
        use_url, conn_arg = self._build_redis_params()

        # Helper to attempt and optionally try alternate on failure
        def try_connect(primary_is_url: bool, primary_arg):
            client = None
            try:
                if primary_is_url:
                    client = self._create_redis_client_from_url(primary_arg)
                else:
                    client = self._create_redis_client_from_params(primary_arg)
                if client is None:
                    return None, "client_factory_failed"
                # ping to validate connection/auth
                try:
                    client.ping()
                except Exception as e_ping:
                    # Distinguish AuthenticationError if possible
                    try:
                        auth_exc = redis.exceptions.AuthenticationError
                    except Exception:
                        auth_exc = None
                    if auth_exc and isinstance(e_ping, auth_exc):
                        return None, f"auth_failed:{e_ping}"
                    return None, f"ping_failed:{e_ping}"
                return client, None
            except Exception as e:
                logger.debug("Redis primary connection attempt raised: %s", e)
                return None, f"exception:{e}"

        # First attempt (preferred)
        client, err = try_connect(use_url, conn_arg)

        # If failed, attempt one retry with the alternate method (to be resilient)
        if client is None:
            logger.warning("StreamHandler: Redis initial connect failed (%s). Attempting alternate method.", err)
            try:
                # build alternate args
                if use_url:
                    # primary was url; fallback to host/port
                    host = os.getenv("REDIS_HOST", self.redis_host)
                    try:
                        port = int(os.getenv("REDIS_PORT", self.redis_port))
                    except Exception:
                        port = int(self.redis_port)
                    alt_arg = {"host": host, "port": port, "password": os.getenv("REDIS_PASSWORD", None)}
                    client, err2 = try_connect(False, alt_arg)
                else:
                    # primary was host/port; fallback to REDIS_URL if present
                    redis_url = os.getenv("REDIS_URL")
                    if redis_url:
                        client, err2 = try_connect(True, redis_url)
                    else:
                        client = None
                        err2 = "no_alternate_url"
                if client is None:
                    logger.warning("StreamHandler: Redis alternate connect failed (%s). StreamHandler will start without Redis.", err2)
                    return
                else:
                    logger.info("StreamHandler: Redis connected on alternate method")
            except Exception as e:
                logger.warning("StreamHandler: Redis alternate connect attempt raised: %s", e)
                return
        else:
            logger.info("StreamHandler: Redis connected (preferred method)")

        # At this point client is valid
        self.redis_client = client

        try:
            # Subscribe to channels
            try:
                self.pubsub = self.redis_client.pubsub()
                self.pubsub.subscribe("ws:chart", "ws:scanner")
            except Exception as e:
                logger.warning("Redis pubsub subscribe failed: %s", e)
                self.pubsub = None
                # keep redis_client live but do not start listener
                return

            # Start background listener
            self.listener_task = asyncio.create_task(self._redis_listener())
            logger.info("StreamHandler started (Redis connected, listener running)")

        except Exception as e:
            logger.warning("StreamHandler start error after connect: %s", e)
            self.redis_client = None

    async def stop(self):
        """Stop handler: cancel listener and cleanup Redis resources."""
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("Error while cancelling listener task: %s", e)

        if self.pubsub:
            try:
                self.pubsub.unsubscribe()
            except Exception:
                pass
            try:
                self.pubsub.close()
            except Exception:
                pass

        if self.redis_client:
            try:
                if hasattr(self.redis_client, "close"):
                    self.redis_client.close()
            except Exception:
                pass

        logger.info("StreamHandler stopped")

    async def connect(self, websocket: WebSocket):
        """Handle an incoming WebSocket connection (subscribe/unsubscribe commands)."""
        await websocket.accept()
        self.connections[websocket] = set()
        logger.debug("Client connected: total=%d", len(self.connections))

        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                if action == "subscribe":
                    symbol = data.get("symbol")
                    timeframe = data.get("timeframe")
                    if symbol and timeframe:
                        await self.subscribe(websocket, symbol, timeframe)
                elif action == "unsubscribe":
                    symbol = data.get("symbol")
                    timeframe = data.get("timeframe")
                    if symbol and timeframe:
                        await self.unsubscribe(websocket, symbol, timeframe)

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.debug("WebSocket processing error: %s", e)
            self.disconnect(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.connections:
            try:
                del self.connections[websocket]
            except Exception:
                pass
            logger.debug("Client disconnected: total=%d", len(self.connections))

    async def subscribe(self, websocket: WebSocket, symbol: str, timeframe: str):
        """Add a subscription for a websocket."""
        if websocket in self.connections:
            self.connections[websocket].add((symbol, timeframe))
            logger.debug("Subscribe added: %s %s", symbol, timeframe)

    async def unsubscribe(self, websocket: WebSocket, symbol: str, timeframe: str):
        """Remove a subscription for a websocket."""
        if websocket in self.connections:
            self.connections[websocket].discard((symbol, timeframe))
            logger.debug("Subscribe removed: %s %s", symbol, timeframe)

    async def _redis_listener(self):
        """Background loop reading Redis pub/sub messages and dispatching them."""
        logger.info("StreamHandler Redis listener started")
        if not self.pubsub:
            logger.debug("No pubsub configured; listener will not run")
            return

        try:
            while True:
                try:
                    message = self.pubsub.get_message(timeout=0.1)
                    if message and message.get("type") == "message":
                        channel = message.get("channel")
                        data_str = message.get("data")

                        # data may be bytes or string
                        if isinstance(data_str, (bytes, bytearray)):
                            try:
                                data_str = data_str.decode("utf-8", errors="replace")
                            except Exception:
                                data_str = str(data_str)

                        data = None
                        if data_str:
                            try:
                                data = json.loads(data_str)
                            except Exception:
                                logger.debug("JSON decode failed for message: %s", data_str)

                        if data is not None:
                            if channel == "ws:chart":
                                await self._handle_chart_message(data)
                            elif channel == "ws:scanner":
                                await self._handle_scanner_message(data)

                    # no message - short sleep
                    if not message or message.get("type") != "message":
                        await asyncio.sleep(0.05)

                except Exception as e:
                    # keep listener alive; log at debug level to reduce noise
                    logger.debug("Redis listener item error: %s", e)
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.debug("Redis listener cancelled")
        except Exception as e:
            logger.warning("Redis listener stopped (exception): %s", e)
        finally:
            logger.info("StreamHandler Redis listener exited")

    async def _handle_chart_message(self, data: dict):
        """Handle chart messages and broadcast to subscribers (throttled)."""
        symbol = data.get("symbol")
        timeframe = data.get("timeframe")
        if not symbol or not timeframe:
            return

        key = (symbol, timeframe)
        current_time = time.time() * 1000

        if key in self.last_broadcast:
            elapsed = current_time - self.last_broadcast[key]
            if elapsed < self.throttle_ms:
                return

        self.last_broadcast[key] = current_time
        await self._broadcast_to_subscribers(symbol, timeframe, data)

    async def _handle_scanner_message(self, data: dict):
        """Broadcast scanner messages to all connected clients."""
        disconnected = []
        for ws in list(self.connections.keys()):
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.debug("Scanner message send failed: %s", e)
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def _broadcast_to_subscribers(self, symbol: str, timeframe: str, data: dict):
        """Send a message to subscribers of (symbol, timeframe)."""
        disconnected = []
        for ws, subscriptions in list(self.connections.items()):
            if (symbol, timeframe) in subscriptions:
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.debug("Subscriber send failed: %s", e)
                    disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


# Global instance (to be used by FastAPI endpoint)
# Instantiate StreamHandler with environment-provided host/port for consistency
_env_host = os.getenv("REDIS_HOST", "localhost")
try:
    _env_port = int(os.getenv("REDIS_PORT", "6379"))
except Exception:
    _env_port = 6379
stream_handler = StreamHandler(redis_host=_env_host, redis_port=_env_port)