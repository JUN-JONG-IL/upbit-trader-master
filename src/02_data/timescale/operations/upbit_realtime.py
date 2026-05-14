#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
Upbit WebSocket 실시간 연동 → 데이터 파이프라인 통합

[Responsibilities]
- Upbit WebSocket 연결 (Ticker/Trade)
- 실시간 데이터 → Stager → Finalizer → Pub/Sub
- 자동 재연결 (Exponential Backoff)
- 멀티 심볼 구독

[Main Flow]
1. WebSocket 연결 (wss://api.upbit.com/websocket/v1)
2. 구독 메시지 전송 [{"ticket":"..."}, {"type":"ticker","codes":[...]}]
3. 메시지 수신 → 파싱 → Stager.add_candle()
4. Stager → Finalizer → Pub/Sub (자동)

[Performance]
- 비동기 수신 (10ms 지연)
- 자동 재연결 (Exponential Backoff: 1s → 2s → 4s → ...)
- Circuit Breaker (연속 실패 5회 → 60s 타임아웃)

[Error Handling]
- 재연결 로직
- 메시지 파싱 실패 → 로깅
- 연결 끊김 감지 (heartbeat)

[Dependencies]
- websockets (async)
- aiohttp (optional)

[Author] GitHub Copilot
[Created] 2026-02-20
[Modified] 2026-02-20
"""

import asyncio
import uuid
import logging
from typing import List, Optional, Callable
from datetime import datetime
import json

# 조건부 임포트
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logging.warning("⚠️  websockets 미설치 - WebSocket 연결 불가")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson
    ORJSON_AVAILABLE = False


# ============================================================
# UpbitRealtimeClient 클래스
# ============================================================
class UpbitRealtimeClient:
    """Upbit WebSocket 실시간 클라이언트"""
    
    def __init__(self, symbols: List[str], data_callback: Optional[Callable] = None):
        """
        초기화
        
        Args:
            symbols: 심볼 리스트 (예: ['KRW-BTC', 'KRW-ETH'])
            data_callback: async def callback(data: dict)
        """
        # WebSocket 설정
        self.ws_url = "wss://api.upbit.com/websocket/v1"
        self.symbols = symbols
        self.data_callback = data_callback
        
        # 연결 객체
        self.websocket = None
        
        # 재연결 설정
        self.max_reconnect_delay = 60  # 최대 60초
        self.reconnect_delay = 1  # 초기 1초
        self.max_failures = 5  # 연속 실패 5회
        self.failure_count = 0
        
        # 통계
        self.stats = {
            'messages': 0,
            'errors': 0,
            'reconnects': 0,
            'last_message_time': None
        }
        
        # 실행 상태
        self._running = False
    
    # --------------------------------------------------------
    # 연결
    # --------------------------------------------------------
    async def connect(self):
        """WebSocket 연결"""
        if not WEBSOCKETS_AVAILABLE:
            logging.error("❌ websockets 패키지 미설치")
            return
        
        try:
            logging.info(f"🔌 Upbit WebSocket 연결 중... ({len(self.symbols)}개 심볼)")
            
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10
            )
            
            # 구독 메시지 전송
            await self._subscribe()
            
            logging.info("✅ Upbit WebSocket 연결 완료")
            
            # 재연결 카운터 리셋
            self.reconnect_delay = 1
            self.failure_count = 0
        
        except Exception as e:
            logging.error(f"❌ WebSocket 연결 실패: {e}")
            self.failure_count += 1
            raise
    
    async def _subscribe(self):
        """구독 메시지 전송"""
        if not self.websocket:
            return
        
        # Upbit WebSocket 구독 형식
        subscribe_msg = [
            {"ticket": str(uuid.uuid4())},
            {
                "type": "ticker",  # ticker | trade | orderbook
                "codes": self.symbols,
                "isOnlyRealtime": True
            }
        ]
        
        message = json.dumps(subscribe_msg)
        await self.websocket.send(message)
        
        logging.info(f"📡 구독 완료: {self.symbols}")
    
    async def disconnect(self):
        """WebSocket 연결 종료"""
        self._running = False
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        logging.info("🔌 WebSocket 연결 종료")
    
    # --------------------------------------------------------
    # 메시지 수신
    # --------------------------------------------------------
    async def start(self):
        """메시지 수신 시작 (자동 재연결)"""
        self._running = True
        
        while self._running:
            try:
                # 연결
                await self.connect()
                
                # 메시지 수신 루프
                async for message in self.websocket:
                    if not self._running:
                        break
                    
                    await self._handle_message(message)
            
            except asyncio.CancelledError:
                logging.info("🛑 WebSocket 수신 종료 (CancelledError)")
                break
            
            except Exception as e:
                logging.error(f"❌ WebSocket 에러: {e}")
                self.stats['errors'] += 1
                
                # Circuit Breaker
                if self.failure_count >= self.max_failures:
                    logging.error(f"🚨 연속 실패 {self.max_failures}회 → {self.max_reconnect_delay}초 대기")
                    await asyncio.sleep(self.max_reconnect_delay)
                    self.failure_count = 0
                else:
                    # Exponential Backoff
                    delay = min(self.reconnect_delay, self.max_reconnect_delay)
                    logging.info(f"🔄 재연결 대기: {delay}초...")
                    await asyncio.sleep(delay)
                    self.reconnect_delay *= 2
                    self.stats['reconnects'] += 1
            
            finally:
                if self.websocket:
                    await self.websocket.close()
                    self.websocket = None
    
    async def _handle_message(self, message):
        """
        메시지 처리
        
        Args:
            message: WebSocket 메시지 (bytes)
        """
        try:
            # JSON 파싱
            if ORJSON_AVAILABLE:
                data = orjson.loads(message)
            else:
                data = json.loads(message.decode('utf-8'))
            
            # 통계 업데이트
            self.stats['messages'] += 1
            self.stats['last_message_time'] = datetime.now()
            
            # 콜백 실행
            if self.data_callback:
                await self.data_callback(data)
            
            # 디버그 로그
            if self.stats['messages'] % 100 == 0:
                logging.debug(f"📊 수신: {self.stats['messages']}개")
        
        except Exception as e:
            logging.error(f"❌ 메시지 처리 실패: {e}")
            self.stats['errors'] += 1
    
    # --------------------------------------------------------
    # 통계
    # --------------------------------------------------------
    def get_stats(self):
        """통계 조회"""
        return self.stats.copy()


# ============================================================
# 통합 클래스 (WebSocket → Stager → Finalizer)
# ============================================================
class UpbitRealtimePipeline:
    """Upbit 실시간 파이프라인 (WebSocket → Stager → Finalizer)"""
    
    def __init__(self, symbols: List[str]):
        """
        초기화
        
        Args:
            symbols: 심볼 리스트 (예: ['KRW-BTC', 'KRW-ETH'])
        """
        self.symbols = symbols
        
        # 컴포넌트
        self.ws_client = None
        self.stager = None
        self.finalizer = None
        
        # 태스크
        self._ws_task: Optional[asyncio.Task] = None
        self._finalizer_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """초기화"""
        from .stager import DataStager
        from .finalizer import DataFinalizer
        
        # Stager 초기화
        self.stager = DataStager(batch_size=1000, flush_interval=1.0)
        await self.stager.initialize()
        
        # Finalizer 초기화 (Pub/Sub 활성화)
        self.finalizer = DataFinalizer(batch_size=1000, enable_notifications=True)
        await self.finalizer.initialize()
        
        # WebSocket 클라이언트 생성
        self.ws_client = UpbitRealtimeClient(
            symbols=self.symbols,
            data_callback=self._on_ticker_data
        )
        
        logging.info("✅ 실시간 파이프라인 초기화 완료")
    
    async def _on_ticker_data(self, data: dict):
        """
        Ticker 데이터 수신 콜백
        
        Args:
            data: Upbit ticker 데이터
        """
        try:
            # Upbit ticker 형식 변환
            candle_data = {
                'market': data.get('code'),  # 예: KRW-BTC
                'timeframe': '1m',  # 실시간은 1분으로 집계
                'candle_date_time_kst': datetime.fromtimestamp(data.get('timestamp') / 1000).isoformat(),
                'opening_price': data.get('opening_price'),
                'high_price': data.get('high_price'),
                'low_price': data.get('low_price'),
                'trade_price': data.get('trade_price'),
                'candle_acc_trade_volume': data.get('acc_trade_volume_24h'),
                'seq': data.get('sequential_id'),
                'trades': None
            }
            
            # Stager에 추가
            await self.stager.add_candle(candle_data)
        
        except Exception as e:
            logging.error(f"❌ Ticker 처리 실패: {e}")
    
    async def start(self):
        """파이프라인 시작"""
        logging.info("🚀 실시간 파이프라인 시작...")
        
        # WebSocket 시작 (백그라운드)
        self._ws_task = asyncio.create_task(self.ws_client.start())
        
        # Finalizer 연속 실행 (백그라운드)
        self._finalizer_task = asyncio.create_task(
            self.finalizer.run_continuous(interval=1.0)
        )
        
        logging.info("✅ 실시간 파이프라인 실행 중...")
    
    async def stop(self):
        """파이프라인 중지"""
        logging.info("🛑 실시간 파이프라인 중지 중...")
        
        # WebSocket 중지
        if self.ws_client:
            await self.ws_client.disconnect()
        
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        # Finalizer 중지
        if self._finalizer_task:
            self._finalizer_task.cancel()
            try:
                await self._finalizer_task
            except asyncio.CancelledError:
                pass
        
        # 종료
        if self.stager:
            await self.stager.close()
        
        if self.finalizer:
            await self.finalizer.close()
        
        logging.info("✅ 실시간 파이프라인 중지 완료")
    
    def get_stats(self):
        """통계 조회"""
        return {
            'websocket': self.ws_client.get_stats() if self.ws_client else {},
            'stager': self.stager.get_stats() if self.stager else {},
            'finalizer': self.finalizer.get_stats() if self.finalizer else {}
        }


# ============================================================
# 테스트
# ============================================================
async def main():
    """실시간 파이프라인 테스트"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 심볼 설정
    symbols = ['KRW-BTC', 'KRW-ETH']
    
    # 파이프라인 생성
    pipeline = UpbitRealtimePipeline(symbols=symbols)
    await pipeline.initialize()
    
    try:
        # 시작
        await pipeline.start()
        
        # 30초 실행
        logging.info("⏱️  30초 동안 실시간 수신 중...")
        await asyncio.sleep(30)
        
        # 통계 출력
        stats = pipeline.get_stats()
        
        print("\n" + "="*70)
        print("📊 실시간 파이프라인 통계")
        print("="*70)
        
        ws_stats = stats.get('websocket', {})
        print(f"\n[WebSocket]")
        print(f"  수신: {ws_stats.get('messages', 0)}개")
        print(f"  에러: {ws_stats.get('errors', 0)}개")
        print(f"  재연결: {ws_stats.get('reconnects', 0)}회")
        
        stager_stats = stats.get('stager', {})
        print(f"\n[Stager]")
        print(f"  수신: {stager_stats.received_count}개")
        print(f"  저장: {stager_stats.inserted_count}개")
        
        finalizer_stats = stats.get('finalizer', {})
        print(f"\n[Finalizer]")
        print(f"  처리: {finalizer_stats.processed}개")
        print(f"  Upserted: {finalizer_stats.upserted}개")
        print(f"  알림: {finalizer_stats.notifications_sent}개")
        
        print("="*70 + "\n")
    
    finally:
        await pipeline.stop()


if __name__ == '__main__':
    asyncio.run(main())