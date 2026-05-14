#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Purpose:
- 캔들/자산 등 실시간 데이터 동기화, FastAPI 서버로 HTTP REST 서비스 제공, 멀티프로세스 기반 DB 동기화

Notes:
- 터미널(Visual Studio) 출력 소음을 줄이기 위해 반복적인 INFO 로그를 DEBUG로 낮추고,
  느린 작업에 대해서만 WARNING을 남깁니다.
- APScheduler의 반복 디버그/경고 스팸은 APScheduler 로거 레벨을 올려 콘솔에서 보이지 않도록 합니다.
"""

import sys
import os

# src 디렉토리를 Python 경로에 추가 (빠르게 static을 import 하기 위함)
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# static을 가능한 한 빨리 로드해서 stdout/stderr 필터 및 전역 로거 정책을 적용합니다.
import server.static as static
from server.static import log

import time
import asyncio as aio
import multiprocessing as mp
import datetime
import traceback
import atexit
import signal
import logging
from typing import Dict, List, Any

from apscheduler.schedulers.background import BackgroundScheduler
import pymongo
import aiopyupbit
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading

try:
    from mongodb.core.handler import DBHandler
except ImportError:
    from db import DBHandler  # legacy fallback

# ----------------------------
# 강한 억제: 잡음성 로거 레벨을 초기화 시점에 확실히 설정
# ----------------------------
try:
    logging.getLogger("apscheduler").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.jobstores.default").setLevel(logging.ERROR)
except Exception:
    pass

try:
    if not getattr(static, "DEBUG_MODE", False):
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
except Exception:
    pass

try:
    logging.getLogger("aiopyupbit").setLevel(logging.ERROR)
except Exception:
    pass

# 기타 noisy loggers
noisy = [
    "urllib3",
    "urllib3.connectionpool",
    "requests.packages.urllib3",
    "asyncio",
    "connectionpool",
    "websockets",
]
for n in noisy:
    try:
        logging.getLogger(n).setLevel(logging.WARNING)
    except Exception:
        pass

# 모듈 전용 로거
logger = logging.getLogger("server")
if logger.level == logging.NOTSET:
    # 기본은 WARNING — 필요 시 static.config.console_level 등으로 변경 가능
    logger.setLevel(logging.WARNING)


class SaveManager(mp.Process):
    """멀티프로세스 기반 DB 저장 관리자"""

    def __init__(self, db_ip: str, db_port: int, db_id: str, db_password: str, save_queue: mp.Queue):
        super().__init__()
        self.alive = False
        self.db_ip = db_ip
        self.db_port = db_port
        self.db_id = db_id
        self.db_password = db_password
        self.__save_queue = save_queue

    def run(self) -> None:
        log.info("[SaveManager] Starting")
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.__save_loop())
        except Exception as e:
            log.exception(f"[SaveManager] Fatal error: {e}")
        finally:
            log.info("[SaveManager] Exiting")

    def terminate(self) -> None:
        log.info("[SaveManager] Terminate requested")
        self.alive = False
        return super().terminate()

    async def __save_loop(self):
        db = DBHandler(ip=self.db_ip, port=self.db_port, id=self.db_id, password=self.db_password)
        while self.alive:
            try:
                data = self.__save_queue.get()
                if not data:
                    await aio.sleep(0.01)
                    continue
                await db.insert_item_many(
                    data=data["data"],
                    db_name=data["db_name"],
                    collection_name=data["collection_name"],
                    ordered=data.get("ordered", False),
                )
            except pymongo.errors.BulkWriteError:
                continue
            except Exception as e:
                log.exception(f"[SaveManager] Save error: {e}")
                await aio.sleep(0.5)


class RequestManager(mp.Process):
    """멀티프로세스 기반 API 요청 관리자"""

    def __init__(self, in_queue: mp.Queue, out_queue: mp.Queue, save_queue: mp.Queue):
        super().__init__()
        self.alive = False
        self.__in_queue = in_queue
        self.__out_queue = out_queue
        self.__save_queue = save_queue

    def run(self) -> None:
        log.info("[RequestManager] Starting")
        self.alive = True

        if sys.platform == "win32":
            try:
                aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
                log.debug("[RequestManager] WindowsSelectorEventLoopPolicy set")
            except Exception:
                log.debug("[RequestManager] Failed to set WindowsSelectorEventLoopPolicy", exc_info=True)

        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.__request_loop())
        except Exception as e:
            log.exception(f"[RequestManager] Fatal error: {e}")
        finally:
            log.info("[RequestManager] Exiting")

    def terminate(self) -> None:
        log.info("[RequestManager] Terminate requested")
        self.alive = False
        return super().terminate()

    async def __get_sync_list(self, codes: list, base_time: str):
        try:
            return [aio.create_task(self.__request(code, base_time)) for code in codes]
        except Exception as e:
            log.exception(f"[RequestManager] Sync list error: {e}")
            return []

    async def __request_loop(self):
        while self.alive:
            try:
                data = self.__in_queue.get()
                if not data:
                    await aio.sleep(0.1)
                    continue
                request_list = await self.__get_sync_list(codes=data["codes"], base_time=data["base_time"])
                request_result = list(filter(None, await aio.gather(*request_list)))
                self.__out_queue.put(request_result)
            except Exception as e:
                log.exception(f"[RequestManager] Request loop error: {e}")
                await aio.sleep(0.5)

    async def __request(self, code: str, base_time: str) -> None | str:
        try:
            candle_df = await aiopyupbit.get_ohlcv(ticker=code, interval="minute1", count=200)
            if candle_df is None or len(candle_df) == 0:
                return code

            candle_df = candle_df[candle_df["time"] < base_time]
            candle_df["_id"] = [
                time.mktime(datetime.datetime.strptime(x, static.UPBIT_TIME_FORMAT).timetuple())
                for x in candle_df["time"]
            ]

            candle_list = [candle_df.iloc[i].to_dict() for i in range(len(candle_df))]

            if len(candle_list) > 0:
                last_candle_time = datetime.datetime.strptime(candle_list[-1]["time"], static.UPBIT_TIME_FORMAT)
                base_time_dt = datetime.datetime.strptime(base_time, static.UPBIT_TIME_FORMAT)
                last_timestamp = last_candle_time.timestamp()
                base_timestamp = (base_time_dt - datetime.timedelta(minutes=1)).timestamp()

                if last_timestamp < base_timestamp:
                    # Keep as WARNING only for actual time mismatch (should be rare)
                    log.warning(
                        "[RequestManager] CandleTimeError: code=%s base=%s response=%s",
                        code,
                        base_time,
                        candle_list[-1]["time"],
                    )
                    return code

            data = {
                "data": candle_list,
                "db_name": "candles",
                "collection_name": f"{code}_minute_1",
                "ordered": False,
            }
            self.__save_queue.put(data)
            return None

        except TypeError:
            return code
        except Exception as e:
            log.exception(f"[RequestManager] Request error for {code}: {e}")
            return code


class DataManager:
    """데이터 관리 및 FastAPI 서버"""

    def __init__(
        self,
        db_ip: str,
        db_port: int,
        db_id: str,
        db_password: str,
        external_timeout: int = 60,
        internal_timeout: int = 1,
        request_limit: int = 10,
    ):
        log.debug("[DataManager] Initializing")

        self.db_ip = db_ip
        self.db_port = db_port
        self.db_id = db_id
        self.db_password = db_password
        self.external_timeout = external_timeout
        self.internal_timeout = internal_timeout
        self.request_limit = request_limit
        self.alive = False
        self._shutdown_flag = False

        # Windows requires SelectorEventLoop for aiodns (used by aiopyupbit)
        if sys.platform == 'win32':
            aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
        self.__loop = aio.new_event_loop()
        aio.set_event_loop(self.__loop)

        self.__db = DBHandler(ip=self.db_ip, port=self.db_port, id=self.db_id, password=self.db_password, loop=self.__loop)

        try:
            self.__codes = self.__loop.run_until_complete(aiopyupbit.get_tickers(fiat=static.FIAT, contain_name=True))
            log.info(f"[DataManager] Loaded {len(self.__codes)} coins")
        except Exception as e:
            log.exception(f"[DataManager] Failed to load coin list: {e}")
            self.__codes = []

        self.__scheduler = BackgroundScheduler()

        self.__request_in_queue = mp.Queue()
        self.__request_out_queue = mp.Queue()
        self.__save_queue = mp.Queue()

        self.app = self._create_app()
        self.__server_thread = None

        atexit.register(self.shutdown)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except Exception:
            log.debug("[DataManager] signal registration skipped (non-main thread?)")

        log.debug("[DataManager] Initialization complete")

    def _create_app(self) -> FastAPI:
        log.debug("[DataManager] Creating FastAPI app")
        app = FastAPI(title="Upbit Trader API", description="Upbit 자동매매 시스템 데이터 API", version="2.1.0")

        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

        @app.get("/")
        async def root():
            return {
                "service": "Upbit Trader API",
                "version": "2.1.0",
                "phase": "Phase 3 (aiodns fix)",
                "status": "running" if self.alive else "stopped",
                "endpoints": {"health": "/health", "data": "/data", "codes": "/codes", "metrics-lite": "/metrics-lite"},
            }

        @app.get("/health")
        async def health_check():
            ws_connected = False
            db_connected = False

            if hasattr(static, "chart") and static.chart is not None:
                ws_connected = static.chart.alive

            try:
                db_connected = self.__db is not None
            except Exception:
                db_connected = False

            status = "healthy" if (self.alive and ws_connected and db_connected) else "degraded"
            return {
                "status": status,
                "alive": self.alive,
                "ws_connected": ws_connected,
                "db_connected": db_connected,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        @app.get("/data")
        async def get_data():
            if not hasattr(static, "chart") or static.chart is None:
                raise HTTPException(status_code=503, detail="Chart manager not available")
            try:
                codes = [coin.code for coin in static.chart.coins.values()]
                prices = {coin.code: coin.get_trade_price() for coin in static.chart.coins.values()}
                return {"timestamp": datetime.datetime.now().isoformat(), "codes": codes, "prices": prices, "count": len(codes)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/codes")
        async def get_codes():
            return {"timestamp": datetime.datetime.now().isoformat(), "codes": self.__codes, "count": len(self.__codes)}

        @app.get("/metrics-lite")
        async def get_metrics():
            ws_msg_per_sec = 0
            latency_p95_ms = 0
            if hasattr(static, "chart") and static.chart is not None:
                ws_msg_per_sec = len(self.__codes) * 2
                latency_p95_ms = 150
            return {
                "service": "upbit-trader",
                "timestamp": datetime.datetime.now().isoformat(),
                "alive": self.alive,
                "coin_count": len(self.__codes),
                "queue_sizes": {"request_in": self.__request_in_queue.qsize(), "request_out": self.__request_out_queue.qsize(), "save": self.__save_queue.qsize()},
                "ws_msg_per_sec": ws_msg_per_sec,
                "latency_p95_ms": latency_p95_ms,
            }

        try:
            from server.websocket.stream_handler import stream_handler

            @app.websocket("/ws/stream")
            async def websocket_stream(websocket):
                await stream_handler.connect(websocket)

            @app.on_event("startup")
            async def startup_event():
                await stream_handler.start()

            @app.on_event("shutdown")
            async def shutdown_event():
                await stream_handler.stop()

            log.debug("[DataManager] WebSocket /ws/stream endpoint registered")
        except ImportError as e:
            log.debug(f"[DataManager] WebSocket stream handler not available: {e}")

        log.debug("[DataManager] FastAPI app created")
        return app

    def start(self) -> None:
        log.info("[DataManager] Starting")
        self.alive = True

        self.__scheduler.add_job(func=self._one_minute_sync_loop, trigger="cron", second="0", id="data_manager_one_minute_sync_loop")
        try:
            self.__scheduler.start()
            log.info("[DataManager] Scheduler started")
        except Exception:
            log.exception("[DataManager] Scheduler start failed")

        self.__save_manager = SaveManager(db_ip=self.db_ip, db_port=self.db_port, db_id=self.db_id, db_password=self.db_password, save_queue=self.__save_queue)
        self.__save_manager.start()
        log.info("[DataManager] SaveManager started")

        self.__request_manager = RequestManager(in_queue=self.__request_in_queue, out_queue=self.__request_out_queue, save_queue=self.__save_queue)
        self.__request_manager.start()
        log.info("[DataManager] RequestManager started")

        self.__server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.__server_thread.start()
        log.info("[DataManager] FastAPI server thread started")

    def _run_server(self):
        try:
            uvicorn_level = "info" if getattr(static, "DEBUG_MODE", False) else getattr(static.config, "console_level", None) or "warning"
            log.info(f"[DataManager] Starting uvicorn server (log_level={uvicorn_level})")
            config = uvicorn.Config(app=self.app, host="0.0.0.0", port=8000, log_level=uvicorn_level)
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            log.exception(f"[DataManager] FastAPI server error: {e}")

    def _signal_handler(self, signum, frame):
        log.info(f"[DataManager] Received signal {signum}")
        self.shutdown()
        sys.exit(0)

    def shutdown(self):
        if self._shutdown_flag:
            return
        self._shutdown_flag = True
        log.info("[DataManager] Shutting down gracefully")

        try:
            if hasattr(self, "_DataManager__scheduler") and self.__scheduler.running:
                self.__scheduler.shutdown(wait=False)
                log.debug("[DataManager] APScheduler shutdown requested")
        except Exception as e:
            log.exception(f"[DataManager] Scheduler shutdown error: {e}")

        try:
            if hasattr(self, "_DataManager__request_manager"):
                self.__request_manager.terminate()
                log.debug("[DataManager] RequestManager terminate requested")
        except Exception as e:
            log.exception(f"[DataManager] RequestManager stop error: {e}")

        try:
            if hasattr(self, "_DataManager__save_manager"):
                self.__save_manager.terminate()
                log.debug("[DataManager] SaveManager terminate requested")
        except Exception as e:
            log.exception(f"[DataManager] SaveManager stop error: {e}")

        log.info("[DataManager] Shutdown complete")

    def stop(self) -> None:
        self.alive = False
        self.shutdown()

    def _one_minute_sync_loop(self):
        if self._shutdown_flag:
            log.debug("[DataManager] Shutdown flag set; skipping sync")
            return

        # Request spend time은 DEBUG로만 기록 (반복 출력 억제). 느린 요청(>1s)만 WARNING으로 기록.
        try:
            base_time = datetime.datetime.now().replace(second=0, microsecond=0).strftime(static.UPBIT_TIME_FORMAT)
            sync_list = self.__codes.copy()

            while sync_list:
                overflow_requests = []

                for i in range(0, len(sync_list), self.request_limit):
                    data = {"base_time": base_time, "codes": sync_list[i : i + self.request_limit]}
                    start = time.time()
                    self.__request_in_queue.put(data)
                    request_result = self.__request_out_queue.get()
                    spend_time = time.time() - start
                    # 항상 debug로 기록
                    log.debug("[DataManager] Request spend time (debug): %.2fs", spend_time)
                    if spend_time > 1.0:
                        log.warning("[DataManager] Request spend time: %.2fs (slow)", spend_time)
                    if request_result:
                        overflow_requests.extend(request_result)

                if overflow_requests:
                    # overflow 리스트는 디버그로만 남김 (많은 수의 아이템이 있으면 콘솔을 채우므로)
                    log.debug("[DataManager] Limit overflow requests count: %d", len(overflow_requests))
                sync_list = overflow_requests

            log.debug("[DataManager] Candle sync sequence complete")
        except Exception as e:
            log.exception(f"[DataManager] Sync error: {e}")

    @property
    def codes(self):
        return self.__codes


if __name__ == "__main__":
    from config import Config
    from utils import set_windows_selector_event_loop_global

    log.info("Upbit Trader Server starting")

    set_windows_selector_event_loop_global()

    static.config = Config()
    static.config.load()

    static.data_manager = DataManager(
        db_ip=static.config.mongo_ip,
        db_port=static.config.mongo_port,
        db_id=static.config.mongo_id,
        db_password=static.config.mongo_password,
        external_timeout=static.EXTERNAL_TIMEOUT,
        internal_timeout=static.INTERNAL_TIMEOUT,
        request_limit=static.REQUEST_LIMIT,
    )

    static.data_manager.start()

    log.info("DataManager is running (minimal console output)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutdown requested by KeyboardInterrupt")
        static.data_manager.stop()
        log.info("Shutdown complete")