#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
Compute 프로세스 - GUI와 분리된 계산 전용 프로세스

[Notes]
- child 프로세스에서 직접 print()로 찍히는 불필요한 터미널 출력을 억제하도록
  run() 시작부에서 안전한 stdout/stderr 필터를 설치합니다.
- 가능한 한 로거(logging)로 출력하도록 유지하여 부모 프로세스의 로그 정책을 따릅니다.
- 동작(로직)은 변경하지 않으며 출력 방식만 조정합니다.
"""

import sys
import os
import time
import json
import asyncio as aio
import multiprocessing as mp
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from threading import Lock

# ============================================
# Rate Limiter for Upbit API
# ============================================
class RateLimiter:
    """API Rate Limiter for Upbit API"""
    def __init__(self, max_per_second=8, max_per_minute=500):
        self.max_per_second = max_per_second
        self.max_per_minute = max_per_minute
        self.second_requests = []
        self.minute_requests = []
        self.lock = Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.second_requests = [t for t in self.second_requests if now - t < 1.0]
            self.minute_requests = [t for t in self.minute_requests if now - t < 60.0]
            if len(self.second_requests) >= self.max_per_second:
                sleep_time = 1.0 - (now - self.second_requests[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self.second_requests = []
            if len(self.minute_requests) >= self.max_per_minute:
                sleep_time = 60.0 - (now - self.minute_requests[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self.minute_requests = []
            self.second_requests.append(now)
            self.minute_requests.append(now)


rate_limiter = RateLimiter()

# ============================================
# Optional dependencies
# ============================================
try:
    import redis
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

try:
    from motor import motor_asyncio
    MONGODB_AVAILABLE = True
except Exception:
    MONGODB_AVAILABLE = False

# ============================================
# dynamic imports for components (CandleAggregator, IndicatorEngine)
# (we will re-import in child process as needed)
# ============================================
CANDLE_AGGREGATOR_AVAILABLE = False
INDICATOR_ENGINE_AVAILABLE = False
try:
    compute_dir = os.path.dirname(os.path.abspath(__file__))
    if compute_dir not in sys.path:
        sys.path.insert(0, compute_dir)
    from candle_aggregator import CandleAggregator
    CANDLE_AGGREGATOR_AVAILABLE = True
except Exception:
    CANDLE_AGGREGATOR_AVAILABLE = False

try:
    from indicator_engine import IndicatorEngine
    INDICATOR_ENGINE_AVAILABLE = True
except Exception:
    INDICATOR_ENGINE_AVAILABLE = False


# ----------------------------
# Child-process stdout/stderr filter
# ----------------------------
class _ChildFilteredWriter:
    """
    Child process 전용 stdout/stderr wrapper.
    지정된 패턴이 포함된 라인은 터미널 출력에서 억제합니다.
    """
    def __init__(self, wrapped, patterns=None):
        self._wrapped = wrapped
        self._patterns = patterns or []
        self._buffer = ""

    def _should_suppress(self, line: str) -> bool:
        for p in self._patterns:
            if p and p in line:
                return True
        return False

    def write(self, s):
        try:
            if not s:
                return
            if not isinstance(s, str):
                s = str(s)
            self._buffer += s
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if self._should_suppress(line):
                    continue
                try:
                    self._wrapped.write(line + "\n")
                except Exception:
                    pass
        except Exception:
            try:
                self._wrapped.write(s)
            except Exception:
                pass

    def flush(self):
        try:
            if self._buffer:
                if not self._should_suppress(self._buffer):
                    try:
                        self._wrapped.write(self._buffer)
                    except Exception:
                        pass
                self._buffer = ""
            try:
                self._wrapped.flush()
            except Exception:
                pass
        except Exception:
            pass

    def isatty(self):
        try:
            return self._wrapped.isatty()
        except Exception:
            return False

    def fileno(self):
        try:
            return self._wrapped.fileno()
        except Exception:
            return 1


_CHILD_SUPPRESS_PATTERNS = [
    "[ComputeProcess]",
    "aiopyupbit 에러",
    "요청 수 제한",
    "Prefetching",
    "Prefetch complete",
    "All indicators are now ready for calculation",
    "Subscribed to",
    "StreamHandler]",
    "Request spend time:",
    "Starting new HTTPS connection",
    "GET /v1/candles",
]


class ComputeProcess(mp.Process):
    """
    Compute 프로세스
    """
    def __init__(self,
                 redis_host: str = "localhost",
                 redis_port: int = 6379,
                 mongodb_host: str = "localhost",
                 mongodb_port: int = 27017,
                 mongodb_id: Optional[str] = None,
                 mongodb_password: Optional[str] = None,
                 kafka_enabled: bool = False,
                 mongodb_enabled: bool = True):
        super().__init__()
        self.redis_host = redis_host
        self.redis_port = redis_port
        # read redis password from environment by default (can be overridden externally if needed)
        self.redis_password = os.getenv("REDIS_PASSWORD", None)

        self.mongodb_host = mongodb_host
        self.mongodb_port = mongodb_port
        self.mongodb_id = mongodb_id
        self.mongodb_password = mongodb_password
        self.kafka_enabled = kafka_enabled
        self.mongodb_enabled = mongodb_enabled

        self.alive = True
        self.redis_client = None
        self.pubsub = None
        self.mongodb_client = None

        self.candle_aggregator = None
        self.indicator_engine = None

        self.metrics = {
            "trade_count": 0,
            "candle_count": 0,
            "closed_candle_count": 0,
            "indicator_count": 0,
            "prefetch_count": 0,
            "mongodb_save_count": 0,
            "redis_save_count": 0,
            "ws_publish_count": 0,
            "latencies": []
        }

        self.last_ws_publish = {}
        self.ws_throttle_ms = 500

    def _init_logger(self):
        """
        Compute 프로세스 전용 로거 초기화.
        - 기본 콘솔 레벨은 WARNING (터미널 소음 억제)
        - 환경변수 COMPUTE_LOG_LEVEL로 조정 가능 (e.g., DEBUG/INFO/WARNING)
        """
        level_name = os.environ.get("COMPUTE_LOG_LEVEL", "WARNING").upper()
        level = getattr(logging, level_name, logging.WARNING)
        logger = logging.getLogger("ComputeProcess")
        logger.setLevel(level)

        # If no handlers, add a StreamHandler to stdout (so logs go to parent's console if level allows)
        if not logger.handlers:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(level)
            fmt = logging.Formatter("[%(asctime)s] [ComputeProcess] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
            ch.setFormatter(fmt)
            logger.addHandler(ch)

        # Avoid propagation to root to prevent duplicate messages
        logger.propagate = False
        return logger

    def run(self):
        # Child process에서 print() 출력을 억제하기 위해 stdout/stderr 필터 설치
        try:
            sys.stdout = _ChildFilteredWriter(sys.stdout, patterns=_CHILD_SUPPRESS_PATTERNS)
            sys.stderr = _ChildFilteredWriter(sys.stderr, patterns=_CHILD_SUPPRESS_PATTERNS)
        except Exception:
            pass

        logger = self._init_logger()
        logger.info("Starting compute process")  # info-level; may be suppressed by default console level

        # Re-import modules in multiprocessing child
        self._reimport_modules(logger)

        if sys.platform == "win32":
            logger.debug("Setting WindowsSelectorEventLoopPolicy (aiodns fix)")
            try:
                aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
            except Exception:
                logger.exception("Failed to set Windows selector policy")

        # Redis 연결
        if not self._connect_redis(logger):
            logger.warning("Failed to connect to Redis; compute process exiting")
            return

        # MongoDB 연결 (선택)
        if self.mongodb_enabled:
            if not self._connect_mongodb(logger):
                logger.warning("MongoDB connection failed; continuing without MongoDB (candles will not be saved)")
                self.mongodb_client = None
        else:
            logger.info("MongoDB disabled (candles will not be saved)")

        # 컴포넌트 초기화
        self._init_components(logger)

        # 이벤트 루프 실행
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._event_loop(logger))
        except KeyboardInterrupt:
            logger.info("Interrupted")
        except Exception as e:
            logger.exception("Compute process encountered an error: %s", e)
        finally:
            self._cleanup(logger)

    def _reimport_modules(self, logger):
        global CANDLE_AGGREGATOR_AVAILABLE, CandleAggregator
        global INDICATOR_ENGINE_AVAILABLE, IndicatorEngine

        compute_dir = os.path.dirname(os.path.abspath(__file__))
        if compute_dir not in sys.path:
            sys.path.insert(0, compute_dir)

        if not CANDLE_AGGREGATOR_AVAILABLE:
            try:
                from candle_aggregator import CandleAggregator
                CANDLE_AGGREGATOR_AVAILABLE = True
                logger.info("CandleAggregator re-imported successfully")
            except Exception as e:
                logger.warning("CandleAggregator re-import failed: %s", e)

        if not INDICATOR_ENGINE_AVAILABLE:
            try:
                from indicator_engine import IndicatorEngine
                INDICATOR_ENGINE_AVAILABLE = True
                logger.info("IndicatorEngine re-imported successfully")
            except Exception as e:
                logger.warning("IndicatorEngine re-import failed: %s", e)

    def _connect_redis(self, logger) -> bool:
        if not REDIS_AVAILABLE:
            logger.warning("redis package not available")
            return False
        try:
            # Prefer instance attribute if set, otherwise environment variable
            password = getattr(self, "redis_password", None) or os.getenv("REDIS_PASSWORD", None)

            # Create client with password if available (safe to pass None)
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=password,
                decode_responses=True
            )

            # ping -> may raise AuthenticationError if password required/invalid
            self.redis_client.ping()
            logger.info("Connected to Redis")
            return True

        except Exception as e:
            # Handle AuthenticationError separately if available
            try:
                auth_err = redis.exceptions.AuthenticationError
            except Exception:
                auth_err = None

            if auth_err and isinstance(e, auth_err):
                logger.error("Redis authentication failed: %s", e)
            else:
                logger.exception("Redis connection failed: %s", e)

            # ensure client cleaned up
            try:
                # best-effort close or disconnect
                if hasattr(self.redis_client, "close"):
                    try:
                        self.redis_client.close()
                    except Exception:
                        pass
                if hasattr(self.redis_client, "connection_pool") and hasattr(self.redis_client.connection_pool, "disconnect"):
                    try:
                        self.redis_client.connection_pool.disconnect()
                    except Exception:
                        pass
            except Exception:
                pass

            self.redis_client = None
            return False

    def _connect_mongodb(self, logger) -> bool:
        if not MONGODB_AVAILABLE:
            logger.warning("motor package not available")
            return False
        try:
            if self.mongodb_id and self.mongodb_password:
                uri = f"mongodb://{self.mongodb_id}:{self.mongodb_password}@{self.mongodb_host}:{self.mongodb_port}/?authSource=admin"
                logger.debug("MongoDB connecting as: %s@%s:%s", self.mongodb_id, self.mongodb_host, self.mongodb_port)
            else:
                uri = f"mongodb://{self.mongodb_host}:{self.mongodb_port}"
                logger.debug("MongoDB URI: %s", uri)

            self.mongodb_client = motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)

            logger.info("Testing MongoDB connection...")
            test_loop = aio.new_event_loop()
            aio.set_event_loop(test_loop)

            async def test_connection():
                try:
                    result = await self.mongodb_client.admin.command("ping")
                    return result.get("ok") == 1.0
                except Exception as e:
                    logger.warning("MongoDB ping failed: %s", e)
                    return False

            connected = test_loop.run_until_complete(test_connection())
            test_loop.close()

            if not connected:
                logger.warning("MongoDB connection test failed")
                self.mongodb_client = None
                return False

            logger.info("Connected to MongoDB (authenticated)")
            return True
        except Exception as e:
            logger.exception("MongoDB connection failed: %s", e)
            self.mongodb_client = None
            return False

    def _init_components(self, logger):
        if CANDLE_AGGREGATOR_AVAILABLE:
            try:
                self.candle_aggregator = CandleAggregator(exchange="upbit")
                logger.info("CandleAggregator initialized")
            except Exception as e:
                logger.exception("CandleAggregator initialization failed: %s", e)
        else:
            logger.warning("CandleAggregator not available")

        if INDICATOR_ENGINE_AVAILABLE:
            try:
                self.indicator_engine = IndicatorEngine()
                logger.info("IndicatorEngine initialized")
            except Exception as e:
                logger.exception("IndicatorEngine initialization failed: %s", e)
        else:
            logger.warning("IndicatorEngine not available")

        logger.info("Components initialized")
        logger.info("Starting prefetch for historical candles...")
        try:
            self._prefetch_historical_candles(logger)
        except Exception:
            logger.exception("Prefetch failed unexpectedly")

    async def _event_loop(self, logger):
        logger.info("Event loop started")
        self.pubsub = self.redis_client.pubsub()
        # psubscribe may be resource-heavy — keep it but log at info level
        self.pubsub.psubscribe("md:last:*:ticker")
        logger.info("Subscribed to 'md:last:*:ticker'")

        message_count = 0
        for message in self.pubsub.listen():
            if not self.alive:
                break
            if message.get("type") != "pmessage":
                continue
            try:
                await self._process_trade(message)
                message_count += 1
                if message_count % 10000 == 0:
                    logger.info("Processed %d trade events", message_count)
                    self._print_metrics(logger)
            except Exception as e:
                logger.exception("Process error: %s", e)

    async def _process_trade(self, message: Dict[str, Any]):
        start_time = time.time()
        try:
            data = json.loads(message["data"])
        except Exception:
            return
        if "cd" not in data and "code" not in data:
            return
        symbol = data.get("cd") or data.get("code")
        price = data.get("tp") or data.get("trade_price", 0)
        volume = data.get("tv") or data.get("trade_volume", 0)
        timestamp = data.get("tms", int(time.time() * 1000)) // 1000

        self.metrics["trade_count"] += 1

        if self.candle_aggregator:
            closed_candles = self.candle_aggregator.process_trade({
                "symbol": symbol,
                "price": price,
                "volume": volume,
                "timestamp": timestamp
            })
            for candle in closed_candles:
                if candle.get("is_closed"):
                    self.metrics["closed_candle_count"] += 1
                    indicators = {}
                    if self.indicator_engine:
                        try:
                            indicators = self.indicator_engine.calculate(candle)
                            self.metrics["indicator_count"] += 1
                        except Exception as e:
                            # reduce prints: only log sparsely
                            if self.metrics["indicator_count"] % 1000 == 0:
                                logging.getLogger("ComputeProcess").warning("Indicator calculation error: %s", e)
                    candle["indicators"] = indicators
                    await self._save_to_mongodb(candle)
                    self._save_to_redis(candle)
                    self._publish_ws_patch(candle)

        latency_ms = (time.time() - start_time) * 1000
        self.metrics["latencies"].append(latency_ms)
        if len(self.metrics["latencies"]) > 1000:
            self.metrics["latencies"] = self.metrics["latencies"][-1000:]

    async def _save_to_mongodb(self, candle: Dict[str, Any]):
        if not self.mongodb_client:
            return
        try:
            db_name = "candles"
            collection_name = f"{candle['symbol']}_{candle['timeframe']}"
            await self.mongodb_client[db_name][collection_name].update_one(
                {"t": candle["t"]},
                {"$set": candle},
                upsert=True
            )
            self.metrics["mongodb_save_count"] += 1
        except Exception as e:
            if self.metrics["mongodb_save_count"] % 1000 == 0:
                logging.getLogger("ComputeProcess").warning("MongoDB save error: %s", e)

    def _save_to_redis(self, candle: Dict[str, Any]):
        if not self.redis_client:
            return
        try:
            key = f"candle:{candle.get('exchange','upbit')}:{candle['symbol']}:{candle['timeframe']}:latest"
            self.redis_client.setex(key, 60, json.dumps(candle))
            self.metrics["redis_save_count"] += 1
        except Exception as e:
            if self.metrics["redis_save_count"] % 1000 == 0:
                logging.getLogger("ComputeProcess").warning("Redis save error: %s", e)

    def _publish_ws_patch(self, candle: Dict[str, Any]):
        if not self.redis_client:
            return
        try:
            key = (candle["symbol"], candle["timeframe"])
            now = time.time() * 1000
            if key in self.last_ws_publish:
                elapsed = now - self.last_ws_publish[key]
                if elapsed < self.ws_throttle_ms:
                    return
            self.last_ws_publish[key] = now
            self.redis_client.publish("ui.chart", json.dumps(candle))
            self.metrics["ws_publish_count"] += 1
        except Exception as e:
            if self.metrics["ws_publish_count"] % 1000 == 0:
                logging.getLogger("ComputeProcess").warning("WebSocket publish error: %s", e)

    def _prefetch_historical_candles(self, logger):
        if not self.candle_aggregator or not self.indicator_engine:
            logger.debug("Prefetch skipped (components not available)")
            return

        try:
            import requests
            import pytz
            from datetime import datetime
        except Exception as e:
            logger.warning("Prefetch skipped (missing dependency): %s", e)
            return

        symbols = [
            "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE",
            "KRW-ADA", "KRW-AVAX", "KRW-MATIC", "KRW-DOT", "KRW-LINK"
        ]
        api_timeframes = {
            "min_1": ("minutes", 1),
            "min_3": ("minutes", 3),
            "min_5": ("minutes", 5),
            "min_10": ("minutes", 10),
            "min_15": ("minutes", 15),
            "min_30": ("minutes", 30),
            "min_60": ("minutes", 60),
            "min_240": ("minutes", 240),
            "day": ("days", None),
            "week": ("weeks", None),
            "month": ("months", None),
        }
        KST = pytz.timezone("Asia/Seoul")
        total_prefetched = 0
        logger.info("Prefetching %d symbols x %d timeframes...", len(symbols), len(api_timeframes))

        for symbol in symbols:
            for tf_name, (unit, unit_count) in api_timeframes.items():
                try:
                    rate_limiter.wait_if_needed()
                    if unit_count:
                        url = f"https://api.upbit.com/v1/candles/{unit}/{unit_count}"
                    else:
                        url = f"https://api.upbit.com/v1/candles/{unit}"
                    params = {"market": symbol, "count": 200}
                    response = requests.get(url, params=params, timeout=5)
                    if response.status_code != 200:
                        continue
                    candles = response.json()
                    if not candles:
                        continue
                    candles.reverse()
                    for candle_data in candles:
                        candle = {
                            "exchange": "upbit",
                            "symbol": symbol,
                            "timeframe": tf_name,
                            "t": int(datetime.fromisoformat(candle_data["candle_date_time_kst"].replace("Z", "+00:00")).replace(tzinfo=pytz.UTC).astimezone(KST).timestamp()),
                            "o": candle_data["opening_price"],
                            "h": candle_data["high_price"],
                            "l": candle_data["low_price"],
                            "c": candle_data["trade_price"],
                            "v": candle_data["candle_acc_trade_volume"],
                            "trade_count": 0,
                            "is_closed": True
                        }
                        if self.indicator_engine:
                            try:
                                self.indicator_engine.calculate(candle)
                                total_prefetched += 1
                            except Exception:
                                pass
                except Exception:
                    logger.debug("Prefetch item failed", exc_info=True)
                    continue

        self.metrics["prefetch_count"] = total_prefetched
        logger.info("Prefetch complete: %d candles processed", total_prefetched)
        logger.info("All indicators are now ready for calculation!")

    def _print_metrics(self, logger=None):
        if logger is None:
            logger = logging.getLogger("ComputeProcess")
        avg_latency = sum(self.metrics["latencies"]) / len(self.metrics["latencies"]) if self.metrics["latencies"] else 0
        logger.info("=" * 60)
        logger.info("Metrics:")
        logger.info("  Trade count: %d", self.metrics["trade_count"])
        logger.info("  Closed candle count: %d", self.metrics["closed_candle_count"])
        logger.info("  Indicator count: %d", self.metrics["indicator_count"])
        logger.info("  Prefetch count: %d", self.metrics["prefetch_count"])
        logger.info("  MongoDB save count: %d", self.metrics["mongodb_save_count"])
        logger.info("  Redis save count: %d", self.metrics["redis_save_count"])
        logger.info("  WebSocket publish count: %d", self.metrics["ws_publish_count"])
        logger.info("  Average latency: %.2f ms", avg_latency)
        logger.info("=" * 60)

    def _cleanup(self, logger):
        logger.info("Cleaning up...")
        self._print_metrics(logger)
        try:
            if self.pubsub:
                try:
                    self.pubsub.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self.mongodb_client:
                try:
                    self.mongodb_client.close()
                except Exception:
                    pass
        except Exception:
            pass
        # Best-effort close of redis client / pool
        try:
            if self.redis_client:
                if hasattr(self.redis_client, "close"):
                    try:
                        self.redis_client.close()
                    except Exception:
                        pass
                if hasattr(self.redis_client, "connection_pool") and hasattr(self.redis_client.connection_pool, "disconnect"):
                    try:
                        self.redis_client.connection_pool.disconnect()
                    except Exception:
                        pass
        except Exception:
            pass
        logger.info("Stopped")

    def stop(self):
        self.alive = False