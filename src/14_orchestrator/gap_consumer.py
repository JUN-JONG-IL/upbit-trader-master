# -*- coding: utf-8 -*-
"""
GapConsumer - Redis gap_fill_queue ?�비??(보강??
- 멀???�커(GAP_CONSUMER_WORKERS) 지??
- processor lookup ?�시??기본 5s) -> ?�으�?Redis publish fallback
"""
from __future__ import annotations

import threading
import time
import json
import logging
import os
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

try:
    import redis
except Exception:
    redis = None

try:
    import requests
except Exception:
    requests = None

import asyncio

logger = logging.getLogger("GapConsumer")
logger.addHandler(logging.NullHandler())

# Redis URL 로드 (redis_factory 우선, config.yaml 기반 설정)
REDIS_URL = None
try:
    import importlib.util as _gc_ilu
    import pathlib as _gc_pl
    _gc_factory_path = _gc_pl.Path(__file__).resolve().parent.parent / "01_core" / "database" / "redis_factory.py"
    _gc_spec = _gc_ilu.spec_from_file_location("_redis_factory_gc", str(_gc_factory_path))
    _gc_factory_mod = _gc_ilu.module_from_spec(_gc_spec)  # type: ignore[arg-type]
    _gc_spec.loader.exec_module(_gc_factory_mod)  # type: ignore[union-attr]
    REDIS_URL = _gc_factory_mod.get_redis_url()
    logger.debug("[GapConsumer] redis_factory 로드 성공")
except Exception as _gc_e:
    logger.debug("[GapConsumer] redis_factory 로드 실패 (%s)", _gc_e)

if not REDIS_URL:
    REDIS_URL = os.getenv("REDIS_URL", None)

if not REDIS_URL:
    _gc_password = os.getenv("REDIS_PASSWORD", "dummy")
    REDIS_URL = f"redis://:{_gc_password}@127.0.0.1:58530/0"
    logger.debug("[GapConsumer] 기본 REDIS_URL 사용: %s", REDIS_URL)
GAP_QUEUE = os.getenv("GAP_QUEUE", "gap_fill_queue")
CLAIM_PREFIX = os.getenv("GAP_CLAIM_PREFIX", "gap_job_claim:")
JOB_TTL = int(os.getenv("GAP_JOB_TTL", str(60 * 60)))
PROCESSOR_RETRY_SECONDS = int(os.getenv("PROCESSOR_RETRY_SECONDS", "5"))
WORKER_COUNT = int(os.getenv("GAP_CONSUMER_WORKERS", "1"))
BACKFILL_CHUNK_SIZE = int(os.getenv("GAP_BACKFILL_CHUNK_SIZE", "1000"))
BACKFILL_CHUNK_DELAY_SECONDS = float(os.getenv("GAP_BACKFILL_CHUNK_DELAY", "1.0"))

# ---------------------------------------------------------------------------
# Rate Limiter ???�비??API ?�출 ?�도 ?�한 (초당 최�? 8??
# ---------------------------------------------------------------------------
class UpbitRateLimiter:
    """?�비??API ?�출 ?�도 ?�한 (초당 최�? 8??"""
    def __init__(self, max_calls_per_second: int = 8):
        self.max_calls = max_calls_per_second
        self.calls: List[datetime] = []
        self.lock = threading.Lock()

    def wait_if_needed(self) -> None:
        with self.lock:
            now = datetime.now()
            # 1�??�내 ?�출 기록�??��?
            self.calls = [t for t in self.calls if now - t < timedelta(seconds=1)]
            if len(self.calls) >= self.max_calls:
                sleep_time = 1.0 - (now - self.calls[0]).total_seconds()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.calls = []
            self.calls.append(now)

# 모듈 ?��? 공유 ?�이??리�???(?�러 ?�커가 공유?�여 �??�출 ?�수 ?�한)
_rate_limiter = UpbitRateLimiter(
    max_calls_per_second=int(os.getenv("UPBIT_API_CALLS_PER_SEC", "8"))
)

def _find_processor_callable() -> Optional[Any]:
    """
    ?��??�에 static.processor.process_candle??찾아 반환 (?�으�?None)
    ?�러 ?�보 경로�??�도??
    """
    # Try common component module
    candidates = [
        ("11_server.component.component", "static"),
        ("src.11_server.component.component", "static"),
        ("src.app.bootstrap", "static"),
        ("app.bootstrap", "static"),
    ]
    for mod_name, attr in candidates:
        try:
            mod = __import__(mod_name, fromlist=[attr])
            st = getattr(mod, attr, None)
            if st:
                proc = getattr(st, "processor", None)
                if proc and hasattr(proc, "process_candle"):
                    return proc.process_candle
        except Exception:
            continue
    # Last resort: try 'static' module directly in sys.modules
    try:
        import sys
        st = sys.modules.get("11_server.component.component")
        if st:
            comp = getattr(st, "static", None)
            if comp:
                proc = getattr(comp, "processor", None)
                if proc and hasattr(proc, "process_candle"):
                    return proc.process_candle
    except Exception:
        pass
    return None

class GapConsumerWorker:
    def __init__(self, redis_url: str = REDIS_URL, poll_interval: float = 1.0):
        if redis is None:
            raise RuntimeError("redis ?�키지가 ?�요?�니??)
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._poll_interval = float(poll_interval)
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("GapConsumerWorker ?�작 (thread=%s)", self._thread.name)

    def stop(self):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("GapConsumerWorker 중�?")

    def _claim_job(self, symbol: str, timeframe: str) -> bool:
        key = f"{CLAIM_PREFIX}{symbol}:{timeframe}"
        try:
            ok = self._redis.set(key, "1", nx=True, ex=JOB_TTL)
            return bool(ok)
        except Exception:
            logger.exception("claim ?�패")
            return False

    def _release_claim(self, symbol: str, timeframe: str) -> None:
        key = f"{CLAIM_PREFIX}{symbol}:{timeframe}"
        try:
            self._redis.delete(key)
        except Exception:
            pass

    def _pop_job(self) -> Optional[Dict[str, Any]]:
        try:
            rows = self._redis.zrange(GAP_QUEUE, 0, 0, withscores=True)
            if not rows:
                return None
            member, score = rows[0]
            removed = self._redis.zrem(GAP_QUEUE, member)
            if removed:
                try:
                    job = json.loads(member)
                    return job
                except Exception:
                    return {"member": member, "score": score}
            return None
        except Exception:
            logger.exception("gap ??pop ?�패")
            return None

    def _fetch_from_upbit_rest(self, symbol: str, start_iso: Optional[str], end_iso: Optional[str]) -> List[Dict[str, Any]]:
        if requests is None:
            logger.error("requests 미설�?- REST 백필 불�?")
            return []
        out = []
        url = "https://api.upbit.com/v1/candles/minutes/1"
        params = {"market": symbol, "count": 200}
        to_ts = end_iso
        iterations = 0
        while iterations < 200:
            iterations += 1
            try:
                _rate_limiter.wait_if_needed()  # Rate Limit 체크
                p = dict(params)
                if to_ts:
                    p["to"] = to_ts
                resp = requests.get(url, params=p, timeout=10)
                if resp.status_code != 200:
                    # 429: Rate Limit ?�달 ??5�??��????�재 ?�볼 백필 중단
                    if resp.status_code == 429:
                        logger.warning("Upbit REST Rate Limit ?�달 (429), 5�??��? symbol=%s", symbol)
                        time.sleep(5.0)
                        break
                    else:
                        logger.debug("Upbit REST ?�답 ?�패(%s): %s", resp.status_code, resp.text[:200])
                    break
                data = resp.json()
                if not data:
                    break
                for c in data:
                    candle = {
                        "symbol": symbol,
                        "time": c.get("candle_date_time_utc") or c.get("candle_date_time_kst"),
                        "exchange_ts": c.get("timestamp"),
                        "timeframe": "1m",
                        "open": c.get("opening_price"),
                        "high": c.get("high_price"),
                        "low": c.get("low_price"),
                        "close": c.get("trade_price"),
                        "volume": c.get("candle_acc_trade_volume"),
                        "quote_volume": c.get("candle_acc_trade_price"),
                        "exchange": "upbit",
                        "_raw": c,
                    }
                    out.append(candle)
                earliest = data[-1].get("candle_date_time_utc") or data[-1].get("candle_date_time_kst")
                if not earliest:
                    break
                to_ts = earliest
                if start_iso and earliest <= start_iso:
                    break
                time.sleep(0.2)  # UpbitRateLimiter?� ?�동?�여 Rate Limit 준??
            except Exception:
                logger.exception("Upbit REST page fetch ?�패")
                break
        out.reverse()
        return out

    def _submit_to_pipeline(self, candles: List[Dict[str, Any]]) -> None:
        # Try to find processor, retry for small window
        proc_fn = _find_processor_callable()
        waited = 0
        while proc_fn is None and waited < PROCESSOR_RETRY_SECONDS:
            time.sleep(0.5)
            waited += 0.5
            proc_fn = _find_processor_callable()
        if proc_fn is None:
            logger.error("pipeline processor�?찾을 ???�습?�다. ui.chart�?publish ?�???�용")
            # fallback publish
            for c in candles:
                try:
                    self._redis.publish("ui.chart", json.dumps(c, default=str, ensure_ascii=False))
                except Exception:
                    logger.exception("fallback publish ?�패")
            return

        # submit each candle asynchronously to the processor
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except Exception:
            loop = None

        for c in candles:
            try:
                coro = proc_fn(c)
                try:
                    asyncio.run_coroutine_threadsafe(coro, loop)
                except Exception:
                    # last resort synchronous run (slow)
                    try:
                        asyncio.run(coro)
                    except Exception:
                        logger.exception("process_candle ?�기 ?�행 ?�패")
            except Exception:
                logger.exception("pipeline submit ?�패")

    def _handle_job(self, job: Dict[str, Any]) -> None:
        symbol = job.get("symbol") or job.get("market") or job.get("symbol_id")
        timeframe = job.get("timeframe") or job.get("tf") or "1m"
        start_iso = job.get("start")
        end_iso = job.get("end")
        if not symbol:
            logger.warning("job???�볼 ?�보 ?�음: %s", job)
            return

        if not self._claim_job(symbol, timeframe):
            logger.info("?��? ?�른 worker가 처리�? %s/%s", symbol, timeframe)
            return

        try:
            logger.debug("Backfill ?�작: %s %s -> %s", symbol, start_iso, end_iso)
            candles = self._fetch_from_upbit_rest(symbol, start_iso, end_iso)
            if not candles:
                logger.debug("?�수�?결과 ?�음: %s", symbol)
                return

            # ???�???�이??분할 처리
            if len(candles) > BACKFILL_CHUNK_SIZE:
                logger.warning("[GapConsumer] %s: ?�???�이??%d�? 분할 처리", symbol, len(candles))
                for i in range(0, len(candles), BACKFILL_CHUNK_SIZE):
                    chunk = candles[i:i + BACKFILL_CHUNK_SIZE]
                    logger.info(
                        "[GapConsumer] %s: chunk %d-%d (%d�? ???�이?�라??,
                        symbol, i, min(i + BACKFILL_CHUNK_SIZE, len(candles)), len(chunk),
                    )
                    self._submit_to_pipeline(chunk)
                    time.sleep(BACKFILL_CHUNK_DELAY_SECONDS)  # ??�?�� �??��?(DB 부??분산)
            else:
                logger.info("??[GapConsumer] %s: %d�????�이?�라??, symbol, len(candles))
                self._submit_to_pipeline(candles)
                logger.debug("?�이?�라?�으�??�송 ?�료: %s", symbol)
        except Exception:
            logger.exception("job 처리 �??�외")
        finally:
            try:
                self._release_claim(symbol, timeframe)
            except Exception:
                pass

    def _run(self):
        while not self._stop_evt.is_set():
            try:
                job = self._pop_job()
                if job:
                    self._handle_job(job)
                else:
                    time.sleep(self._poll_interval)
            except Exception:
                logger.exception("GapConsumer 루프 ?�외(무시)")
                time.sleep(self._poll_interval)

class GapConsumerManager:
    def __init__(self, workers: int = WORKER_COUNT, redis_url: str = REDIS_URL, poll_interval: float = 1.0):
        self.workers = workers
        self._instances: List[GapConsumerWorker] = []
        self.redis_url = redis_url
        self.poll_interval = poll_interval

    def start(self):
        if self._instances:
            return
        for i in range(max(1, int(self.workers))):
            w = GapConsumerWorker(redis_url=self.redis_url, poll_interval=self.poll_interval)
            w.start()
            self._instances.append(w)
        logger.info("GapConsumerManager ?�작 - workers=%d", len(self._instances))

    def stop(self):
        for w in self._instances:
            try:
                w.stop()
            except Exception:
                logger.debug("worker stop ?�패", exc_info=True)
        self._instances = []
        logger.info("GapConsumerManager 중�?")
