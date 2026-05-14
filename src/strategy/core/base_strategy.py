#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- Strategy 추상 기본 클래스 (Thread 기반)
[Responsibilities]
- 시그널 전송 및 공통 유틸리티 메서드 제공
- 하위 전략 클래스가 override할 __loop() 추상 메서드 정의
"""

import asyncio as aio
import os
import numpy as np
from multiprocessing import Queue
from threading import Thread
import redis
from apscheduler.schedulers.background import BackgroundScheduler

try:
    import server.static as static
    from server.static import log
except ImportError:
    import logging
    log = logging.getLogger(__name__)


def _get_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import pathlib as _pl
        import importlib.util as _ilu
        _factory_path = _pl.Path(__file__).resolve().parents[2] / "core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_bs", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


class BaseStrategy(Thread):
    """자동매매 전략 추상 기본 클래스"""

    def __init__(self, queue: Queue) -> None:
        super().__init__()
        self.alive = False
        self.daemon = False
        self.__queue = queue
        self.redis_client = redis.from_url(_get_redis_url(), decode_responses=True)
        self.scheduler = BackgroundScheduler()

    def run(self) -> None:
        log.info('Start strategy thread')
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        loop.run_until_complete(self.__loop())
        self.scheduler.start()

    def terminate(self) -> None:
        log.info('Stop strategy thread')
        self.alive = False
        self.scheduler.shutdown()
        self.redis_client.close()

    def send_signal(self, code: str, position: str, type: str, price: float) -> None:
        """시그널 큐에 전송"""
        self.__queue.put({'code': code, 'position': position,
                          'type': type, 'price': price})

    def get_average(self, arr: np.ndarray, unit: int = 5) -> float:
        """이동 평균 계산"""
        return np.mean(arr[-unit:]) if len(arr) >= unit else 0.0

    async def __loop(self) -> None:
        raise NotImplementedError('Subclasses must implement __loop() method')
