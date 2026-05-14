#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 변동성 돌파 전략 구현
[Responsibilities]
- 최적 코인 목록 탐색, k값 계산, 목표가 계산, 주문 실행
"""

import time
import datetime
import asyncio as aio
import numpy as np
import aiopyupbit
import polars as pl
import dask.dataframe as dd
import orjson
import redis

try:
    import server.static as static
    from server.static import log
    from utils.helpers import Coin
except ImportError:
    import logging
    log = logging.getLogger(__name__)
    Coin = object

import backtrader as bt
import pandas as pd

from ..core.base_strategy import BaseStrategy
from multiprocessing import Queue


class VolatilityBreakoutStrategy(BaseStrategy):
    """변동성 돌파 전략"""

    def __init__(self, queue: Queue, period: str = 'day') -> None:
        super().__init__(queue=queue)
        self.period = period

    def run(self) -> None:
        log.info('Start volatility breakout strategy thread')
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        loop.run_until_complete(self.__loop())

    def terminate(self) -> None:
        log.info('Stop volatility breakout strategy thread')
        self.alive = False

    async def get_best_coin_list(self):
        log.info('Find best target coins, it will spend 60 sec...')
        while True:
            candidate_list = []
            for coin in static.chart.codes:
                df = await aiopyupbit.get_ohlcv(coin, interval=self.period, count=20)
                ddf = dd.from_polars(pl.DataFrame(df.to_dict(as_series=False)), npartitions=4)
                avg_5 = self.get_average(ddf['close'].compute().to_numpy(), unit=5)
                avg_10 = self.get_average(ddf['close'].compute().to_numpy(), unit=10)
                avg_20 = self.get_average(ddf['close'].compute().to_numpy(), unit=20)
                if (avg_5 > avg_10) and (avg_10 > avg_20):
                    candidate_list.append(coin)
                time.sleep(0.2)
            if candidate_list:
                break
            log.info('Cannot find best target coins, it will re-working again...')
        return [x for x in static.chart.coins.values() if x.code in candidate_list]

    async def get_best_k(self, code: str):
        df = await aiopyupbit.get_ohlcv(code, interval=self.period, count=21)
        time.sleep(0.5)
        df = df.iloc[:-1]
        ddf = dd.from_polars(pl.DataFrame(df.to_dict(as_series=False)), npartitions=4)
        high = ddf['high'].compute().to_numpy()
        low = ddf['low'].compute().to_numpy()
        open_ = ddf['open'].compute().to_numpy()
        close = ddf['close'].compute().to_numpy()
        hl_range = high - low
        # 고가=저가인 캔들(range=0)은 noise=1(완전 노이즈)로 처리
        noise_arr = np.where(hl_range > 0, 1 - abs(open_ - close) / hl_range, 1.0)
        return np.mean(noise_arr)

    async def get_target_price(self, coin: str, k: float):
        df = await aiopyupbit.get_ohlcv(ticker=coin, interval=self.period, count=2)
        previous_candle = df.iloc[-2]
        return previous_candle['close'] + (previous_candle['high'] - previous_candle['low']) * k

    async def __get_check_list(self, target_price: dict) -> list:
        return [aio.create_task(self.__is_reached(x, target_price[x.code])) for x in self.coin_list]

    async def __loop(self):
        while self.alive:
            self.coin_list = await self.get_best_coin_list()
            k_dict = {x.code: await self.get_best_k(x.code) for x in self.coin_list}
            target_price = {x.code: await self.get_target_price(x.code, k_dict[x.code]) for x in self.coin_list}
            self.redis_client.set("strategy:k_dict", orjson.dumps(k_dict))
            self.redis_client.set("strategy:target_price", orjson.dumps(target_price))
            log.info(f'k: {k_dict}\n'
                     f'target_price: {target_price}')
            now = datetime.datetime.now()
            end_time = datetime.datetime.now().replace(hour=static.STRATEGY_DAILY_FINISH_TIME,
                                                       minute=0, second=0, microsecond=0)
            if now.hour > static.STRATEGY_DAILY_FINISH_TIME:
                end_time = end_time + datetime.timedelta(days=1)
            log.info(f'Volatility breakout strategy finish at {end_time}')
            while datetime.datetime.now() < end_time:
                check_list = await self.__get_check_list(target_price=target_price)
                check_result = list(filter(None, await aio.gather(*check_list)))
                log.info(f'check_result: {check_result}')
                for code in check_result:
                    self.send_signal(code=code, position='bid',
                                     type='limit', price=target_price)
                time.sleep(1)
            for coin in self.coin_list:
                self.send_signal(code=coin.code, position='ask',
                                 type='market', price=-1)
            self.send_signal(None, None, None, None)

    async def __is_reached(self, coin: Coin, target_price: float):
        log.info(
            f'code: {coin.code}, target_price: {target_price}, current_price: {coin.get_trade_price()}')
        return coin.code if coin.get_trade_price() >= target_price else None

    def backtest(self, data):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(bt.Strategy)
        dat = bt.feeds.PandasData(dataname=pd.DataFrame(data))
        cerebro.adddata(dat)
        cerebro.run()
        return cerebro.getstrategy()
