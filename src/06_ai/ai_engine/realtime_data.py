#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Real-time Data Feed - WebSocket 기반 실시간 데이터 스트리밍
freqtrade의 CCXT WebSocket 패턴 참조

CCXT Pro 라이브러리가 필요합니다:
    pip install ccxt[pro]
    
현재는 스텁 구현입니다. 실제 사용을 위해서는:
1. ccxt.pro 설치
2. Upbit API 키 설정
3. WebSocket 연결 활성화
"""

import asyncio
import logging
from typing import Dict, Optional, Callable, Any
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class RealtimeDataFeed:
    """
    실시간 WebSocket 데이터 피드
    
    freqtrade 스타일의 CCXT WebSocket 통합
    Reference: freqtrade/exchange/exchange.py
    """
    
    def __init__(self, use_ccxt_pro: bool = False):
        """
        Args:
            use_ccxt_pro: CCXT Pro WebSocket 사용 여부
                         False일 경우 폴링 기반 대체 구현 사용
        """
        self.use_ccxt_pro = use_ccxt_pro
        self.exchange = None
        self.is_running = False
        self.subscribers = {}
        self.ticker_buffer = deque(maxlen=1000)
        
        if use_ccxt_pro:
            try:
                import ccxt.pro as ccxtpro
                import os
                
                # 환경변수에서 API 키 로드
                api_key = os.getenv('UPBIT_ACCESS_KEY', '')
                secret = os.getenv('UPBIT_SECRET_KEY', '')
                
                self.exchange = ccxtpro.upbit({
                    'apiKey': api_key,
                    'secret': secret,
                    'enableRateLimit': True,
                })
                logger.info("CCXT Pro WebSocket 초기화 완료")
            except ImportError:
                logger.warning(
                    "CCXT Pro not installed. Install with: pip install ccxt[pro]"
                )
                self.use_ccxt_pro = False
    
    async def watch_ticker(self, symbol: str, callback: Optional[Callable] = None):
        """
        실시간 티커 스트리밍 (freqtrade 방식)
        
        Args:
            symbol: 심볼 (예: 'BTC/KRW')
            callback: 틱 데이터 수신 시 호출될 콜백
            
        Yields:
            Dict: 틱 데이터
        """
        if not self.use_ccxt_pro or self.exchange is None:
            logger.info(
                f"WebSocket not available for {symbol}. "
                "Using polling fallback."
            )
            # 폴링 기반 대체 구현
            async for ticker in self._watch_ticker_polling(symbol):
                if callback:
                    callback(ticker)
                yield ticker
            return
        
        self.is_running = True
        
        try:
            while self.is_running:
                ticker = await self.exchange.watch_ticker(symbol)
                
                # 틱 데이터 버퍼에 저장
                self.ticker_buffer.append({
                    'symbol': symbol,
                    'timestamp': ticker.get('timestamp'),
                    'datetime': ticker.get('datetime'),
                    'bid': ticker.get('bid'),
                    'ask': ticker.get('ask'),
                    'last': ticker.get('last'),
                    'volume': ticker.get('volume'),
                })
                
                if callback:
                    callback(ticker)
                
                yield ticker
                
        except Exception as e:
            logger.error(f"WebSocket error for {symbol}: {e}")
            self.is_running = False
    
    async def _watch_ticker_polling(self, symbol: str, interval: float = 1.0):
        """
        폴링 기반 티커 감시 (WebSocket 대체)
        
        Args:
            symbol: 심볼
            interval: 폴링 간격 (초)
        """
        # 실제 구현에서는 pyupbit 또는 ccxt 사용
        logger.info(f"Polling ticker for {symbol} every {interval}s")
        
        while self.is_running:
            # 스텁 데이터
            ticker = {
                'symbol': symbol,
                'timestamp': int(datetime.now().timestamp() * 1000),
                'datetime': datetime.now().isoformat(),
                'bid': 50000000,
                'ask': 50010000,
                'last': 50005000,
                'volume': 1234.5,
            }
            
            yield ticker
            await asyncio.sleep(interval)
    
    async def watch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1m',
        callback: Optional[Callable] = None
    ):
        """
        실시간 OHLCV 스트리밍
        
        Args:
            symbol: 심볼
            timeframe: 타임프레임 (1m, 5m, 15m, 1h 등)
            callback: 캔들 데이터 수신 시 호출될 콜백
            
        Yields:
            List: OHLCV 데이터
        """
        if not self.use_ccxt_pro or self.exchange is None:
            logger.info(
                f"WebSocket not available for {symbol} OHLCV. "
                "Using polling fallback."
            )
            return
        
        self.is_running = True
        
        try:
            while self.is_running:
                ohlcv = await self.exchange.watch_ohlcv(symbol, timeframe)
                
                if callback:
                    callback(ohlcv)
                
                yield ohlcv
                
        except Exception as e:
            logger.error(f"OHLCV WebSocket error for {symbol}: {e}")
            self.is_running = False
    
    def stop(self):
        """WebSocket 스트림 중지"""
        self.is_running = False
        logger.info("Real-time data feed stopped")
    
    def get_recent_ticks(self, limit: int = 100) -> list:
        """
        최근 틱 데이터 조회
        
        Args:
            limit: 반환할 틱 개수
            
        Returns:
            List[Dict]: 틱 데이터 목록
        """
        return list(self.ticker_buffer)[-limit:]


# 싱글톤 인스턴스
_feed_instance = None


def get_realtime_feed() -> RealtimeDataFeed:
    """글로벌 실시간 데이터 피드 인스턴스 반환"""
    global _feed_instance
    if _feed_instance is None:
        _feed_instance = RealtimeDataFeed()
    return _feed_instance


async def example_usage():
    """사용 예시"""
    feed = RealtimeDataFeed(use_ccxt_pro=False)
    
    def on_ticker(ticker):
        print(f"Received: {ticker['symbol']} @ {ticker['last']}")
    
    # 실시간 틱 스트리밍
    async for ticker in feed.watch_ticker('BTC/KRW', callback=on_ticker):
        print(f"BTC/KRW: {ticker['last']}")
        
        # 10개 틱만 수신 후 중지 (예시)
        if len(feed.ticker_buffer) >= 10:
            feed.stop()
            break


if __name__ == "__main__":
    # 테스트 실행
    asyncio.run(example_usage())
