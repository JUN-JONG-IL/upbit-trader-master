#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 다양한 지표 기반 전략 구현 (RSI, 거래량 등)
"""

import time
import datetime
import asyncio as aio
import numpy as np
import aiopyupbit
from pandas.core.frame import DataFrame
import polars as pl
import dask.dataframe as dd
import talib
import orjson
import redis

try:
    import server.static as static
    from server.static import log
except ImportError:
    import logging
    log = logging.getLogger(__name__)

from ..core.base_strategy import BaseStrategy
from multiprocessing import Queue


class VariousIndicatorStrategy(BaseStrategy):
    """다양한 기술 지표 기반 전략 (RSI + 거래량)"""

    def __init__(self, queue: Queue, period: int = 14, rsi: int = 35) -> None:
        super().__init__(queue=queue)
        self.period = period
        self.rsi = rsi

    def run(self) -> None:
        log.info('Start various indicator strategy thread')
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        loop.run_until_complete(self.__loop())

    def terminate(self) -> None:
        log.info('Stop various indicator strategy thread')
        self.alive = False

    async def get_best_coin_list(self):
        log.info('Find best target coins, it will spend 60 sec...')
        candidate_list = []
        while True:
            for coin in static.chart.codes:
                df = await aiopyupbit.get_ohlcv(coin, interval='minute5', count=20)
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

    def get_rsi(self, df: DataFrame):
        return talib.RSI(np.asarray(df['close']), self.period)

    async def __loop(self):
        time_history = {}
        coin_list = await self.get_best_coin_list()
        log.info(f'Coin list: {[x.code for x in coin_list]}')
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
        log.info(f'Refresh at {end_time}')
        while self.alive:
            if datetime.datetime.now() >= end_time:
                for coin in coin_list:
                    self.send_signal(code=coin.code, position='ask',
                                     type='market', price=-1)
                self.send_signal(None, None, None, None)
                coin_list = await self.get_best_coin_list()
                end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
                log.info(f'Coin list: {[x.code for x in coin_list]}')
                log.info(f'Refresh at {end_time}')
            for coin in coin_list:
                time.sleep(0.2)
                candle = await aiopyupbit.get_ohlcv(ticker=coin.code, interval='minute1')
                rsi = self.get_rsi(candle)[-1]
                average_volume = self.get_average(candle, 5, 'volume')[1]
                status = {}
                status['own'] = True if coin.code.split('-')[1] in static.account.coins.keys() else False
                if status['own']:
                    if coin.code not in time_history:
                        time_history[coin.code] = datetime.datetime.now()
                    buy_history = static.account.coins[coin.code.split('-')[1]]
                    current_price = coin.get_trade_price()
                    profit = (current_price / buy_history['avg_buy_price']) - 1
                    if profit >= 0.01 or profit <= -0.01:
                        self.send_signal(code=coin.code, position='ask',
                                         type='market', price=-1)
                else:
                    if coin.code in time_history.keys():
                        del time_history[coin.code]
                    status['rsi'] = True if rsi <= self.rsi else False
                    status['volume'] = True if candle['volume'].iloc[-2] < average_volume else False
                    if status['rsi'] and status['volume']:
                        self.send_signal(code=coin.code, position='bid',
                                         type='limit', price=coin.get_trade_price())
                self.redis_client.set(f"strategy:status:{coin.code}", orjson.dumps(status))
                log.info(f'code: {coin.code}, status: {status}')
