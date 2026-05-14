# -*- coding: utf-8 -*-
"""
[Purpose]
캔들 데이터 fetch + Redis 실시간 구독 워커

[Responsibilities]
- REST API 캔들 조회 (aiopyupbit)
- Redis 캐시 (TTL 60s)
- Redis Pub/Sub 구독 (ui.chart)
- 실시간 캔들 패치 수신

[Signals]
- data_fetched: 캔들 데이터 fetch 완료
- realtime_candle: 실시간 캔들 패치

[Author] Phase 1-3 (모듈화)
[Created] 2026-01-25
"""
from __future__ import annotations

import io
import os
import sys
import json
import asyncio as aio
import importlib
import importlib.util
from dataclasses import dataclass
from typing import Any, Optional

try:
    import aiopyupbit
    _AIOPYUPBIT_AVAILABLE = True
except ImportError:
    aiopyupbit = None  # type: ignore[assignment]
    _AIOPYUPBIT_AVAILABLE = False

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore[assignment]
    _PANDAS_AVAILABLE = False

# ----------------------------
# PyQt5.QtCore 안전 로드
# ----------------------------
try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    QThread = None
    pyqtSignal = None

    _qt_stub_candidates = [
        "utils.qt_stub",
        "01_core.utils.qt_stub",
        "src.01_core.utils.qt_stub",
        "src.utils.qt_stub",
        "qt_stub",
    ]

    _qtcore_module = None
    for _name in _qt_stub_candidates:
        try:
            mod = importlib.import_module(_name)
            if hasattr(mod, "QtCore"):
                _qtcore_module = getattr(mod, "QtCore")
            else:
                _qtcore_module = mod
            break
        except Exception:
            _qtcore_module = None

    if _qtcore_module is None:
        try:
            _this_dir = os.path.dirname(os.path.abspath(__file__))
            _project_root = os.path.abspath(os.path.join(_this_dir, "..", "..", ".."))
            _candidates_paths = [
                os.path.join(_project_root, "src", "01_core", "utils", "qt_stub.py"),
                os.path.join(_project_root, "01_core", "utils", "qt_stub.py"),
                os.path.join(_project_root, "src", "utils", "qt_stub.py"),
                os.path.join(_project_root, "utils", "qt_stub.py"),
            ]
            for _p in _candidates_paths:
                if os.path.isfile(_p):
                    spec = importlib.util.spec_from_file_location("qt_stub_fallback", _p)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "QtCore"):
                            _qtcore_module = getattr(mod, "QtCore")
                        else:
                            _qtcore_module = mod
                        break
        except Exception:
            _qtcore_module = None

    if _qtcore_module is None:
        class _MinimalSignal:
            def __init__(self, *args, **kwargs):
                pass
            def __call__(self, *args, **kwargs):
                return None

        class _MinimalQThread:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                pass
            def quit(self):
                pass
            def wait(self, timeout=None):
                return True

        class _MinimalQtCore:
            QThread = _MinimalQThread
            pyqtSignal = staticmethod(lambda *a, **kw: _MinimalSignal())

        _qtcore_module = _MinimalQtCore()

    try:
        QThread = getattr(_qtcore_module, "QThread", QThread)
    except Exception:
        QThread = QThread or type("QThreadStub", (), {})
    try:
        pyqtSignal = getattr(_qtcore_module, "pyqtSignal", pyqtSignal)
    except Exception:
        pyqtSignal = pyqtSignal or (lambda *a, **kw: (lambda *x, **y: None))

import logging
log = logging.getLogger(__name__)

if not _AIOPYUPBIT_AVAILABLE:
    log.warning("[CandleFetchWorker] aiopyupbit 패키지가 설치되지 않았습니다. pip install aiopyupbit 로 기능을 활성화하세요.")
if not _PANDAS_AVAILABLE:
    log.warning("[CandleFetchWorker] pandas 패키지가 설치되지 않았습니다. pip install pandas 로 기능을 활성화하세요.")

# Redis import with graceful fallback
try:
    import importlib as _importlib
    _redis_pkg = _importlib.import_module('redis')
    _redis_from_url = getattr(_redis_pkg, 'from_url', None)
    _Redis = getattr(_redis_pkg, 'Redis', None)
    _redis_exceptions = getattr(_redis_pkg, 'exceptions', None)
    if _Redis is None:
        raise ImportError("redis.Redis not found")
    REDIS_AVAILABLE = True
except Exception:
    _redis_pkg = None
    _redis_from_url = None
    _Redis = None
    _redis_exceptions = None
    REDIS_AVAILABLE = False
    log.warning("[CandleFetchWorker] redis 패키지가 설치되지 않았습니다. pip install redis 로 기능을 활성화하세요.")


@dataclass(frozen=True)
class CandleRequest:
    """캔들 요청 (불변 객체)"""
    code: str
    interval: str
    count: int
    to: Optional[Any] = None


class CandleFetchWorker(QThread):
    """
    캔들 fetch + Redis 실시간 구독 워커
    """

    data_fetched = pyqtSignal(dict)
    realtime_candle = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.alive = False
        self._event_loop: Optional[aio.AbstractEventLoop] = None

        # Redis 연결 초기화 (redis_factory 최우선)
        self.redis = None
        if REDIS_AVAILABLE:
            try:
                redis_url = None
                
                # 1순위: redis_factory (config.yaml 기반)
                try:
                    import importlib.util as _ilu
                    import pathlib as _pl
                    _factory_path = _pl.Path(__file__).resolve().parent.parent.parent / "01_core" / "database" / "redis_factory.py"
                    _spec = _ilu.spec_from_file_location("_redis_factory_cw", str(_factory_path))
                    _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
                    _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
                    redis_url = _factory_mod.get_redis_url()
                    log.debug("[CandleFetchWorker] redis_factory 로드 성공: %s", redis_url)
                except Exception as _e:
                    log.debug("[CandleFetchWorker] redis_factory 로드 실패 (%s), fallback 시도", _e)

                # 2순위: 환경변수 (REDIS_URL)
                if not redis_url:
                    redis_url = os.getenv("REDIS_URL", None)
                    if redis_url:
                        log.debug("[CandleFetchWorker] REDIS_URL 환경변수 사용: %s", redis_url)

                # 3순위: 기본값 (포트 58530)
                if not redis_url:
                    _password = os.getenv("REDIS_PASSWORD", "dummy")
                    _host = os.getenv("REDIS_HOST", "127.0.0.1")
                    _port = int(os.getenv("REDIS_PORT", "58530"))
                    _db = int(os.getenv("REDIS_DB", "0"))
                    redis_url = f"redis://:{_password}@{_host}:{_port}/{_db}"
                    log.debug("[CandleFetchWorker] 기본 Redis URL 사용: %s", redis_url)

                # Redis 연결 시도 (URL 파싱을 직접 수행하여 호환성 확보)
                if redis_url and _Redis:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(redis_url)
                        self.redis = _Redis(
                            host=parsed.hostname or '127.0.0.1',
                            port=parsed.port or 58530,
                            db=int(parsed.path.strip('/') or '0'),
                            password=parsed.password,
                            decode_responses=True
                        )
                        self.redis.ping()
                        log.info("[CandleFetchWorker] ✅ Redis 연결 성공: %s", redis_url)
                    except Exception as e:
                        log.warning("[CandleFetchWorker] Redis ping 실패: %s", e)
                        self.redis = None

            except Exception as e:
                log.warning("[CandleFetchWorker] Redis 초기화 실패: %s", e)
                self.redis = None
        
        self._pending_req: Optional[CandleRequest] = None
        self._pending_id: int = 0
        self._last_cache_key: Optional[str] = None
        self._poll_interval_sec = 0.05

        self._redis_pubsub = None
        self._current_symbol = "KRW-BTC"
        self._current_timeframe = "minute1"

        # API rate limiting
        self._api_call_delay = 0.15
        self._consecutive_calls = 0
        self._max_consecutive_calls = 5
        self._rate_limit_cooldown = 1.0
        self._rate_limit_retry_delay = 3.0

    def run(self) -> None:
        self.alive = True
        if sys.platform == 'win32':
            try:
                aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass
        loop = aio.new_event_loop()
        self._event_loop = loop
        aio.set_event_loop(loop)

        log.info("[CandleFetchWorker] Started")

        try:
            if self.redis:
                try:
                    self._redis_pubsub = self.redis.pubsub()
                    self._redis_pubsub.subscribe("ui.chart")
                    log.debug("[CandleFetchWorker] Redis Pub/Sub subscribed: ui.chart")
                except Exception as e:
                    try:
                        if _redis_exceptions is not None:
                            auth_exc = getattr(_redis_exceptions, 'AuthenticationError', None)
                            if auth_exc and isinstance(e, auth_exc):
                                log.warning(f"[CandleFetchWorker] Redis Pub/Sub subscribe failed (auth): {e}")
                            else:
                                log.warning(f"[CandleFetchWorker] Redis Pub/Sub subscribe failed: {e}")
                        else:
                            log.warning(f"[CandleFetchWorker] Redis Pub/Sub subscribe failed: {e}")
                    except Exception:
                        log.warning(f"[CandleFetchWorker] Redis Pub/Sub subscribe failed: {e}")
                    self._redis_pubsub = None
        except Exception as e:
            log.warning(f"[CandleFetchWorker] Redis Pub/Sub init error: {e}")
            self._redis_pubsub = None

        try:
            loop.run_until_complete(self._loop())
        except Exception as e:
            log.error(f"[CandleFetchWorker] Worker loop crashed: {e}", exc_info=True)
        finally:
            try:
                if self._redis_pubsub:
                    try:
                        self._redis_pubsub.close()
                    except Exception:
                        pass
                if self.redis:
                    try:
                        if hasattr(self.redis, "close"):
                            self.redis.close()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                try:
                    try:
                        loop.run_until_complete(loop.shutdown_asyncgens())
                    except Exception:
                        pass
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
            except Exception:
                pass

            self._event_loop = None
            log.info("[CandleFetchWorker] Stopped")

    def stop(self) -> None:
        self.alive = False
        try:
            loop = getattr(self, "_event_loop", None)
            if loop and loop.is_running():
                try:
                    aio.run_coroutine_threadsafe(self._stop_coro(), loop)
                except Exception:
                    pass
        except Exception:
            pass

    async def _stop_coro(self) -> None:
        try:
            self.alive = False
        except Exception:
            pass
        return None

    def close(self) -> None:
        try:
            self.stop()
            try:
                self.quit()
            except Exception:
                pass
            try:
                self.wait(5000)
            except Exception:
                pass
        except Exception:
            pass

    def request_fetch(self, req: CandleRequest) -> int:
        self._pending_id += 1
        self._pending_req = req
        self._current_symbol = req.code
        return self._pending_id

    def set_symbol_timeframe(self, symbol: str, timeframe: str):
        self._current_symbol = symbol
        self._current_timeframe = timeframe

    def _make_cache_key(self, req: CandleRequest) -> str:
        to_part = ""
        if req.to is not None:
            try:
                to_part = f":to={req.to.isoformat()}"
            except Exception:
                to_part = f":to={str(req.to)}"
        return f"candle:{req.code}:{req.interval}:{req.count}{to_part}"

    async def _loop(self) -> None:
        while self.alive:
            try:
                if self._redis_pubsub:
                    try:
                        message = self._redis_pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=0.001,
                        )
                    except Exception as e:
                        log.debug(f"[CandleFetchWorker] Pub/Sub get_message error: {e}")
                        message = None

                    if message and message.get("type") == "message":
                        try:
                            await self._handle_realtime_candle(message)
                        except Exception as e:
                            log.debug(f"[CandleFetchWorker] _handle_realtime_candle failed: {e}", exc_info=True)

                await aio.sleep(self._poll_interval_sec)

                req = self._pending_req
                if req is None:
                    continue

                req_id = self._pending_id
                self._pending_req = None

                cache_key = self._make_cache_key(req)
                if cache_key == self._last_cache_key:
                    continue
                self._last_cache_key = cache_key

                try:
                    df = await self._get_df(req=req, cache_key=cache_key)
                except Exception as e:
                    log.error(f"[CandleFetchWorker] _get_df failed: {e}", exc_info=True)
                    df = None

                try:
                    self.data_fetched.emit(
                        {
                            "req": req,
                            "df": df,
                            "cache_key": cache_key,
                            "request_id": req_id,
                        }
                    )
                except Exception:
                    log.debug("[CandleFetchWorker] data_fetched.emit failed", exc_info=True)

            except Exception as e:
                log.error(f"[CandleFetchWorker] Loop error: {e}", exc_info=True)
                try:
                    await aio.sleep(0.1)
                except Exception:
                    pass

    async def _handle_realtime_candle(self, message: dict):
        try:
            data_str = message.get("data")
            if not data_str:
                return
            candle = json.loads(data_str)

            if candle.get("symbol") != self._current_symbol:
                return

            tf_map = {
                "min_1": "minute1",
                "min_3": "minute3",
                "min_5": "minute5",
                "min_10": "minute10",
                "min_15": "minute15",
                "min_30": "minute30",
                "min_60": "minute60",
                "min_240": "minute240",
                "day": "day",
                "week": "week",
                "month": "month",
            }

            candle_tf = candle.get("timeframe", "")
            mapped_tf = tf_map.get(candle_tf, candle_tf)

            if mapped_tf != self._current_timeframe:
                return

            try:
                self.realtime_candle.emit(candle)
            except Exception:
                log.debug("[CandleFetchWorker] realtime_candle.emit failed", exc_info=True)

        except Exception as e:
            log.error(f"[CandleFetchWorker] Realtime candle parse error: {e}", exc_info=True)

    async def _get_df(self, req: CandleRequest, cache_key: str) -> Any:
        if not _AIOPYUPBIT_AVAILABLE or not _PANDAS_AVAILABLE:
            log.warning("[CandleFetchWorker] aiopyupbit 또는 pandas 패키지가 설치되지 않았습니다.")
            return None

        cached = None

        try:
            if self.redis:
                try:
                    cached = self.redis.get(cache_key)
                except Exception as e:
                    log.debug(f"[CandleFetchWorker] Redis get failed for {cache_key}: {e}")
                    cached = None
        except Exception:
            cached = None

        if cached:
            try:
                return pd.read_json(io.StringIO(cached))
            except Exception:
                pass

        if self._consecutive_calls >= self._max_consecutive_calls:
            log.warning(
                f"[CandleFetchWorker] Rate limit: {self._consecutive_calls} consecutive calls, waiting {self._rate_limit_cooldown}s"
            )
            await aio.sleep(self._rate_limit_cooldown)
            self._consecutive_calls = 0

        kwargs = {
            "ticker": req.code,
            "interval": req.interval,
            "count": int(req.count),
        }
        if req.to is not None:
            kwargs["to"] = req.to

        try:
            df = await aiopyupbit.get_ohlcv(**kwargs)
            self._consecutive_calls += 1
            await aio.sleep(self._api_call_delay)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "요청 수 제한" in error_str or "Too Many Requests" in error_str:
                log.warning(
                    f"[CandleFetchWorker] API rate limit (429) hit, waiting {self._rate_limit_retry_delay}s before retry..."
                )
                await aio.sleep(self._rate_limit_retry_delay)
                self._consecutive_calls = 0
                try:
                    df = await aiopyupbit.get_ohlcv(**kwargs)
                    log.debug("[CandleFetchWorker] Retry after rate limit successful")
                except Exception as retry_error:
                    log.error(f"[CandleFetchWorker] Retry after rate limit failed: {retry_error}", exc_info=True)
                    raise
            else:
                raise

        try:
            if self.redis and df is not None:
                try:
                    empty = False
                    try:
                        empty = df.empty
                    except Exception:
                        empty = False
                    if not empty:
                        self.redis.setex(cache_key, 60, df.to_json())
                except Exception as e:
                    log.debug(f"[CandleFetchWorker] Redis setex failed for {cache_key}: {e}")
        except Exception:
            pass

        return df