"""
src/data_01/pipeline/receiver.py
Stage 2: WebSocket / REST API ?곗씠???섏떊

Upbit WebSocket ?붾뱶?ъ씤?몃? 援щ룆?섏뿬 ?ㅼ떆媛?ticker ?곗씠?곕? ?섏떊?⑸땲??
?섏떊???곗씠?곕뒗 candle dict ?뺥깭濡?蹂????肄쒕갚(on_candle)???듯빐 ?꾨떖?⑸땲??
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
    """Upbit WebSocket ?섏떊湲?"""

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
        """WebSocket ?곌껐???쒖옉?⑸땲??"""
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as exc:
                logger.error("WebSocket ?곌껐 ?ㅻ쪟: %s ??5珥????ъ뿰寃?, exc)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """?섏떊??以묐떒?⑸땲??"""
        self._running = False

    async def _connect(self) -> None:
        """WebSocket???곌껐?섍퀬 硫붿떆吏瑜?泥섎━?⑸땲??"""
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise ImportError("websockets ?⑦궎吏媛 ?꾩슂?⑸땲??") from exc

        subscribe = json.dumps([
            {"ticket": str(uuid.uuid4())},
            {
                "type":  "ticker",
                "codes": self._symbols,
            },
        ])

        async with websockets.connect(UPBIT_WS_URL) as ws:
            await ws.send(subscribe)
            logger.info("WebSocket 援щ룆 ?꾨즺: %d ?щ낵", len(self._symbols))
            async for raw in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    candle = self._to_candle(msg)
                    if candle and self._on_candle:
                        await self._on_candle(candle)
                except Exception as exc:
                    logger.warning("硫붿떆吏 泥섎━ ?ㅻ쪟: %s", exc)

    def _to_candle(self, msg: dict) -> Optional[dict]:
        """WebSocket ticker 硫붿떆吏瑜?candle dict濡?蹂?섑빀?덈떎."""
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

