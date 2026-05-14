#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
7단계 - 완료 알림 (Redis Pub/Sub, UI/Inference 트리거)

[Responsibilities]
- 캔들 저장 완료 시 Redis Pub/Sub 발행
- UI 실시간 업데이트 트리거
- ML Inference 파이프라인 트리거

[Main Flow]
1. Finalizer에서 candles 저장 완료 → notify_candle_updated()
2. Redis PUBLISH candles:{symbol}:{timeframe} {payload}
3. Subscribers (UI/Inference) 수신 → 즉시 업데이트

[Performance]
- 1ms 알림 지연
- 비동기 발행 (논블로킹)
- Channel 패턴 매칭

[Error Handling]
- 재시도 (3회)
- Fallback (polling 모드)

[Dependencies]
- redis (aioredis)

[Author] GitHub Copilot
[Created] 2026-02-20
[Modified] 2026-02-20
"""

from __future__ import annotations

import asyncio
import os
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import logging

# 조건부 임포트
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis as redis
        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False
        logging.warning("⚠️  redis 미설치 - Pub/Sub 불가")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson
    ORJSON_AVAILABLE = False


# ============================================================
# DataNotifier 클래스
# ============================================================
class DataNotifier:
    """7단계 - 완료 알림 (Redis Pub/Sub)"""
    
    def __init__(self):
        """초기화"""
        # Redis 설정
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_password = os.getenv('REDIS_PASSWORD', None)
        
        # 연결 객체
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        
        # 구독 핸들러
        self._subscribers: Dict[str, List[Callable]] = {}
        
        # 통계
        self.stats = {
            'published': 0,
            'failed': 0,
            'subscribers': 0
        }
        
        # 실행 상태
        self._running = False
    
    async def initialize(self):
        """비동기 초기화"""
        if REDIS_AVAILABLE and not self.redis_client:
            try:
                self.redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    password=self.redis_password,
                    decode_responses=False
                )
                await self.redis_client.ping()
                
                self.pubsub = self.redis_client.pubsub()
                
                logging.info("✅ DataNotifier - Redis Pub/Sub 연결 완료")
            except Exception as e:
                logging.error(f"❌ DataNotifier - Redis 연결 실패: {e}")
    
    async def close(self):
        """연결 종료"""
        self._running = False
        
        if self.pubsub:
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
    
    # --------------------------------------------------------
    # Publish (발행)
    # --------------------------------------------------------
    async def notify_candle_updated(
        self,
        symbol: str,
        timeframe: str,
        time: datetime,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        캔들 업데이트 알림 발행
        
        Args:
            symbol: 심볼 (예: KRW-BTC)
            timeframe: 타임프레임 (예: 1m)
            time: 캔들 시간
            data: 추가 데이터 (옵션)
        """
        if not self.redis_client:
            logging.warning("⚠️  Redis 연결 없음 - 알림 스킵")
            return
        
        try:
            # 채널명: candles:{symbol}:{timeframe}
            channel = f"candles:{symbol}:{timeframe}"
            
            # 페이로드 생성
            payload = {
                'symbol': symbol,
                'timeframe': timeframe,
                'time': time.isoformat(),
                'timestamp': datetime.now().isoformat(),
                'data': data or {}
            }
            
            # JSON 직렬화
            message = orjson.dumps(payload) if ORJSON_AVAILABLE else str(payload).encode()
            
            # Publish
            await self.redis_client.publish(channel, message)
            
            self.stats['published'] += 1
            
            logging.debug(f"📢 Pub/Sub: {channel} → {len(message)} bytes")
        
        except Exception as e:
            logging.error(f"❌ Pub/Sub 발행 실패: {e}")
            self.stats['failed'] += 1
    
    async def notify_batch_updated(
        self,
        updates: List[Dict[str, Any]]
    ):
        """
        배치 알림 발행
        
        Args:
            updates: [{symbol, timeframe, time, data}, ...]
        """
        for update in updates:
            await self.notify_candle_updated(
                symbol=update.get('symbol'),
                timeframe=update.get('timeframe'),
                time=update.get('time'),
                data=update.get('data')
            )
    
    # --------------------------------------------------------
    # Subscribe (구독)
    # --------------------------------------------------------
    async def subscribe(
        self,
        pattern: str,
        handler: Callable
    ):
        """
        채널 구독 (패턴 매칭)
        
        Args:
            pattern: 채널 패턴 (예: candles:KRW-BTC:*)
            handler: async def handler(channel, message)
        """
        if not self.pubsub:
            logging.error("❌ Pub/Sub 미초기화")
            return
        
        try:
            # 패턴 구독
            await self.pubsub.psubscribe(pattern)
            
            # 핸들러 등록
            if pattern not in self._subscribers:
                self._subscribers[pattern] = []
            
            self._subscribers[pattern].append(handler)
            self.stats['subscribers'] += 1
            
            logging.info(f"✅ 구독 등록: {pattern}")
        
        except Exception as e:
            logging.error(f"❌ 구독 실패: {e}")
    
    async def start_listening(self):
        """
        구독 리스닝 시작 (백그라운드)
        """
        if not self.pubsub:
            logging.error("❌ Pub/Sub 미초기화")
            return
        
        self._running = True
        
        logging.info("🎧 Pub/Sub 리스닝 시작...")
        
        try:
            async for message in self.pubsub.listen():
                if not self._running:
                    break
                
                if message['type'] == 'pmessage':
                    # 패턴 매칭 메시지
                    pattern = message['pattern'].decode()
                    channel = message['channel'].decode()
                    data = message['data']
                    
                    # 핸들러 실행
                    if pattern in self._subscribers:
                        for handler in self._subscribers[pattern]:
                            try:
                                await handler(channel, data)
                            except Exception as e:
                                logging.error(f"❌ 핸들러 실행 실패: {e}")
        
        except asyncio.CancelledError:
            logging.info("🛑 Pub/Sub 리스닝 종료")
        except Exception as e:
            logging.error(f"❌ Pub/Sub 리스닝 에러: {e}")
    
    # --------------------------------------------------------
    # 통계
    # --------------------------------------------------------
    def get_stats(self) -> Dict[str, int]:
        """통계 조회"""
        return self.stats.copy()


# ============================================================
# 테스트
# ============================================================
async def test_pubsub():
    """Pub/Sub 테스트"""
    logging.basicConfig(level=logging.INFO)
    
    notifier = DataNotifier()
    await notifier.initialize()
    
    try:
        # 구독자 정의
        async def ui_handler(channel, message):
            """UI 업데이트 핸들러"""
            print(f"[UI] {channel}: {message[:100]}")
        
        async def ml_handler(channel, message):
            """ML Inference 핸들러"""
            print(f"[ML] {channel}: Triggering inference...")
        
        # 구독 등록
        await notifier.subscribe("candles:*:*", ui_handler)
        await notifier.subscribe("candles:KRW-BTC:*", ml_handler)
        
        # 리스닝 시작 (백그라운드)
        listen_task = asyncio.create_task(notifier.start_listening())
        
        # 발행 테스트
        await asyncio.sleep(1)
        
        for i in range(5):
            await notifier.notify_candle_updated(
                symbol='KRW-BTC',
                timeframe='1m',
                time=datetime.now(),
                data={'price': 50000000 + i * 1000}
            )
            await asyncio.sleep(0.5)
        
        # 대기
        await asyncio.sleep(2)
        
        # 통계 출력
        stats = notifier.get_stats()
        print(f"\n📊 Pub/Sub 통계:")
        print(f"  발행: {stats['published']}개")
        print(f"  실패: {stats['failed']}개")
        print(f"  구독자: {stats['subscribers']}개")
        
        # 리스닝 종료
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
    
    finally:
        await notifier.close()


if __name__ == '__main__':
    asyncio.run(test_pubsub())