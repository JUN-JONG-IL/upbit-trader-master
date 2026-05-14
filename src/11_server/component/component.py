#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
RealtimeManager module (fixed imports + robust initialization)

- 목적: 실시간 자산(코인) 관리, WebSocket 이벤트 수신/동기화, 계정 동기화 등 런타임 로직 제공
- 변경: timescale_redis 모듈은 importlib로 동적 로드(식별자에 숫자 포함된 패키지명 안전 처리)
         WebsocketManager.is_alive 재귀 제거
         Redis 발행 시 timescale_redis.publish_status 사용(있을 때)
         server.static import를 레포 구조에 맞게 안전하게 시도하고, 실패 시 경고 대신 디버그로 처리
"""
from __future__ import annotations

import os
import json
import uuid
import time
import asyncio as aio
import logging
import importlib
from dataclasses import dataclass
from threading import Thread, Lock
from queue import Queue
from typing import Dict, List, Optional, Union, Any

# optional third-party libs
try:
    import websockets
except Exception:
    websockets = None  # runtime will handle absence
try:
    import aiopyupbit
except Exception:
    aiopyupbit = None

# --- server.static 로드: 레포 구조를 존중한 견고한 시도 ---
# 임시 로거(폴백)
_temp_logger = logging.getLogger("RealtimeManager")
if not _temp_logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 후보 모듈명 목록 (레포 구조에 따라 확장)
_static_candidates = [
    "11_server.server.static",
    "src.11_server.server.static",
    "11_server.app.static",
    "src.11_server.app.static",
    "server.static",
    "src.server.static",
    "static",
    "src.static",
]

static = None  # will be module if found, otherwise None
log = _temp_logger

_static_attempts = []
for _cand in _static_candidates:
    try:
        mod = importlib.import_module(_cand)
        static = mod
        # prefer mod.log if present
        mod_log = getattr(mod, "log", None)
        if mod_log is not None:
            log = mod_log
            log.info("[component] server.static loaded from %s -> %s", _cand, getattr(mod, "__file__", None))
        else:
            # use temp logger but record where it came from
            log = _temp_logger
            log.info("[component] server.static loaded from %s -> %s (using fallback logger)", _cand, getattr(mod, "__file__", None))
        break
    except Exception as e:
        _static_attempts.append((_cand, f"{type(e).__name__}: {e}"))
# If not found, keep debug-level summary only (avoid noisy output)
if static is None:
    log = _temp_logger
    log.debug("[component] server.static not found among candidates; using fallback logger. attempts=%s", _static_attempts)
# ---------------------------------------------------------

# Try to dynamically import timescale_redis (package name contains digits so avoid direct from-import)
timescale_redis = None
_ts_attempts = []
for name in ("src.data_01.timescale.timescale_redis", "data_01.timescale.timescale_redis", "timescale.timescale_redis", "src.timescale.timescale_redis"):
    try:
        timescale_redis = importlib.import_module(name)
        log.debug("[component] timescale_redis imported from %s -> %s", name, getattr(timescale_redis, "__file__", None))
        break
    except Exception as ex:
        _ts_attempts.append((name, f"{type(ex).__name__}: {ex}"))
if timescale_redis is None:
    log.debug("[component] timescale_redis not available; attempts=%s", _ts_attempts)

# ============================================
# Phase 2.1: Redis 클라이언트 import
# ============================================
try:
    import redis
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False
    log.warning("[RealtimeManager] Redis not available (pip install redis)")

# ----------------------------
# Helper: Upbit REST market fetch (sync)
# ----------------------------
def _fetch_all_upbit_markets_sync(limit: int = 300) -> List[dict]:
    """
    Upbit REST /v1/market/all 호출하여 시장 목록(dict list)을 반환합니다.
    실패 시 빈 리스트 반환. limit으로 결과 수 제한 가능.
    """
    try:
        import requests  # local import to avoid mandatory dependency unless helper used
    except Exception:
        log.debug("[RealtimeManager] requests not available, cannot fetch markets from Upbit REST")
        return []

    try:
        url = "https://api.upbit.com/v1/market/all"
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        if limit and len(data) > limit:
            return data[:limit]
        return data
    except Exception as e:
        log.warning("[RealtimeManager] Upbit REST market fetch failed: %s", e)
        return []

# ----------------------------
# Coin
# ----------------------------
class Coin:
    def __init__(self, code: dict) -> None:
        # Expect code to be a dict containing at least "market" key
        self.code = code.get("market", "") if isinstance(code, dict) else str(code)
        self.korean_name = code.get("korean_name", "") if isinstance(code, dict) else ""
        self.english_name = code.get("english_name", "") if isinstance(code, dict) else ""

        self.ticker = {
            "ty": "ticker",
            "cd": "",
            "op": 0,
            "hp": 0,
            "lp": 0,
            "tp": 0,
            "pcp": 0,
            "atp": 0,
            "c": "RISE",
            "cp": 0,
            "scp": 0,
            "cr": 0,
            "scr": 0,
            "ab": "BID",
            "tv": 0,
            "atv": 0,
            "tdt": "0",
            "ttm": "0",
            "ttms": 0,
            "aav": 0,
            "abv": 0,
            "h52wp": 0,
            "h52wdt": "NONE",
            "l52wp": 0,
            "l52wdt": "NONE",
            "ts": None,
            "ms": "UNKNOWN",
            "msfi": None,
            "its": False,
            "dd": None,
            "mw": "NONE",
            "tms": 0,
            "atp24h": 0,
            "atv24h": 0,
            "st": "SNAPSHOT",
        }
        self.orderbook = {
            "ty": "orderbook",
            "cd": "",
            "tms": 0,
            "tas": 0,
            "tbs": 0,
            "obu": [],
            "st": "SNAPSHOT",
        }

        self.old_price = 0.0
        self.old_trade = 0.0
        self.old_time = 0

    def get_code(self, fiat: bool = True) -> str:
        return self.code if fiat else self.code.split("-")[-1] if self.code else ""

    def get_opening_price(self) -> float: return self.ticker.get("op", 0)
    def get_high_price(self) -> float: return self.ticker.get("hp", 0)
    def get_low_price(self) -> float: return self.ticker.get("lp", 0)
    def get_trade_price(self) -> float: return self.ticker.get("tp", 0)
    def get_prev_closing_price(self) -> float: return self.ticker.get("pcp", 0)
    def get_acc_trade_price(self) -> float: return self.ticker.get("atp", 0)
    def get_change(self) -> str: return self.ticker.get("c", "")
    def get_change_price(self) -> float: return self.ticker.get("cp", 0)
    def get_signed_change_price(self) -> float: return self.ticker.get("scp", 0)
    def get_change_rate(self) -> float: return self.ticker.get("cr", 0)
    def get_signed_change_rate(self) -> float: return self.ticker.get("scr", 0)
    def get_ask_bid(self) -> str: return self.ticker.get("ab", "")
    def get_trade_volume(self) -> float: return self.ticker.get("tv", 0)
    def get_acc_trade_volume(self) -> float: return self.ticker.get("atv", 0)
    def get_trade_date(self) -> str: return self.ticker.get("tdt", "0")
    def get_trade_time(self) -> str: return self.ticker.get("ttm", "0")
    def get_trade_timestamp(self) -> int: return self.ticker.get("ttms", 0)
    def get_acc_ask_volume(self) -> float: return self.ticker.get("aav", 0)
    def get_acc_bid_volume(self) -> float: return self.ticker.get("abv", 0)
    def get_highest_52_week_price(self) -> float: return self.ticker.get("h52wp", 0)
    def get_highest_52_week_date(self) -> str: return self.ticker.get("h52wdt", "NONE")
    def get_lowest_52_week_price(self) -> float: return self.ticker.get("l52wp", 0)
    def get_lowest_52_week_date(self) -> str: return self.ticker.get("l52wdt", "NONE")
    def get_trade_status(self) -> str: return self.ticker.get("ts", "")
    def get_market_state_for_ios(self) -> str: return self.ticker.get("msfi", "")
    def get_market_state(self) -> str: return self.ticker.get("ms", "")
    def get_is_trading_suspended(self) -> bool: return self.ticker.get("its", False)
    def get_delisting_date(self) -> str: return self.ticker.get("dd", "")
    def get_market_warning(self) -> str: return self.ticker.get("mw", "")
    def get_timestamp(self) -> int: return self.ticker.get("tms", 0)
    def get_acc_trade_price_24h(self) -> float: return self.ticker.get("atp24h", 0)
    def get_acc_trade_volume_24h(self) -> float: return self.ticker.get("atv24h", 0)
    def get_stream_type(self) -> str: return self.ticker.get("st", "")

    def get_total_ask_size(self) -> float: return self.orderbook.get("tas", 0)
    def get_total_bid_size(self) -> float: return self.orderbook.get("tbs", 0)

    def get_orderbook_units(self, _index: int = 0) -> Union[dict, list]:
        obu = self.orderbook.get("obu", [])
        if _index == 0:
            return obu
        if isinstance(obu, list) and _index < len(obu):
            return obu[_index]
        return {}

# ----------------------------
# WebsocketManager
# ----------------------------
class WebsocketManager(Thread):
    """
    WebSocket 연결 관리 (재연결 지원)
    - 로그를 과도하게 찍지 않도록 INFO는 상태 중심, DEBUG는 상세(필요 시)로 유지
    """

    def __init__(self, uri: str, request: str, ping_interval: int, queue: Queue, name: str) -> None:
        super().__init__(daemon=True, name=name)
        self.uri = uri
        self.request = request
        self.ping_interval = int(ping_interval)
        self._queue = queue
        self._alive = False

        # 재연결 로직 강화
        self.reconnect_delay = 1  # 초기 1초
        self.max_reconnect_delay = 60  # 최대 60초
        self.reconnect_count = 0
        self.subscribed_symbols = set()  # 구독 복원용

        # 메트릭스
        self.connection_start_time = None
        self.total_messages = 0

    def stop(self) -> None:
        """WebSocket 연결 중지"""
        log.info(f"[WebSocket] Stopping {self.name}...")
        self._alive = False

    def is_alive(self) -> bool:
        # avoid recursive call; use Thread.is_alive via super()
        try:
            return self._alive and super().is_alive()
        except Exception:
            return self._alive

    def run(self) -> None:
        """Thread 실행 진입점"""
        log.info(f"[WebSocket] Thread start: {self.name}")
        log.debug(f"[WebSocket] Config: uri={self.uri}, ping_interval={self.ping_interval}")

        self._alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._connect_loop())
        except Exception as e:
            log.error(f"[WebSocket] Fatal error in {self.name}: {e}")
        finally:
            try:
                loop.stop()
                loop.close()
            except Exception:
                pass
            log.info(f"[WebSocket] Thread stopped: {self.name}")

    async def _connect_loop(self) -> None:
        """
        WebSocket 연결 루프 (지수 백오프 재연결 지원)
        """
        if websockets is None:
            log.error("[WebsocketManager] websockets package not available; cannot connect.")
            return

        attempt = 0

        while self._alive:
            try:
                if attempt == 0:
                    log.info(f"[WebSocket] Connecting: {self.name}")
                else:
                    log.info(f"[WebSocket] Reconnecting: {self.name} (attempt #{attempt})")

                async with websockets.connect(
                    self.uri,
                    ping_interval=self.ping_interval,
                    close_timeout=10,
                    max_size=10_000_000
                ) as websocket:
                    log.info(f"[WebSocket] Connected: {self.name}")

                    try:
                        await websocket.send(self.request)
                        log.debug(f"[WebSocket] Subscription request sent for {self.name} (truncated)")
                    except Exception as e:
                        log.warning(f"[WebSocket] Subscription send failed for {self.name}: {e}")

                    self.connection_start_time = time.time()
                    self.reconnect_delay = 1
                    attempt = 0

                    if self.subscribed_symbols:
                        log.debug(f"[WebSocket] Restoring {len(self.subscribed_symbols)} subscriptions for {self.name}")
                        await self._restore_subscriptions(websocket)

                    while self._alive:
                        try:
                            message = await websocket.recv()

                            if isinstance(message, (bytes, bytearray)):
                                try:
                                    payload = json.loads(message.decode("utf-8"))
                                except Exception as decode_error:
                                    log.debug(f"[WebSocket] Decode error (skipping): {decode_error}")
                                    continue
                            else:
                                payload = json.loads(message)

                            # push into queue for RealtimeManager consumer
                            try:
                                self._queue.put(payload, block=False)
                            except Exception:
                                self._queue.put(payload)
                            self.total_messages += 1

                            if self.total_messages % 10000 == 0:
                                log.debug(f"[WebSocket] {self.name}: {self.total_messages} messages received")

                        except websockets.exceptions.ConnectionClosed:
                            log.warning(f"[WebSocket] Connection closed: {self.name}")
                            break
                        except Exception as recv_error:
                            log.error(f"[WebSocket] Receive error on {self.name}: {recv_error}")
                            break

            except Exception as e:
                attempt += 1
                self.reconnect_count += 1
                log.warning(f"[WebSocket] Connection failed ({self.name}): {e}")

                if self._alive:
                    log.info(f"[WebSocket] Waiting {self.reconnect_delay}s before reconnect ({self.name})")
                    await aio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def _restore_subscriptions(self, websocket):
        """구독 복원 (필요 시 확장)"""
        return

# ----------------------------
# Realtime Manager
# ----------------------------
@dataclass
class RealtimeOptions:
    ping_interval: int = 60
    redis_enabled: bool = True  # Phase 2.1: Redis 활성화


class RealtimeManager:
    """
    실시간 데이터 관리 (Ticker + Orderbook)
    """

    def __init__(self, codes: Optional[list] = None, ping_interval: int = 60, redis_enabled: bool = True) -> None:
        # 안전망: 입력 codes가 비어있거나 None인 경우 Upbit REST에서 전체 마켓 목록을 조회해 사용
        if not codes:
            # config_loader 에서 최대 구독 수 읽기 (환경변수 > config.yaml > 기본값 300)
            try:
                import importlib.util as _ilu
                from pathlib import Path as _Path
                _cfg_path = _Path(__file__).resolve().parents[3] / "data_01" / "ui" / "utils" / "config_loader.py"
                _spec = _ilu.spec_from_file_location("config_loader", str(_cfg_path))
                if _spec and _spec.loader:
                    _mod = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
                    max_sub = _mod.get_ws_max_subscribe()
                else:
                    raise ImportError("config_loader spec 없음")
            except Exception:
                max_sub = int(os.getenv("UPBIT_WS_MAX_SUBSCRIBE", "300"))
            fetched = _fetch_all_upbit_markets_sync(limit=max_sub)
            if fetched:
                codes = fetched
                log.info("[RealtimeManager] No initial codes provided; populated %d markets from Upbit REST (limit=%d)",
                         len(codes), max_sub)
            else:
                codes = []
                log.warning("[RealtimeManager] No initial codes and Upbit REST returned none; RealtimeManager will initialize with no codes")

        # 기존 기대 형태: codes는 list[dict] with key 'market' OR list[str]
        try:
            if codes and isinstance(codes[0], dict):
                self.codes: List[str] = [x.get("market", "") for x in codes if x.get("market")]
                self.coins: Dict[str, Coin] = {c["market"]: Coin(c) for c in codes if c.get("market")}
            elif codes and isinstance(codes[0], str):
                # already list of symbol strings
                self.codes: List[str] = [str(x).strip() for x in codes if x]
                self.coins: Dict[str, Coin] = {m: Coin({"market": m}) for m in self.codes}
            else:
                self.codes = []
                self.coins = {}
        except Exception as exc:
            log.exception("[RealtimeManager] Failed to initialize codes/coins: %s", exc)
            try:
                self.codes = [str(x) for x in codes] if codes else []
            except Exception:
                self.codes = []
            self.coins = {m: Coin({"market": m}) for m in self.codes}

        self.uri = "wss://api.upbit.com/websocket/v1"
        self.alive = False
        self._queue: Queue = Queue()

        self.options = RealtimeOptions(ping_interval=ping_interval, redis_enabled=redis_enabled)

        self._ws_ticker: Optional[WebsocketManager] = None
        self._ws_orderbook: Optional[WebsocketManager] = None

        self._orderbook_symbol_current: Optional[str] = None
        self._orderbook_lock = Lock()

        self._consumer_thread: Optional[Thread] = None

        # Phase 2.1: Redis 클라이언트 초기화 (환경변수 우선, URL 우선처리)
        self.redis_client = None
        if redis_enabled and REDIS_AVAILABLE:
            try:
                redis_url = os.getenv("REDIS_URL", None)
                if redis_url:
                    try:
                        self.redis_client = redis.from_url(redis_url, decode_responses=True)
                        self.redis_client.ping()
                        log.info("[RealtimeManager] ✅ Redis connected via REDIS_URL (publishing enabled)")
                    except Exception as e:
                        log.warning("[RealtimeManager] Redis.from_url failed: %s", e)
                        self.redis_client = None

                if not self.redis_client:
                    redis_kwargs = {
                        "host": os.getenv("REDIS_HOST", "localhost"),
                        "port": int(os.getenv("REDIS_PORT", 6379)),
                        "db": int(os.getenv("REDIS_DB", 0)),
                        "decode_responses": True,
                    }
                    password = os.getenv("REDIS_PASSWORD", None)
                    if password:
                        redis_kwargs["password"] = password

                    try:
                        self.redis_client = redis.Redis(**redis_kwargs)
                        self.redis_client.ping()
                        log.info("[RealtimeManager] ✅ Redis connected (publishing enabled)")
                    except Exception as e:
                        try:
                            auth_exc = redis.exceptions.AuthenticationError
                            if isinstance(e, auth_exc):
                                log.warning("[RealtimeManager] Redis authentication failed: %s", e)
                            else:
                                log.warning("[RealtimeManager] Redis connection failed: %s", e)
                        except Exception:
                            log.warning("[RealtimeManager] Redis connection failed: %s", e)
                        self.redis_client = None

            except Exception as e:
                log.warning("[RealtimeManager] Redis initialization error: %s", e)
                self.redis_client = None

        log.info("[RealtimeManager] Initialized (codes=%d, redis=%s)", len(self.codes), "enabled" if self.redis_client else "disabled")

    def _build_ticker_request(self) -> str:
        return json.dumps(
            [
                {"ticket": str(uuid.uuid4())[:6]},
                {"type": "ticker", "codes": self.codes, "isOnlyRealtime": False},
                {"format": "SIMPLE"},
            ]
        )

    def _build_orderbook_request(self, symbol: str) -> str:
        return json.dumps(
            [
                {"ticket": str(uuid.uuid4())[:6]},
                {"type": "orderbook", "codes": [symbol], "isOnlyRealtime": False},
                {"format": "SIMPLE"},
            ]
        )

    def get_coin(self, code: str) -> Optional[Coin]:
        return self.coins.get(code)

    def start(self) -> None:
        """RealtimeManager 시작"""
        if self.alive:
            return

        log.info("[RealtimeManager] Starting...")
        self.alive = True

        # Ticker WebSocket 시작
        log.info("[RealtimeManager] Starting ticker WebSocket (%d coins)", len(self.codes))
        self._ws_ticker = WebsocketManager(
            uri=self.uri,
            request=self._build_ticker_request(),
            ping_interval=self.options.ping_interval,
            queue=self._queue,
            name="ticker",
        )
        self._ws_ticker.start()

        # Consumer 스레드 시작
        log.debug("[RealtimeManager] Starting message consumer thread")
        self._consumer_thread = Thread(target=self._consume_loop, daemon=True, name="consumer")
        self._consumer_thread.start()

        log.info("[RealtimeManager] Started")

    def stop(self) -> None:
        """RealtimeManager 중지"""
        log.info("[RealtimeManager] Stopping...")
        self.alive = False

        try:
            if self._ws_ticker:
                self._ws_ticker.stop()
        except Exception:
            pass
        try:
            if self._ws_orderbook:
                self._ws_orderbook.stop()
        except Exception:
            pass

        log.info("[RealtimeManager] Stopped")

    def set_orderbook_symbols(self, symbols: List[str]) -> None:
        """
        Orderbook 구독 종목 변경
        """
        if not symbols:
            return
        symbol = str(symbols[0]).strip()

        with self._orderbook_lock:
            if symbol == self._orderbook_symbol_current and self._ws_orderbook and getattr(self._ws_orderbook, "is_alive", lambda: False)():
                log.debug("[RealtimeManager] Orderbook already subscribed: %s", symbol)
                return

            self._orderbook_symbol_current = symbol

            try:
                if self._ws_orderbook:
                    log.info("[RealtimeManager] Stopping previous orderbook WebSocket...")
                    try:
                        self._ws_orderbook.stop()
                    except Exception:
                        pass
            except Exception:
                pass

            log.info("[RealtimeManager] Starting orderbook WebSocket for %s", symbol)
            self._ws_orderbook = WebsocketManager(
                uri=self.uri,
                request=self._build_orderbook_request(symbol),
                ping_interval=self.options.ping_interval,
                queue=self._queue,
                name=f"orderbook:{symbol}",
            )
            self._ws_orderbook.start()

            log.debug("[RealtimeManager] set_orderbook_symbols -> ['%s']", symbol)

    def _extract_orderbook_units_raw(self, msg: Dict[str, Any]) -> List[dict]:
        """Orderbook units 추출 (다양한 키 형태 지원)"""
        v = msg.get("obu")
        if isinstance(v, list):
            return v
        v = msg.get("orderbook_units")
        if isinstance(v, list):
            return v
        v = msg.get("units")
        if isinstance(v, list):
            return v
        return []

    def _normalize_obu_units(self, units: List[dict]) -> List[dict]:
        """
        OrderbookWidget이 기대하는 키(ap/as/bp/bs)로 정규화
        """
        out: List[dict] = []
        for u in units:
            if not isinstance(u, dict):
                continue

            if all(k in u for k in ("ap", "as", "bp", "bs")):
                out.append(u)
                continue

            if all(k in u for k in ("ask_price", "ask_size", "bid_price", "bid_size")):
                out.append({
                    "ap": u.get("ask_price"),
                    "as": u.get("ask_size"),
                    "bp": u.get("bid_price"),
                    "bs": u.get("bid_size"),
                })
                continue

            ap = u.get("ap") or u.get("ask_price") or u.get("askPrice")
            a_s = u.get("as") or u.get("ask_size") or u.get("askSize")
            bp = u.get("bp") or u.get("bid_price") or u.get("bidPrice")
            b_s = u.get("bs") or u.get("bid_size") or u.get("bidSize")
            if ap is not None and a_s is not None and bp is not None and b_s is not None:
                out.append({"ap": ap, "as": a_s, "bp": bp, "bs": b_s})
        return out

    def _consume_loop(self) -> None:
        """
        메시지 소비 루프 (큐 처리)
        """
        log.info("[RealtimeManager] Message consumer started")
        message_count = 0
        redis_publish_count = 0

        while self.alive:
            try:
                message = self._queue.get()
                if not isinstance(message, dict):
                    continue

                message_count += 1

                if message_count % 10000 == 0:
                    log.debug("[RealtimeManager] Processed %d messages", message_count)

                ty = message.get("ty") or message.get("type")
                cd_raw = message.get("cd") or message.get("code")
                if not ty or cd_raw is None:
                    continue

                cd = str(cd_raw).strip()
                coin = self.coins.get(cd)
                if not coin:
                    log.debug("[RealtimeManager] Unknown coin code: %s", cd)
                    continue

                if ty == "ticker":
                    coin.ticker = message

                    if self.redis_client:
                        try:
                            channel = f"md:last:{cd}:ticker"
                            # use timescale_redis.publish_status if available to ensure channel registry
                            if timescale_redis and hasattr(timescale_redis, "publish_status"):
                                try:
                                    timescale_redis.publish_status(self.redis_client, channel, message)
                                except Exception as e:
                                    log.warning("[RealtimeManager] timescale_redis.publish_status failed, falling back to raw publish: %s", e)
                                    try:
                                        self.redis_client.publish(channel, json.dumps(message))
                                    except Exception as e2:
                                        log.error("[RealtimeManager] Redis publish fallback failed: %s", e2)
                            else:
                                # fallback: raw publish
                                self.redis_client.publish(channel, json.dumps(message))

                            redis_publish_count += 1
                            if redis_publish_count % 10000 == 0:
                                log.debug("[RealtimeManager] Published %d messages to Redis", redis_publish_count)
                        except Exception as e:
                            log.error("[RealtimeManager] Redis publish error: %s", e)

                elif ty == "orderbook":
                    raw_units = self._extract_orderbook_units_raw(message)
                    obu = self._normalize_obu_units(raw_units)

                    normalized = dict(message)
                    normalized["cd"] = cd
                    normalized["obu"] = obu
                    coin.orderbook = normalized

            except Exception as e:
                log.error("[RealtimeManager] Consume error: %s", e)
                time.sleep(0.1)

        log.info("[RealtimeManager] Message consumer stopped")

# ----------------------------
# Account
# ----------------------------
class Account(Thread):
    """
    계정 정보 동기화 (잔고, 수익률 등)
    """

    def __init__(self, access_key: str, secret_key: str) -> None:
        super().__init__(daemon=True)
        self.alive = False
        self.access_key = access_key
        self.secret_key = secret_key
        self.upbit = aiopyupbit.Upbit(self.access_key, self.secret_key) if aiopyupbit else None

        self.coins: dict = {}
        self.cash = 0.0
        self.locked_cash = 0.0
        self.total_purchase = 0
        self.total_evaluate = 0
        self.total_loss = 0
        self.total_yield = 0.0

    def run(self) -> None:
        log.info("[Account] Starting account sync thread")
        self.alive = True
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        loop.run_until_complete(self.__loop())

    def close(self) -> None:
        log.info("[Account] Stopping account sync thread")
        self.alive = False

    async def __loop(self) -> None:
        while self.alive:
            try:
                time.sleep(0.25)

                coins = {}
                cash = 0
                locked_cash = 0
                total_purchase = 0
                total_evaluate = 0

                if not self.upbit:
                    log.debug("[Account] aiopyupbit not available; skipping balance fetch")
                    await aio.sleep(1)
                    continue

                balances = await self.upbit.get_balances()
                for item in balances:
                    currency = item.get("currency")
                    avg_buy_price = float(item.get("avg_buy_price", 0))
                    balance = float(item.get("balance", 0))
                    locked = float(item.get("locked", 0))

                    if currency == "KRW":
                        cash = round(balance, 0)
                        locked_cash = round(locked, 0)
                        continue
                    if currency in ("XYM", "VTHO"):
                        continue

                    try:
                        if static and getattr(static, "chart", None):
                            coin = static.chart.get_coin(f"{static.FIAT}-{currency}")
                            trade_price = coin.get_trade_price()
                        else:
                            trade_price = 0
                    except Exception:
                        trade_price = 0

                    purchase = (balance + locked) * avg_buy_price
                    evaluate = (balance + locked) * trade_price
                    loss = evaluate - purchase

                    coins[currency] = {
                        "currency": currency,
                        "balance": balance,
                        "locked": locked,
                        "avg_buy_price": avg_buy_price,
                        "purchase": purchase,
                        "evaluate": evaluate,
                        "loss": loss,
                        "yield": (loss / purchase * 100) if purchase else 0,
                    }
                    total_purchase += purchase
                    total_evaluate += evaluate

                total_loss = total_evaluate - total_purchase
                total_yield = (total_loss / total_purchase * 100) if total_purchase else 0

                self.coins = coins
                self.cash = cash
                self.locked_cash = locked_cash
                self.total_purchase = total_purchase
                self.total_evaluate = total_evaluate
                self.total_loss = total_loss
                self.total_yield = total_yield

            except Exception as e:
                log.error("[Account] Sync error: %s", e)
                import traceback
                log.debug(traceback.format_exc())

# Module import-time summary for easier diagnostics (no "shim" wording)
try:
    log.debug("[component] Implementation module loaded -> %s", os.path.abspath(__file__))
except Exception:
    pass