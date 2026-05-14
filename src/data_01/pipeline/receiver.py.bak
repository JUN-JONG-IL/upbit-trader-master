"""
src/02_data/pipeline/receiver.py
Stage 2: WebSocket / REST API 데이터 수신

Upbit WebSocket 엔드포인트를 구독하여 실시간 ticker 데이터를 수신합니다.
수신된 데이터는 candle dict 형태로 변환 후 콜백(on_candle)을 통해 전달됩니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


class CandleReceiver:
    """Upbit WebSocket 수신기."""

    def __init__(
        self,
        symbols: list[str],
        timeframe: str = "1m",
        on_candle: Optional[Callable[[dict], Coroutine]] = None,
    ) -> None:
        self._symbols   = symbols
        self._timeframe = timeframe
        self._on_candle = on_candle
        self._running   = False

    async def start(self) -> None:
        """WebSocket 연결을 시작합니다."""
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as exc:
                logger.error("WebSocket 연결 오류: %s – 5초 후 재연결", exc)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """수신을 중단합니다."""
        self._running = False

    async def _connect(self) -> None:
        """WebSocket에 연결하고 메시지를 처리합니다."""
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise ImportError("websockets 패키지가 필요합니다.") from exc

        subscribe = json.dumps([
            {"ticket": str(uuid.uuid4())},
            {
                "type":  "ticker",
                "codes": self._symbols,
            },
        ])

        async with websockets.connect(UPBIT_WS_URL) as ws:
            await ws.send(subscribe)
            logger.info("WebSocket 구독 완료: %d 심볼", len(self._symbols))
            async for raw in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    candle = self._to_candle(msg)
                    if candle and self._on_candle:
                        await self._on_candle(candle)
                except Exception as exc:
                    logger.warning("메시지 처리 오류: %s", exc)

    def _to_candle(self, msg: dict) -> Optional[dict]:
        """WebSocket ticker 메시지를 candle dict로 변환합니다."""
        if msg.get("type") != "ticker":
            return None
        trade_time = msg.get("trade_timestamp")
        if trade_time:
            ts = datetime.fromtimestamp(trade_time / 1000, tz=timezone.utc)
        else:
            ts = datetime.now(tz=timezone.utc)

        price = float(msg.get("trade_price", 0))
        return {
            "time":         ts,
            "symbol":       msg.get("code", ""),
            "timeframe":    self._timeframe,
            "exchange":     "upbit",
            "open":         price,
            "high":         price,
            "low":          price,
            "close":        price,
            "volume":       float(msg.get("acc_trade_volume", 0)),
            "quote_volume": float(msg.get("acc_trade_price", 0)),
            "trade_count":  int(msg.get("total_ask_size", msg.get("acc_ask_volume", 0))),
            "is_complete":  False,
            "seq":          msg.get("stream_type"),
        }
