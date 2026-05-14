"""
src/data_01/pipeline/notifier.py
Stage 7: Redis Pub/Sub 諛쒗뻾

梨꾨꼸 援ъ“:
    timescale:events          ???꾩뿭 ?대깽??
    candles:{symbol}:{tf}     ???щ낵蹂?罹붾뱾 ?대깽??
"""

from __future__ import annotations

import logging

try:
    import orjson  # type: ignore
    def _json_dumps(obj) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    orjson = None  # type: ignore
    import json as _json
    def _json_dumps(obj) -> str:  # type: ignore[misc]
        return _json.dumps(obj, default=str)

logger = logging.getLogger(__name__)

GLOBAL_CHANNEL = "timescale:events"


class CandleNotifier:
    """罹붾뱾 ????꾨즺 ??Redis Pub/Sub ?쇰줈 ?대깽?몃? 諛쒗뻾?⑸땲??"""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def notify_candle(self, candle: dict) -> None:
        """?щ낵蹂?梨꾨꼸怨??꾩뿭 梨꾨꼸??罹붾뱾 ?대깽?몃? 諛쒗뻾?⑸땲??"""
        symbol    = candle.get("symbol",    "")
        timeframe = candle.get("timeframe", "1m")
        message   = _json_dumps(candle)

        symbol_channel = f"candles:{symbol}:{timeframe}"
        try:
            pipe = self._redis.pipeline()
            pipe.publish(symbol_channel, message)
            pipe.publish(GLOBAL_CHANNEL,  message)
            await pipe.execute()
            logger.debug("Pub/Sub 諛쒗뻾: %s", symbol_channel)
        except Exception as exc:
            logger.warning("Pub/Sub 諛쒗뻾 ?ㅽ뙣 (%s): %s", symbol_channel, exc)

    async def notify_gap(self, symbol: str, timeframe: str, gap_seconds: float) -> None:
        """Gap 諛쒖깮 ?대깽?몃? ?꾩뿭 梨꾨꼸??諛쒗뻾?⑸땲??"""
        message = _json_dumps({
            "event":      "gap_detected",
            "symbol":     symbol,
            "timeframe":  timeframe,
            "gap_seconds": gap_seconds,
        })
        try:
            await self._redis.publish(GLOBAL_CHANNEL, message)
        except Exception as exc:
            logger.warning("Gap ?대깽??諛쒗뻾 ?ㅽ뙣: %s", exc)

