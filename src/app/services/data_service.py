# -*- coding: utf-8 -*-
"""
data_01 紐⑤뱢 ?명꽣?섏씠??
TimescaleDB / Redis / MongoDB ?곗씠???묎렐 異붿긽??
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_data_dir = str(Path(__file__).parents[3] / "data_01")
if _data_dir not in sys.path:
    sys.path.insert(0, _data_dir)


class DataService:
    """data_01 紐⑤뱢 ?쒕퉬???덉씠??""

    def __init__(self) -> None:
        self._timescale: Optional[Any] = None
        self._redis: Optional[Any] = None
        self._mongo: Optional[Any] = None

    # ?? TimescaleDB ??????????????????????????????????????????????????????????

    def get_timescale(self) -> Any:
        if self._timescale is None:
            try:
                from timescale.timescale_settings import TimescaleSettings  # type: ignore
                self._timescale = TimescaleSettings()
            except ImportError:
                pass
        return self._timescale

    # ?? Redis ????????????????????????????????????????????????????????????????

    def get_redis(self) -> Any:
        if self._redis is None:
            try:
                from redis.core.connection import get_client  # type: ignore
                self._redis = get_client()
            except ImportError:
                pass
        return self._redis

    # ?? MongoDB ??????????????????????????????????????????????????????????????

    def get_mongo(self) -> Any:
        if self._mongo is None:
            try:
                from mongodb.core.handler import DBHandler  # type: ignore
                self._mongo = DBHandler()
            except ImportError:
                pass
        return self._mongo

    async def get_candles(
        self, symbol: str, tf: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        李⑦듃 ?곗씠??議고쉶 (L1 Redis 罹먯떆 ??TimescaleDB)
        """
        redis = self.get_redis()
        if redis is not None:
            try:
                cached = await redis.get_candles(symbol, tf, limit)
                if cached:
                    return cached
            except Exception:
                pass

        ts = self.get_timescale()
        if ts is not None:
            try:
                candles = await ts.fetch_candles(symbol, tf, limit)
                if redis is not None:
                    try:
                        await redis.cache_candles(symbol, tf, candles)
                    except Exception:
                        pass
                return candles
            except Exception:
                pass
        return []

