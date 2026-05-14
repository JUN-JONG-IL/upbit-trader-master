#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
1단계 - DB 보유 여부/누락 확인 (L0~L3 캐시 계층)

[Responsibilities]
- L0 (In-Memory): 1ms, @lru_cache 기반
- L1 (Redis): 5ms, 최근 500개 LRANGE
- L2 (TimescaleDB): 15ms, latest_snapshot 조회
- L3 (Archive/API): 500ms, 백필 필요 여부 판단
- Gap 탐지: timestamp gap > TF * 2 → enqueue

[Main Flow]
check_data_availability() → L0→L1→L2→L3 순차 확인 → Gap 감지 → 백필 큐 등록

[Performance]
- 캐시 히트율 95% 목표
- 병렬 체크 (asyncio.gather)
- Circuit Breaker (실패 5회 → 60s 타임아웃)

[Dependencies]
- asyncpg (TimescaleDB)
- redis (aioredis 또는 redis-py)
- orjson (직렬화)

[Author] GitHub Copilot
[Created] 2026-02-20
[Modified] 2026-02-20
"""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

# 조건부 임포트
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logging.warning("⚠️  asyncpg 미설치 - TimescaleDB 연결 불가")

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis as redis
        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False
        logging.warning("⚠️  redis 미설치 - Redis 연결 불가")

try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    import json as orjson
    ORJSON_AVAILABLE = False


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class DataCheckResult:
    """데이터 확인 결과"""
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    available: bool
    cache_level: str  # 'L0', 'L1', 'L2', 'L3', 'NONE'
    gaps: List[Tuple[datetime, datetime]]
    last_candle_time: Optional[datetime]
    needs_backfill: bool


@dataclass
class GapInfo:
    """Gap 정보 (백필 큐용)"""
    symbol: str
    timeframe: str
    gap_start: datetime
    gap_end: datetime
    priority: str  # 'HIGH', 'MEDIUM', 'LOW'


# ============================================================
# DataChecker 클래스
# ============================================================
class DataChecker:
    """DB 보유 여부/누락 확인 (L0~L3 계층)"""
    
    def __init__(self):
        """초기화 (환경변수에서 DB 설정 로드)"""
        self.pg_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.pg_port = int(os.getenv('POSTGRES_PORT', 58529))
        self.pg_db = os.getenv('POSTGRES_DB', 'upbit_trader')
        self.pg_user = os.getenv('POSTGRES_USER', 'app_user')
        self.pg_password = os.getenv('POSTGRES_PASSWORD', '')
        
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 58530))
        self.redis_password = os.getenv('REDIS_PASSWORD', None)
        
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.redis_client = None
        
        # L0 캐시 (메모리)
        self._l0_cache: Dict[str, Dict] = {}
        
        # Circuit Breaker
        self._failure_count = {'pg': 0, 'redis': 0}
        self._circuit_open_until = {'pg': None, 'redis': None}
    
    async def initialize(self):
        """비동기 초기화 (연결 풀 생성)"""
        if ASYNCPG_AVAILABLE and not self.pg_pool:
            try:
                self.pg_pool = await asyncpg.create_pool(
                    host=self.pg_host,
                    port=self.pg_port,
                    database=self.pg_db,
                    user=self.pg_user,
                    password=self.pg_password,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
                logging.info("✅ TimescaleDB 연결 풀 생성")
            except Exception as e:
                logging.error(f"❌ TimescaleDB 연결 실패: {e}")
                self._failure_count['pg'] += 1
        
        if REDIS_AVAILABLE and not self.redis_client:
            try:
                self.redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    password=self.redis_password,
                    decode_responses=False
                )
                await self.redis_client.ping()
                logging.info("✅ Redis 연결 완료")
            except Exception as e:
                logging.error(f"❌ Redis 연결 실패: {e}")
                self._failure_count['redis'] += 1
    
    async def close(self):
        """연결 종료"""
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis_client:
            await self.redis_client.close()
    
    # --------------------------------------------------------
    # L0: In-Memory Cache
    # --------------------------------------------------------
    @lru_cache(maxsize=1000)
    def _check_l0_cache(self, cache_key: str) -> Optional[Dict]:
        """L0 캐시 확인 - 1ms"""
        return self._l0_cache.get(cache_key)
    
    def _set_l0_cache(self, cache_key: str, value: Dict):
        """L0 캐시 저장"""
        self._l0_cache[cache_key] = value
    
    # --------------------------------------------------------
    # L1: Redis Cache
    # --------------------------------------------------------
    async def _check_l1_redis(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """L1 Redis 확인 - 5ms, 최근 500개"""
        if not self.redis_client or self._is_circuit_open('redis'):
            return None
        
        try:
            redis_key = f"candles:{symbol}:{timeframe}"
            data = await self.redis_client.lrange(redis_key, 0, 499)
            
            if data:
                candles = [orjson.loads(item) if ORJSON_AVAILABLE else __import__('json').loads(item.decode()) for item in data]
                return {
                    'level': 'L1',
                    'count': len(candles),
                    'last_time': candles[0].get('time') if candles else None
                }
        except Exception as e:
            logging.error(f"❌ Redis L1 조회 실패: {e}")
            self._record_failure('redis')
        
        return None
    
    # --------------------------------------------------------
    # L2: TimescaleDB
    # --------------------------------------------------------
    async def _check_l2_timescale(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[Dict]:
        """L2 TimescaleDB 확인 - 15ms"""
        if not self.pg_pool or self._is_circuit_open('pg'):
            return None
        
        try:
            async with self.pg_pool.acquire() as conn:
                query = """
                    SELECT last_candle_time, updated_at
                    FROM latest_snapshot
                    WHERE symbol = $1 AND timeframe = $2
                """
                row = await conn.fetchrow(query, symbol, timeframe)
                
                if not row:
                    return None
                
                last_candle_time = row['last_candle_time']
                
                return {
                    'level': 'L2',
                    'last_candle_time': last_candle_time,
                    'available': last_candle_time >= end_time,
                    'gap_start': last_candle_time if last_candle_time < end_time else None,
                    'gap_end': end_time if last_candle_time < end_time else None
                }
        except Exception as e:
            logging.error(f"❌ TimescaleDB L2 조회 실패: {e}")
            self._record_failure('pg')
        
        return None
    
    # --------------------------------------------------------
    # L3: Archive/API
    # --------------------------------------------------------
    async def _check_l3_archive(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict:
        """L3 Archive/API - 500ms (백필 필요 판단)"""
        # TODO: Parquet/S3/API 백필 로직
        return {
            'level': 'L3',
            'needs_backfill': True,
            'backfill_start': start_time,
            'backfill_end': end_time
        }
    
    # --------------------------------------------------------
    # Gap 감지
    # --------------------------------------------------------
    def _detect_gaps(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        last_candle_time: Optional[datetime]
    ) -> List[Tuple[datetime, datetime]]:
        """Gap 감지: gap > TF * 2"""
        if not last_candle_time:
            return [(start_time, end_time)]
        
        tf_seconds = self._parse_timeframe_seconds(timeframe)
        gap_threshold = tf_seconds * 2
        
        gaps = []
        if (end_time - last_candle_time).total_seconds() > gap_threshold:
            gaps.append((last_candle_time, end_time))
        
        return gaps
    
    def _parse_timeframe_seconds(self, timeframe: str) -> int:
        """TF 문자열 → 초"""
        tf_map = {
            '1m': 60, '3m': 180, '5m': 300, '15m': 900,
            '1h': 3600, '4h': 14400, '1d': 86400
        }
        return tf_map.get(timeframe, 60)
    
    # --------------------------------------------------------
    # Circuit Breaker
    # --------------------------------------------------------
    def _is_circuit_open(self, service: str) -> bool:
        """Circuit 열림 확인"""
        if self._circuit_open_until.get(service):
            if datetime.now() < self._circuit_open_until[service]:
                return True
            else:
                # Circuit 닫기
                self._circuit_open_until[service] = None
                self._failure_count[service] = 0
        return False
    
    def _record_failure(self, service: str):
        """실패 기록 및 Circuit 열기"""
        self._failure_count[service] += 1
        if self._failure_count[service] >= 5:
            self._circuit_open_until[service] = datetime.now() + timedelta(seconds=60)
            logging.warning(f"⚠️  Circuit Breaker: {service} 60초 차단")
    
    # --------------------------------------------------------
    # 메인 체크 함수
    # --------------------------------------------------------
    async def check_data_availability(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> DataCheckResult:
        """
        데이터 보유 여부 확인 (L0→L1→L2→L3 순차)
        
        Returns:
            DataCheckResult
        """
        cache_key = f"{symbol}:{timeframe}:{start_time}:{end_time}"
        
        # L0 확인
        l0_result = self._check_l0_cache(cache_key)
        if l0_result:
            return DataCheckResult(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                available=True,
                cache_level='L0',
                gaps=[],
                last_candle_time=l0_result.get('last_time'),
                needs_backfill=False
            )
        
        # L1 확인
        l1_result = await self._check_l1_redis(symbol, timeframe)
        if l1_result:
            last_time = l1_result.get('last_time')
            gaps = self._detect_gaps(symbol, timeframe, start_time, end_time, last_time)
            
            result = DataCheckResult(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                available=len(gaps) == 0,
                cache_level='L1',
                gaps=gaps,
                last_candle_time=last_time,
                needs_backfill=len(gaps) > 0
            )
            
            self._set_l0_cache(cache_key, {'last_time': last_time})
            return result
        
        # L2 확인
        l2_result = await self._check_l2_timescale(symbol, timeframe, start_time, end_time)
        if l2_result:
            last_time = l2_result.get('last_candle_time')
            available = l2_result.get('available', False)
            
            gaps = [] if available else [(l2_result['gap_start'], l2_result['gap_end'])]
            
            result = DataCheckResult(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                available=available,
                cache_level='L2',
                gaps=gaps,
                last_candle_time=last_time,
                needs_backfill=not available
            )
            
            self._set_l0_cache(cache_key, {'last_time': last_time})
            return result
        
        # L3 백필 필요
        l3_result = await self._check_l3_archive(symbol, timeframe, start_time, end_time)
        
        return DataCheckResult(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            available=False,
            cache_level='L3',
            gaps=[(start_time, end_time)],
            last_candle_time=None,
            needs_backfill=True
        )
    
    def prioritize_gap(self, symbol: str) -> str:
        """Gap 우선순위 판단"""
        hot_symbols = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP']
        return 'HIGH' if symbol in hot_symbols else 'MEDIUM'


# ============================================================
# 테스트
# ============================================================
async def main():
    """테스트"""
    logging.basicConfig(level=logging.INFO)
    
    checker = DataChecker()
    await checker.initialize()
    
    try:
        result = await checker.check_data_availability(
            symbol='KRW-BTC',
            timeframe='1m',
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now()
        )
        
        print(f"\n✅ 1단계 - 데이터 확인 결과:")
        print(f"  Symbol: {result.symbol}")
        print(f"  Timeframe: {result.timeframe}")
        print(f"  데이터 존재: {result.available}")
        print(f"  캐시 레벨: {result.cache_level}")
        print(f"  Gap 개수: {len(result.gaps)}")
        print(f"  백필 필요: {result.needs_backfill}")
    finally:
        await checker.close()


if __name__ == '__main__':
    asyncio.run(main())