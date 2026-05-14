#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터 파이프라인 통합 (1~6단계 완전 자동화)

[Flow]
1. DataChecker: DB 보유 여부 확인 (L0~L3 캐시)
2. Receiver: 실시간 WS 또는 백필 API
3. Stager: 임시 저장 (staging_candles)
4. Validator: 정합성 검증
5. IsolationHandler: 이상 처리 (격리/Gap 큐잉)
6. Finalizer: 최종 저장 (candles hypertable)

[Author] GitHub Copilot
[Created] 2026-02-20
[Modified] 2026-03-02
"""

import asyncio
import logging
from typing import List, Optional

from .operations.checker import DataChecker
from .operations.receiver import UpbitReceiver, ReceiverConfig, ExchangeType, DataType, ReceivedData
from .operations.stager import DataStager, StagingCandle
from .operations.validator import CandleValidator, CandleData
from .operations.isolator import IsolationHandler, IsolatedCandle, GapFillTask
from .operations.finalizer import DataFinalizer


class DataPipeline:
    """데이터 파이프라인 (1~6단계 완전 통합)"""

    def __init__(
        self,
        batch_size: int = 1000,
        flush_interval: float = 1.0,
        zscore_threshold: float = 3.0
    ):
        self.checker = DataChecker()
        self.receiver: Optional[UpbitReceiver] = None
        self.stager = DataStager(batch_size=batch_size, flush_interval=flush_interval)
        self.validator = CandleValidator(zscore_threshold=zscore_threshold)
        self.isolator = IsolationHandler()
        self.finalizer = DataFinalizer(batch_size=batch_size)
        self._finalizer_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self):
        """초기화 (모든 컴포넌트)"""
        await self.checker.initialize()
        await self.stager.initialize()
        await self.isolator.initialize()
        await self.finalizer.initialize()
        logging.info("✅ 데이터 파이프라인 초기화 완료 (1~6단계)")

    async def close(self):
        """종료"""
        self._running = False
        if self._finalizer_task:
            self._finalizer_task.cancel()
            try:
                await self._finalizer_task
            except asyncio.CancelledError:
                pass
        await self.checker.close()
        await self.stager.close()
        await self.isolator.close()
        await self.finalizer.close()
        if self.receiver:
            await self.receiver.close()
        logging.info("✅ 데이터 파이프라인 종료 완료")

    async def on_received_data(self, data: ReceivedData):
        """수신 데이터 처리 콜백"""
        try:
            candle_dict = {
                'market': data.symbol,
                'timeframe': '1m',
                'candle_date_time_kst': data.timestamp.isoformat(),
                'opening_price': data.data.get('opening_price', 0),
                'high_price': data.data.get('high_price', 0),
                'low_price': data.data.get('low_price', 0),
                'trade_price': data.data.get('trade_price', 0),
                'candle_acc_trade_volume': data.data.get('candle_acc_trade_volume', 0),
                'seq': data.data.get('seq'),
                'exchange': data.exchange,
            }
            await self.stager.add_candle(candle_dict)

            candle_data = CandleData(
                symbol=data.symbol, timeframe='1m', time=data.timestamp,
                open=float(data.data.get('opening_price', 0)),
                high=float(data.data.get('high_price', 0)),
                low=float(data.data.get('low_price', 0)),
                close=float(data.data.get('trade_price', 0)),
                volume=float(data.data.get('candle_acc_trade_volume', 0)),
                seq=data.data.get('seq'),
            )
            result = self.validator.validate_ohlc(candle_data)
            if not result.valid:
                isolated = IsolatedCandle(
                    symbol=data.symbol, timeframe='1m', time=data.timestamp,
                    open=candle_data.open, high=candle_data.high,
                    low=candle_data.low, close=candle_data.close,
                    volume=candle_data.volume, seq=candle_data.seq,
                    exchange=data.exchange, raw_data=data.raw,
                    isolation_reason='; '.join(result.errors),
                )
                await self.isolator.isolate_candle(isolated)
                logging.warning("⚠️  이상 데이터 격리: %s @ %s", data.symbol, data.timestamp)
        except Exception as e:
            logging.error("❌ 데이터 처리 실패: %s", e)

    async def start_realtime(self, symbols: List[str]):
        """실시간 수신 시작"""
        if self.receiver:
            logging.warning("⚠️  이미 수신기가 실행 중입니다")
            return
        config = ReceiverConfig(
            exchange=ExchangeType.UPBIT, symbols=symbols, data_type=DataType.TICKER
        )
        self.receiver = UpbitReceiver(config)
        await self.receiver.initialize()
        self.receiver.set_callback(self.on_received_data)
        self._running = True
        self._finalizer_task = asyncio.create_task(
            self.finalizer.run_continuous(interval=1.0)
        )
        logging.info("✅ 실시간 수신 시작: %s", symbols)
        await self.receiver.start_websocket()

    async def backfill_gaps(self, max_tasks: int = 10):
        """Gap 백필 실행"""
        logging.info("🔄 Gap 백필 시작...")
        while True:
            tasks = await self.isolator.dequeue_gaps(count=max_tasks)
            if not tasks:
                logging.info("✅ Gap 큐 비어있음")
                break
            logging.info("📥 %d개 Gap 태스크 처리 중...", len(tasks))
            await asyncio.gather(*[self._backfill_single_gap(task) for task in tasks])

    async def _backfill_single_gap(self, task: GapFillTask):
        """단일 Gap 백필"""
        try:
            logging.info(
                "🔄 Gap 백필: %s %s %s ~ %s (우선순위: %s)",
                task.symbol, task.timeframe, task.gap_start, task.gap_end, task.priority,
            )
            if not self.receiver:
                config = ReceiverConfig(
                    exchange=ExchangeType.UPBIT, symbols=[task.symbol], data_type=DataType.CANDLE
                )
                self.receiver = UpbitReceiver(config)
                await self.receiver.initialize()
                self.receiver.set_callback(self.on_received_data)
            await self.receiver.backfill(task.gap_start, task.gap_end)
            logging.info("✅ Gap 백필 완료: %s", task.symbol)
        except Exception as e:
            logging.error("❌ Gap 백필 실패: %s - %s", task.symbol, e)
            task.priority = 'LOW'
            await self.isolator.enqueue_gap(task)

    def print_stats(self):
        """전체 통계 출력"""
        print("\n" + "="*60)
        print("📊 데이터 파이프라인 통계")
        print("="*60)
        stager_stats = self.stager.get_stats()
        print(f"\n[3단계] Stager:")
        print(f"  수신: {stager_stats.received_count}개, 저장: {stager_stats.inserted_count}개")
        validator_stats = self.validator.get_stats()
        print(f"\n[4단계] Validator:")
        print(f"  검증: {validator_stats['validated']}개, 통과: {validator_stats['passed']}개")
        isolator_stats = self.isolator.get_stats()
        print(f"\n[5단계] Isolator:")
        print(f"  격리: {isolator_stats['isolated']}개")
        finalizer_stats = self.finalizer.get_stats()
        print(f"\n[6단계] Finalizer:")
        print(f"  처리: {finalizer_stats.processed}개, Upserted: {finalizer_stats.upserted}개")
        print("="*60 + "\n")


async def main():
    logging.basicConfig(level=logging.INFO)
    pipeline = DataPipeline(batch_size=1000, flush_interval=1.0, zscore_threshold=3.0)
    await pipeline.initialize()
    try:
        await asyncio.wait_for(
            pipeline.start_realtime(['KRW-BTC', 'KRW-ETH']), timeout=10.0
        )
    except asyncio.TimeoutError:
        logging.info("⏱️  테스트 시간 종료")
    finally:
        pipeline.print_stats()
        await pipeline.close()


if __name__ == '__main__':
    asyncio.run(main())
