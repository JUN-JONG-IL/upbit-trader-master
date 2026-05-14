#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
6단계 - 최종 저장 (staging_candles → candles hypertable)
7단계 통합 - Redis Pub/Sub 알림
...
"""
from __future__ import annotations

import asyncio
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

# 조건부 임포트
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logging.warning("⚠️  asyncpg 미설치 - TimescaleDB 연결 불가")


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class FinalizeStats:
    """최종 저장 통계"""
    processed: int = 0
    upserted: int = 0
    snapshot_updates: int = 0
    notifications_sent: int = 0  # NEW!
    failed: int = 0
    last_process_time: Optional[datetime] = None


# ============================================================
# DataFinalizer 클래스
# ============================================================
class DataFinalizer:
    """6단계 - 최종 저장 (staging → candles) + 7단계 알림"""
    
    def __init__(self, batch_size: int = 1000, enable_notifications: bool = True):
        """
        초기화
        
        Args:
            batch_size: 배치 크기
            enable_notifications: Pub/Sub 알림 활성화 여부
        """
        # DB 설정
        self.pg_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.pg_port = int(os.getenv('POSTGRES_PORT', 58529))
        self.pg_db = os.getenv('POSTGRES_DB', 'upbit_trader')
        self.pg_user = os.getenv('POSTGRES_USER', 'app_user')
        self.pg_password = os.getenv('POSTGRES_PASSWORD', '')
        
        # 배치 설정
        self.batch_size = batch_size
        self.enable_notifications = enable_notifications
        
        # 연결 객체
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.notifier = None  # DataNotifier (lazy load)
        
        # 통계
        self.stats = FinalizeStats()
        
        # 실행 상태
        self._running = False
    
    async def initialize(self):
        """비동기 초기화"""
        # TimescaleDB 초기화
        if ASYNCPG_AVAILABLE and not self.pg_pool:
            try:
                self.pg_pool = await asyncpg.create_pool(
                    host=self.pg_host,
                    port=self.pg_port,
                    database=self.pg_db,
                    user=self.pg_user,
                    password=self.pg_password,
                    min_size=2,
                    max_size=20,
                    command_timeout=60
                )
                logging.info("✅ DataFinalizer - TimescaleDB 연결 풀 생성")
            except Exception as e:
                logging.error(f"❌ DataFinalizer - TimescaleDB 연결 실패: {e}")
        
        # Notifier 초기화 (선택적)
        if self.enable_notifications:
            try:
                from .notifier import DataNotifier
                self.notifier = DataNotifier()
                await self.notifier.initialize()
                logging.info("✅ DataFinalizer - Pub/Sub 알림 활성화")
            except Exception as e:
                logging.warning(f"⚠️  Pub/Sub 초기화 실패 (계속 진행): {e}")
                self.notifier = None
    
    async def close(self):
        """연결 종료"""
        self._running = False
        
        if self.notifier:
            await self.notifier.close()
        
        if self.pg_pool:
            await self.pg_pool.close()
    
    # --------------------------------------------------------
    # Staging → Candles 처리
    # --------------------------------------------------------
    async def process_batch(self) -> int:
        """
        배치 처리 (staging → candles)
        
        Returns:
            처리된 레코드 수
        """
        if not self.pg_pool:
            logging.error("❌ TimescaleDB 연결 없음")
            return 0
        
        try:
            async with self.pg_pool.acquire() as conn:
                # 1. staging_candles에서 미처리 데이터 조회
                query_select = """
                    SELECT time, symbol, timeframe, open, high, low, close, volume, seq, trades
                    FROM staging_candles
                    WHERE NOT processed
                    ORDER BY received_at
                    LIMIT $1
                """
                
                rows = await conn.fetch(query_select, self.batch_size)
                
                if not rows:
                    return 0
                
                # 2. candles에 upsert
                async with conn.transaction():
                    query_upsert = """
                        INSERT INTO candles (time, symbol, timeframe, open, high, low, close, volume, seq, trades, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                        ON CONFLICT (time, symbol, timeframe)
                        DO UPDATE SET
                            high = GREATEST(candles.high, EXCLUDED.high),
                            low = LEAST(candles.low, EXCLUDED.low),
                            volume = candles.volume + EXCLUDED.volume,
                            trades = COALESCE(candles.trades, 0) + COALESCE(EXCLUDED.trades, 0)
                    """
                    
                    args_list = [
                        (
                            row['time'],
                            row['symbol'],
                            row['timeframe'],
                            row['open'],
                            row['high'],
                            row['low'],
                            row['close'],
                            row['volume'],
                            row['seq'],
                            row['trades']
                        )
                        for row in rows
                    ]
                    
                    await conn.executemany(query_upsert, args_list)
                    
                    # 3. latest_snapshot 업데이트
                    await self._update_snapshot(conn, rows)
                    
                    # 4. staging_candles.processed = true
                    query_update_staging = """
                        UPDATE staging_candles
                        SET processed = true
                        WHERE (time, symbol, timeframe) IN (
                            SELECT time, symbol, timeframe 
                            FROM unnest($1::timestamptz[], $2::text[], $3::text[]) 
                            AS t(time, symbol, timeframe)
                        )
                        AND NOT processed
                    """
                    
                    times = [row['time'] for row in rows]
                    symbols = [row['symbol'] for row in rows]
                    timeframes = [row['timeframe'] for row in rows]
                    
                    await conn.execute(query_update_staging, times, symbols, timeframes)
                
                # 5. Redis Pub/Sub 알림 (NEW!)
                if self.notifier:
                    await self._send_notifications(rows)
                
                # 통계 업데이트
                self.stats.processed += len(rows)
                self.stats.upserted += len(rows)
                self.stats.last_process_time = datetime.now(timezone.utc)
                
                logging.info(f"✅ {len(rows)}개 캔들 최종 저장 완료")
                
                return len(rows)
        
        except Exception as e:
            logging.error(f"❌ Staging 배치 처리 실패: {e}")
            self.stats.failed += 1
            return 0
    
    async def _update_snapshot(self, conn: asyncpg.Connection, rows: List[asyncpg.Record]):
        """
        latest_snapshot 업데이트
        
        Args:
            conn: DB 연결
            rows: 캔들 레코드 리스트
        """
        # symbol, timeframe별로 그룹화
        snapshots = {}
        
        for row in rows:
            key = (row['symbol'], row['timeframe'])
            if key not in snapshots:
                snapshots[key] = {
                    'symbol': row['symbol'],
                    'timeframe': row['timeframe'],
                    'last_time': row['time']
                }
            else:
                # 최신 시간으로 업데이트
                if row['time'] > snapshots[key]['last_time']:
                    snapshots[key]['last_time'] = row['time']
        
        # latest_snapshot 업데이트
        query = """
            INSERT INTO latest_snapshot (symbol, timeframe, last_time, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (symbol, timeframe)
            DO UPDATE SET
                last_time = GREATEST(latest_snapshot.last_time, EXCLUDED.last_time),
                updated_at = NOW()
        """
        
        args_list = [
            (s['symbol'], s['timeframe'], s['last_time'])
            for s in snapshots.values()
        ]
        
        await conn.executemany(query, args_list)
        
        self.stats.snapshot_updates += len(snapshots)
    
    async def _send_notifications(self, rows: List[asyncpg.Record]):
        """
        Redis Pub/Sub 알림 발행 (NEW!)
        
        Args:
            rows: 캔들 레코드 리스트
        """
        if not self.notifier:
            return
        
        try:
            # symbol, timeframe별로 그룹화
            updates = {}
            
            for row in rows:
                key = (row['symbol'], row['timeframe'])
                if key not in updates:
                    updates[key] = {
                        'symbol': row['symbol'],
                        'timeframe': row['timeframe'],
                        'time': row['time'],
                        'data': {
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close'],
                            'volume': row['volume']
                        }
                    }
                else:
                    # 최신 시간으로 업데이트
                    if row['time'] > updates[key]['time']:
                        updates[key]['time'] = row['time']
                        updates[key]['data'] = {
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close'],
                            'volume': row['volume']
                        }
            
            # 배치 알림
            for update in updates.values():
                await self.notifier.notify_candle_updated(
                    symbol=update['symbol'],
                    timeframe=update['timeframe'],
                    time=update['time'],
                    data=update['data']
                )
                self.stats.notifications_sent += 1
            
            logging.debug(f"📢 {len(updates)}개 심볼/TF 알림 발행")
        
        except Exception as e:
            logging.error(f"❌ 알림 발행 실패 (논블로킹): {e}")
    
    # --------------------------------------------------------
    # 연속 실행
    # --------------------------------------------------------
    async def run_continuous(self, interval: float = 1.0):
        """
        연속 실행 (백그라운드 태스크)
        
        Args:
            interval: 실행 간격 (초)
        """
        self._running = True
        
        logging.info(f"✅ DataFinalizer 연속 실행 시작 (interval={interval}s)")
        
        while self._running:
            try:
                count = await self.process_batch()
                
                if count == 0:
                    # 처리할 데이터가 없으면 대기
                    await asyncio.sleep(interval)
                else:
                    # 처리 후 바로 다음 배치 (연속 처리)
                    await asyncio.sleep(0.01)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"❌ 연속 실행 에러: {e}")
                await asyncio.sleep(interval)
        
        logging.info("✅ DataFinalizer 연속 실행 종료")
    
    async def process_all_staging(self) -> int:
        """
        모든 staging 데이터 처리 (한 번에)
        
        Returns:
            총 처리된 레코드 수
        """
        total = 0
        
        logging.info("🔄 Staging 전체 처리 시작...")
        
        while True:
            count = await self.process_batch()
            if count == 0:
                break
            total += count
            
            # 진행 상황 로깅
            if total % 1000 == 0:
                logging.info(f"  처리 중: {total}개...")
        
        logging.info(f"✅ Staging 전체 처리 완료: {total}개")
        return total
    
    # --------------------------------------------------------
    # 통계
    # --------------------------------------------------------
    def get_stats(self) -> FinalizeStats:
        """통계 조회"""
        return self.stats


# ============================================================
# 테스트
# ============================================================
async def main():
    """테스트"""
    logging.basicConfig(level=logging.INFO)
    
    finalizer = DataFinalizer(batch_size=100, enable_notifications=True)
    await finalizer.initialize()
    
    try:
        # 모든 staging 처리
        total = await finalizer.process_all_staging()
        
        print(f"\n✅ 6+7단계 - 최종 저장 + 알림 결과:")
        print(f"  처리: {total}개")
        
        # 통계 출력
        stats = finalizer.get_stats()
        print(f"\n📊 통계:")
        print(f"  처리: {stats.processed}개")
        print(f"  Upserted: {stats.upserted}개")
        print(f"  Snapshot 업데이트: {stats.snapshot_updates}개")
        print(f"  알림 발행: {stats.notifications_sent}개")  # NEW!
        print(f"  실패: {stats.failed}개")
    
    finally:
        await finalizer.close()


if __name__ == '__main__':
    asyncio.run(main())