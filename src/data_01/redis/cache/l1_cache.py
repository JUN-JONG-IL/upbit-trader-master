#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L1 캐시 관리 (Redis LPUSH + LTRIM)

목적: 최근 500개 캔들 빠른 조회 (5ms)
구현:
  - LPUSH: 최신 데이터 앞에 추가
  - LTRIM: 500개 유지
  - TTL: 7일 자동 삭제
  - 키 패턴: candles:{symbol}:{timeframe}
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

LOG = logging.getLogger("redis.cache.l1")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson  # type: ignore
    ORJSON_AVAILABLE = False

L1_MAX_SIZE = 500
L1_TTL_SECONDS = 7 * 24 * 3600  # 7일


def _make_key(symbol: str, timeframe: str) -> str:
    return f"candles:{symbol}:{timeframe}"


class L1Cache:
    """
    Redis L1 캐시 관리자.
    
    최근 500개 캔들을 Redis List에 저장하여 5ms 이하 조회 제공.
    """

    def __init__(self, client=None, max_size: int = L1_MAX_SIZE, ttl: int = L1_TTL_SECONDS):
        self.client = client
        self.max_size = max_size
        self.ttl = ttl

    async def push(self, symbol: str, timeframe: str, candle: Dict[str, Any]) -> bool:
        """
        캔들을 L1 캐시 앞에 추가 (LPUSH + LTRIM + EXPIRE)
        
        Args:
            symbol: 심볼 (예: KRW-BTC)
            timeframe: TF (예: 1m)
            candle: 캔들 dict
        """
        if not self.client:
            return False
        try:
            key = _make_key(symbol, timeframe)
            # 직렬화
            if ORJSON_AVAILABLE:
                serialized = orjson.dumps(candle)
            else:
                serialized = orjson.dumps(candle).encode()
            # LPUSH + LTRIM + EXPIRE
            pipe = self.client.pipeline()
            pipe.lpush(key, serialized)
            pipe.ltrim(key, 0, self.max_size - 1)
            pipe.expire(key, self.ttl)
            await pipe.execute()
            return True
        except Exception as e:
            LOG.error("L1 캐시 push 실패: %s", e)
            return False

    async def push_batch(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> int:
        """배치 push"""
        if not self.client or not candles:
            return 0
        try:
            key = _make_key(symbol, timeframe)
            pipe = self.client.pipeline()
            for c in candles:
                if ORJSON_AVAILABLE:
                    serialized = orjson.dumps(c)
                else:
                    serialized = orjson.dumps(c).encode()
                pipe.lpush(key, serialized)
            pipe.ltrim(key, 0, self.max_size - 1)
            pipe.expire(key, self.ttl)
            await pipe.execute()
            return len(candles)
        except Exception as e:
            LOG.error("L1 캐시 batch push 실패: %s", e)
            return 0

    async def get(self, symbol: str, timeframe: str, count: int = 500) -> List[Dict[str, Any]]:
        """
        최근 N개 캔들 조회 (LRANGE)
        
        Returns:
            캔들 list (newest first)
        """
        if not self.client:
            return []
        try:
            key = _make_key(symbol, timeframe)
            items = await self.client.lrange(key, 0, min(count, self.max_size) - 1)
            result = []
            for item in items:
                try:
                    if ORJSON_AVAILABLE:
                        result.append(orjson.loads(item))
                    else:
                        result.append(orjson.loads(item.decode() if isinstance(item, bytes) else item))
                except Exception:
                    continue
            return result
        except Exception as e:
            LOG.error("L1 캐시 get 실패: %s", e)
            return []

    async def size(self, symbol: str, timeframe: str) -> int:
        """캐시 크기 조회"""
        if not self.client:
            return 0
        try:
            key = _make_key(symbol, timeframe)
            return await self.client.llen(key)
        except Exception:
            return 0

    async def clear(self, symbol: str, timeframe: str) -> bool:
        """캐시 삭제"""
        if not self.client:
            return False
        try:
            key = _make_key(symbol, timeframe)
            await self.client.delete(key)
            return True
        except Exception as e:
            LOG.error("L1 캐시 clear 실패: %s", e)
            return False
