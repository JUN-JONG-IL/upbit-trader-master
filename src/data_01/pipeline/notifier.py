"""
src/data_01/pipeline/notifier.py
Stage 7: Redis Pub/Sub 발행

채널 구조:
    timescale:events          – 전역 이벤트
    candles:{symbol}:{tf}     – 심볼별 캔들 이벤트
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
    """캔들 저장 완료 후 Redis Pub/Sub 으로 이벤트를 발행합니다."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def notify_candle(self, candle: dict) -> None:
        """심볼별 채널과 전역 채널에 캔들 이벤트를 발행합니다."""
        symbol    = candle.get("symbol",    "")
        timeframe = candle.get("timeframe", "1m")
        message   = _json_dumps(candle)

        symbol_channel = f"candles:{symbol}:{timeframe}"
        try:
            pipe = self._redis.pipeline()
            pipe.publish(symbol_channel, message)
            pipe.publish(GLOBAL_CHANNEL,  message)
            await pipe.execute()
            logger.debug("Pub/Sub 발행: %s", symbol_channel)
        except Exception as exc:
            logger.warning("Pub/Sub 발행 실패 (%s): %s", symbol_channel, exc)

    async def notify_gap(self, symbol: str, timeframe: str, gap_seconds: float) -> None:
        """Gap 발생 이벤트를 전역 채널에 발행합니다."""
        message = _json_dumps({
            "event":      "gap_detected",
            "symbol":     symbol,
            "timeframe":  timeframe,
            "gap_seconds": gap_seconds,
        })
        try:
            await self._redis.publish(GLOBAL_CHANNEL, message)
        except Exception as exc:
            logger.warning("Gap 이벤트 발행 실패: %s", exc)
