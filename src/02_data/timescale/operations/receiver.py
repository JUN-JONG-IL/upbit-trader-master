#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
2단계 - 데이터 수신 (실시간 WS + 백필 API)
...
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from enum import Enum

# 조건부 임포트
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("⚠️  aiohttp 미설치 - WebSocket 연결 불가")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logging.warning("⚠️  httpx 미설치 - HTTP 요청 불가")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson
    ORJSON_AVAILABLE = False


# ============================================================
# Enum 정의
# ============================================================
class ExchangeType(Enum):
    """거래소 타입"""
    UPBIT = "upbit"
    BITHUMB = "bithumb"
    BINANCE = "binance"
    # 추가 거래소


class DataType(Enum):
    """데이터 타입"""
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    CANDLE = "candle"


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class ReceiverConfig:
    """수신기 설정"""
    exchange: ExchangeType
    symbols: List[str]
    data_type: DataType
    ws_url: Optional[str] = None
    api_url: Optional[str] = None
    rate_limit: int = 10  # 초당 요청 제한
    chunk_size: int = 200  # 백필 청크 크기
    reconnect_delay: int = 1  # 재연결 지연 (초)
    max_reconnect_attempts: int = 5


@dataclass
class ReceivedData:
    """수신 데이터"""
    exchange: str
    symbol: str
    data_type: str
    timestamp: datetime
    data: Dict[str, Any]
    raw: str  # 원본 JSON


# ============================================================
# BaseReceiver 추상 클래스
# ============================================================
class BaseReceiver:
    """데이터 수신기 기본 클래스"""
    
    def __init__(self, config: ReceiverConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.running = False
        self.reconnect_count = 0
        self.data_callback: Optional[Callable] = None
    
    async def initialize(self):
        """초기화"""
        if AIOHTTP_AVAILABLE and not self.session:
            self.session = aiohttp.ClientSession()
            logging.info(f"✅ {self.config.exchange.value} 세션 생성")
    
    async def close(self):
        """연결 종료"""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
    
    def set_callback(self, callback: Callable):
        """데이터 수신 콜백 등록"""
        self.data_callback = callback
    
    async def _handle_received_data(self, data: ReceivedData):
        """수신 데이터 처리"""
        if self.data_callback:
            await self.data_callback(data)
    
    async def start_websocket(self):
        """WebSocket 시작 (하위 클래스 구현)"""
        raise NotImplementedError
    
    async def backfill(self, start_time: datetime, end_time: datetime):
        """백필 (하위 클래스 구현)"""
        raise NotImplementedError


# ============================================================
# UpbitReceiver
# ============================================================
class UpbitReceiver(BaseReceiver):
    """Upbit 데이터 수신기"""
    
    def __init__(self, config: ReceiverConfig):
        super().__init__(config)
        self.ws_url = config.ws_url or "wss://api.upbit.com/websocket/v1"
        self.api_url = config.api_url or "https://api.upbit.com/v1"
    
    async def start_websocket(self):
        """Upbit WebSocket 연결"""
        if not AIOHTTP_AVAILABLE:
            logging.error("❌ aiohttp 미설치")
            return
        
        self.running = True
        
        while self.running:
            try:
                async with self.session.ws_connect(self.ws_url) as ws:
                    self.ws = ws
                    logging.info(f"✅ Upbit WebSocket 연결: {self.config.symbols}")
                    
                    # 구독 메시지
                    subscribe_msg = [
                        {"ticket": "unique_ticket"},
                        {
                            "type": "ticker",
                            "codes": self.config.symbols,
                            "isOnlyRealtime": True
                        }
                    ]
                    
                    await ws.send_json(subscribe_msg)
                    
                    # 메시지 수신 루프
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._process_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logging.error(f"❌ WS 에러: {ws.exception()}")
                            break
                
                # 연결 종료 시 재연결
                if self.running:
                    await self._reconnect()
            
            except Exception as e:
                logging.error(f"❌ WS 연결 실패: {e}")
                if self.running:
                    await self._reconnect()
    
    async def _process_message(self, data: str):
        """메시지 처리"""
        try:
            parsed = orjson.loads(data) if ORJSON_AVAILABLE else __import__('json').loads(data)
            
            received = ReceivedData(
                exchange=self.config.exchange.value,
                symbol=parsed.get('code', 'UNKNOWN'),
                data_type=parsed.get('type', 'ticker'),
                timestamp=datetime.now(),
                data=parsed,
                raw=data
            )
            
            await self._handle_received_data(received)
            
        except Exception as e:
            logging.error(f"❌ 메시지 파싱 실패: {e}")
    
    async def _reconnect(self):
        """재연결 (Exponential Backoff)"""
        if self.reconnect_count >= self.config.max_reconnect_attempts:
            logging.error("❌ 최대 재연결 시도 초과")
            self.running = False
            return
        
        delay = self.config.reconnect_delay * (2 ** self.reconnect_count)
        logging.warning(f"⚠️  {delay}초 후 재연결 시도 ({self.reconnect_count + 1}회)")
        await asyncio.sleep(delay)
        
        self.reconnect_count += 1
    
    async def backfill(self, start_time: datetime, end_time: datetime):
        """Upbit 백필 (REST API)"""
        if not HTTPX_AVAILABLE:
            logging.error("❌ httpx 미설치")
            return
        
        logging.info(f"🔄 백필 시작: {start_time} ~ {end_time}")
        
        # Semaphore (초당 10회 제한)
        semaphore = asyncio.Semaphore(self.config.rate_limit)
        
        async with httpx.AsyncClient() as client:
            for symbol in self.config.symbols:
                await self._backfill_symbol(client, semaphore, symbol, start_time, end_time)
    
    async def _backfill_symbol(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ):
        """심볼별 백필"""
        url = f"{self.api_url}/candles/minutes/1"
        params = {
            "market": symbol,
            "count": self.config.chunk_size
        }
        
        async with semaphore:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                candles = response.json()
                logging.info(f"✅ 백필 수신: {symbol} ({len(candles)}개)")
                
                # 데이터 처리 (3단계로 전달)
                for candle in candles:
                    received = ReceivedData(
                        exchange=self.config.exchange.value,
                        symbol=symbol,
                        data_type='candle',
                        timestamp=datetime.fromisoformat(candle['candle_date_time_kst'].replace('Z', '+00:00')),
                        data=candle,
                        raw=orjson.dumps(candle).decode() if ORJSON_AVAILABLE else str(candle)
                    )
                    
                    await self._handle_received_data(received)
            
            except Exception as e:
                logging.error(f"❌ 백필 실패: {symbol} - {e}")


# ============================================================
# BithumbReceiver (예시)
# ============================================================
class BithumbReceiver(BaseReceiver):
    """Bithumb 데이터 수신기 (TODO)"""
    
    async def start_websocket(self):
        """TODO: Bithumb WebSocket"""
        logging.warning("⚠️  Bithumb WebSocket 미구현")
    
    async def backfill(self, start_time: datetime, end_time: datetime):
        """TODO: Bithumb 백필"""
        logging.warning("⚠️  Bithumb 백필 미구현")


# ============================================================
# ReceiverFactory
# ============================================================
class ReceiverFactory:
    """수신기 팩토리"""
    
    @staticmethod
    def create(config: ReceiverConfig) -> BaseReceiver:
        """거래소별 수신기 생성"""
        if config.exchange == ExchangeType.UPBIT:
            return UpbitReceiver(config)
        elif config.exchange == ExchangeType.BITHUMB:
            return BithumbReceiver(config)
        else:
            raise ValueError(f"❌ 지원하지 않는 거래소: {config.exchange}")


# ============================================================
# 테스트
# ============================================================
async def main():
    """테스트"""
    logging.basicConfig(level=logging.INFO)
    
    # 설정
    config = ReceiverConfig(
        exchange=ExchangeType.UPBIT,
        symbols=["KRW-BTC", "KRW-ETH"],
        data_type=DataType.TICKER
    )
    
    # 수신기 생성
    receiver = ReceiverFactory.create(config)
    await receiver.initialize()
    
    # 콜백 등록
    async def on_data(data: ReceivedData):
        print(f"✅ 수신: {data.symbol} @ {data.timestamp}")
    
    receiver.set_callback(on_data)
    
    try:
        # WebSocket 시작
        await asyncio.gather(
            receiver.start_websocket(),
            # 10초 후 종료
            asyncio.sleep(10)
        )
    finally:
        await receiver.close()


if __name__ == '__main__':
    asyncio.run(main())