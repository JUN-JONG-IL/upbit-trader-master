#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import time
import datetime
import uuid
import asyncio as aio
from multiprocessing import Queue, Process
from threading import Thread
import numpy as np
import aiopyupbit
from pandas.core.frame import DataFrame
import pandas as pd
import talib
from utils.helpers import Coin
try:
    from mongodb.core.handler import DBHandler
except ImportError:
    from db import DBHandler  # legacy fallback
import server.static as static
from server.static import log
from config import Config
from kafka import KafkaProducer, KafkaConsumer
import json
import orjson
import polars as pl
import redis
import sqlalchemy
import dask.dataframe as dd
from apscheduler.schedulers.background import BackgroundScheduler
import backtrader as bt


def _get_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import pathlib as _pl
        import importlib.util as _ilu
        _factory_path = _pl.Path(__file__).resolve().parents[2] / "core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_sm", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


class SignalManager(Process):
    def __init__(self, config: Config, db_ip: str, db_port: int,
                 db_id: str, db_password: str, queue: Queue) -> None:
        self.alive = False
        self.__config = config
        self.__upbit = aiopyupbit.Upbit(access=self.__config.upbit_access_key,
                                        secret=self.__config.upbit_secret_key)
        self.__queue = queue
        self.__db_ip = db_ip
        self.__db_port = db_port
        self.__db_id = db_id
        self.__db_password = db_password
        self.__max_individual_trade_price = self.__config.max_individual_trade_price
        self.__coin_list = []
        self.producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=lambda v: orjson.dumps(v).decode('utf-8'))
        self.consumer = KafkaConsumer('signal_topic', bootstrap_servers='localhost:9092', auto_offset_reset='latest')
        self.redis_client = redis.from_url(_get_redis_url(), decode_responses=True)
        self.engine = sqlalchemy.create_engine('sqlite:///trade.db')
        self.scheduler = BackgroundScheduler()
        super().__init__()

    def run(self) -> None:
        log.info('Start signal manager process')
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        db = DBHandler(ip=self.__db_ip,
                       port=self.__db_port,
                       id=self.__db_id,
                       password=self.__db_password,
                       loop=loop)
        loop.run_until_complete(self.__loop(db))
        Thread(target=self._kafka_pub_thread, daemon=True).start()
        Thread(target=self._kafka_sub_thread, daemon=True).start()
        self.scheduler.start()

    def terminate(self) -> None:
        log.info('Stop signal manager process')
        ticker = aio.run(self.__upbit.get_balances())
        own_ticker = []
        for x in ticker:
            if x['currency'] != 'KRW':
                own_ticker.append(x)
        for x in own_ticker:
            try:
                ticker = f'{static.FIAT}-{x["currency"]}'
                order_list = aio.run(self.__upbit.get_order(ticker))
                for y in order_list:
                    aio.run(self.__upbit.get_order(y['uuid']))
                current_price = aio.run(aiopyupbit.get_current_price(ticker))
                volume = x["balance"]
                aio.run(self.__upbit.sell_limit_order(
                    ticker, current_price, volume))
            except Exception as e:
                log.error(e)
        for x in self.__coin_list:
            try:
                order_list = aio.run(self.__upbit.get_order(x))
                for y in order_list:
                    aio.run(self.__upbit.get_order(y['uuid']))
            except Exception as e:
                log.error(e)
        self.scheduler.shutdown()
        self.producer.close()
        self.consumer.close()
        self.redis_client.close()
        self.quit()
        self.wait()
        return super().terminate()

    async def __loop(self, db: DBHandler) -> None:
        while self.alive:
            try:
                message = self.__queue.get()
                if not message['code'] and not message['type'] and not message['position'] and not message['price']:
                    self.__coin_list.clear()
                    continue
                now = datetime.datetime.now()
                message['_id'] = f'{uuid.uuid4()}'
                message['time'] = now.strftime(static.BASE_TIME_FORMAT)
                log.info(f'Signal information:\n'
                         f'_id: {message["_id"]}\n'
                         f'time: {message["time"]}\n'
                         f'code: {message["code"]}\n'
                         f'type: {message["type"]}\n'
                         f'position: {message["position"]}\n'
                         f'price: {message["price"]}')
                df = pl.DataFrame([message])
                await db.insert_item_one(data=df.to_dict(as_series=False), db_name='signal_history',
                                         collection_name=datetime.datetime.today().strftime("%Y-%m-%d"))
                code = message['code'].split('-')[1]
                order_list = await self.__upbit.get_order(message['code'])
                own_dict = {x['currency']: x for x in await self.__upbit.get_balances()}
                if message['position'] == 'bid':
                    if code in own_dict.keys():
                        log.warning(f'{code} is already bought')
                        continue
                    elif order_list:
                        log.warning(f'order_list: {order_list}')
                        uuid_list = [x['uuid'] for x in order_list]
                        for x in uuid_list:
                            await self.__upbit.cancel_order(x)
                    if message['type'] == 'market':
                        response = await self.__upbit.buy_market_order(ticker=message['code'],
                                                                       price=self.__max_individual_trade_price)
                    else:
                        volume = self.__max_individual_trade_price / \
                            message['price']
                        response = await self.__upbit.buy_limit_order(ticker=message['code'],
                                                                      price=message['price'],
                                                                      volume=volume)
                else:
                    if code not in own_dict:
                        log.warning(f'{code} is not bought')
                        continue
                    elif order_list:
                        log.warning(f'order_list: {order_list}')
                        uuid_list = [x['uuid'] for x in order_list]
                        for x in uuid_list:
                            await self.__upbit.cancel_order(x)
                    if message['type'] == 'market':
                        response = await self.__upbit.sell_market_order(ticker=message['code'],
                                                                        price=own_dict[code]['balance'])
                    else:
                        response = await self.__upbit.sell_limit_order(ticker=message['code'],
                                                                       price=message['price'],
                                                                       volume=own_dict[code]['balance'])
                if not message['code'] in self.__coin_list:
                    self.__coin_list.append(message['code'])
                response_uuid_list = [x['uuid'] for x in response]
                trade_list = [{'uuid': x for x in response_uuid_list}]
                trade_list = [x.update({'signal_id': message['_id']})
                              for x in trade_list]
                df_trade = pl.DataFrame(trade_list)
                await db.insert_item_many(data=df_trade.to_dicts(), db_name='signal_trade_history',
                                          collection_name=datetime.datetime.today().strftime("%Y-%m-%d"))
                self.redis_client.set(f"signal:{message['_id']}", orjson.dumps(message))
            except Exception as e:
                log.error(e)

    def _kafka_pub_thread(self):
        while self.alive:
            message = self.__queue.get()
            self.producer.send('signal_topic', value=message)
            time.sleep(0.1)

    def _kafka_sub_thread(self):
        for message in self.consumer:
            if not self.alive:
                break
            data = orjson.loads(message.value)
            log.info(f'Received signal from Kafka: {data}')
