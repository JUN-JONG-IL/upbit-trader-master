# -*- coding: utf-8 -*-
"""
WebSocket Candle Manager for Upbit (ws_candle_manager.py)

湲곕뒫 ?붿빟:
- Upbit WebSocket (wss://api.upbit.com/websocket/v1) ???곌껐/?ъ젒??
- subscribe(timeframe, codes) API: ?대??먯꽌 codes瑜?諛곗튂?섏뿬 ?꾩넚
- 硫붿떆吏 ?꾩넚 rate-limit 蹂댄샇 (Upbit: websocket-message 珥덈떦 5??沅뚯옣)
- ?섏떊??罹붾뱾 ?뚯떛 ???쒖? candle dict濡?罹먯떆 諛??깅줉??肄쒕갚?쇰줈 ?꾨떖
- get_latest(symbol, timeframe)?쇰줈 理쒓렐 媛?議고쉶 媛??
- register_callback(callback)濡?pipeline 肄쒕갚 ?깅줉 (肄쒕갚? sync ?먮뒗 async 媛??

?ъ슜踰?(媛꾨떒):
from src.data_01.collectors.ws_candle_manager import get_ws_manager
ws = get_ws_manager()
await ws.start()
ws.register_callback(my_pipeline_callback)
await ws.subscribe(['KRW-BTC','KRW-ETH'], '1m')
...
await ws.stop()

?섏〈:
- Python websockets ?쇱씠釉뚮윭由?(pip install websockets)
"""
from __future__ import annotations

import asyncio
import json
import gzip
import logging
import time
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple, Any

import websockets

logger = logging.getLogger(__name__)

_UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"

# ?덉쟾 留덉쭊?????꾩넚 吏??(珥덈떦 ??4???꾩넚 沅뚯옣)
_DEFAULT_SEND_DELAY = 0.26

# ??援щ룆 硫붿떆吏???ы븿??肄붾뱶 ??諛곗튂)
_DEFAULT_BATCH_SIZE = 30

# ?ъ젒??諛깆삤???뚮씪誘명꽣
_BACKOFF_BASE = 1.0
_BACKOFF_FACTOR = 2.0
_MAX_BACKOFF = 60.0


def _gzip_decompress_if_needed(data: bytes) -> bytes:
    """Upbit? websocket?먯꽌 gzipped binary瑜?蹂대궪 ???덉쓬 ???덉쟾?섍쾶 蹂듭썝."""
    try:
        return gzip.decompress(data)
    except Exception:
        return data


def _parse_upbit_message(raw: Any) -> Optional[dict]:
    """?섏떊??raw frame??JSON dict濡??뚯떛(臾몄옄?댁씠嫄곕굹 gzip-compressed bytes 媛??."""
    try:
        if isinstance(raw, bytes):
            try:
                payload = _gzip_decompress_if_needed(raw)
                text = payload.decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="ignore")
        else:
            text = str(raw)
        obj = json.loads(text)
        return obj
    except Exception:
        logger.debug("[WSManager] 硫붿떆吏 ?뚯떛 ?ㅽ뙣, raw=%s", raw)
        return None


def _to_candle_from_upbit_msg(msg: dict) -> Optional[dict]:
    """
    Upbit websocket??candle 硫붿떆吏(JSON)瑜??쒖? candle dict濡?蹂??
    諛섑솚 ?щ㎎: {
      "symbol","timeframe","time","open","high","low","close","volume","quote_volume","exchange","stream_raw"
    }
    ?쒓컙? 媛?ν븳 寃쎌슦 臾몄옄??ISO)濡?蹂댁〈?⑸땲?? ?몄텧?먯뿉???꾩슂?섎㈃ datetime?쇰줈 ?뚯떛?섏꽭??
    """
    try:
        t = msg.get("type") or msg.get("ty")
        code = msg.get("code") or msg.get("cd") or msg.get("market") or msg.get("market_code")
        if not t or not code:
            return None

        tf = str(t).split(".")[-1]

        time_str = msg.get("candle_date_time_utc") or msg.get("candle_date_time_kst") or msg.get("cdttmu")
        candle_time = None
        if isinstance(time_str, str):
            candle_time = time_str

        open_p = msg.get("opening_price") or msg.get("op") or 0.0
        high_p = msg.get("high_price") or msg.get("hp") or 0.0
        low_p = msg.get("low_price") or msg.get("lp") or 0.0
        close_p = msg.get("trade_price") or msg.get("tp") or 0.0
        volume = msg.get("candle_acc_trade_volume") or msg.get("catv") or 0.0
        quote_volume = msg.get("candle_acc_trade_price") or msg.get("catp") or 0.0

        candle = {
            "symbol": str(code),
            "timeframe": str(tf),
            "time": candle_time,
            "open": float(open_p),
            "high": float(high_p),
            "low": float(low_p),
            "close": float(close_p),
            "volume": float(volume),
            "quote_volume": float(quote_volume),
            "exchange": "upbit",
            "stream_raw": msg,
        }
        return candle
    except Exception as exc:
        logger.debug("[WSManager] upbit 硫붿떆吏->罹붾뱾 占쏙옙???ㅽ뙣: %s", exc)
        return None


class WebSocketCandleManager:
    """Upbit WebSocket ?곌껐 諛?罹붾뱾 援щ룆 留ㅻ땲?"""

    def __init__(
        self,
        url: str = _UPBIT_WS_URL,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        send_delay: float = _DEFAULT_SEND_DELAY,
        auto_start: bool = False,
    ) -> None:
        self.url = url
        self.batch_size = int(batch_size)
        self.send_delay = float(send_delay)

        # websocket protocol instance
        self._ws: Optional[websockets.WebSocketClientProtocol] = None

        # background tasks
        self._recv_task: Optional[asyncio.Task] = None
        self._send_task: Optional[asyncio.Task] = None

        # send queue (bytes payload)
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._connected_evt = asyncio.Event()

        # subscriptions: timeframe -> set(symbols)
        self._subscriptions: Dict[str, Set[str]] = {}

        # latest cache: (symbol, timeframe) -> candle dict
        self._latest_cache: Dict[Tuple[str, str], dict] = {}

        # callbacks
        self._callbacks: List[Callable[[dict], None]] = []

        # control
        self._running = False
        self._lock = asyncio.Lock()

        # reconnect backoff
        self._backoff = _BACKOFF_BASE

        if auto_start:
            logger.debug("[WSManager] auto_start=True ?붿껌????start() ?몄텧 ?꾩슂 (await)")

    # -----------------------
    # Public API
    # -----------------------
    async def start(self) -> None:
        """鍮꾨룞湲곗쟻?쇰줈 WS 留ㅻ땲? ?쒖옉"""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._recv_task = asyncio.create_task(self._run_connection_loop())
            self._send_task = asyncio.create_task(self._send_worker())
            logger.info("[WSManager] ?쒖옉??)

    async def stop(self) -> None:
        """留ㅻ땲? 以묒?: ?쒖뒪??痍⑥냼 諛??곌껐 醫낅즺"""
        async with self._lock:
            self._running = False
            if self._recv_task:
                self._recv_task.cancel()
            if self._send_task:
                self._send_task.cancel()
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            self._connected_evt.clear()
            logger.info("[WSManager] 以묒???)

    def register_callback(self, cb: Callable[[dict], None]) -> None:
        """?섏떊??candle??泥섎━??肄쒕갚 ?깅줉 (?숆린 ?먮뒗 肄붾（??肄쒕갚 ?덉슜)"""
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    async def subscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """timeframe?????codes瑜?援щ룆(?대????깅줉?섍퀬 ?ㅼ젣 ?꾩넚? send_worker媛 泥섎━)"""
        codes_list = [c.strip().upper() for c in list(codes) if c and isinstance(c, str)]
        if not codes_list:
            return
        tf = str(timeframe)
        cur = self._subscriptions.get(tf, set())
        added = set(codes_list) - cur
        if not added:
            return
        cur |= set(added)
        self._subscriptions[tf] = cur

        # 諛곗튂濡??섎닠 ?꾩넚 ?먯뿉 異붽?
        batches = [list(added)[i : i + self.batch_size] for i in range(0, len(added), self.batch_size)]
        for batch in batches:
            msg = [
                {"ticket": "ticket_" + str(int(time.time() * 1000))},
                {"type": f"candle.{tf}", "codes": batch},
                {"format": "DEFAULT"},
            ]
            await self._send_queue.put(json.dumps(msg).encode("utf-8"))

    async def unsubscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """援щ룆 ?댁젣(?대? ?곹깭留??뺣━). ?쒕쾭 ?숆린?붾뒗 ?ъ뿰寃곗떆 泥섎━"""
        tf = str(timeframe)
        cur = self._subscriptions.get(tf, set())
        for c in list(codes):
            cur.discard(c.strip().upper())
        self._subscriptions[tf] = cur

    def is_subscribed(self, symbol: str, timeframe: str) -> bool:
        s = symbol.strip().upper()
        tf = str(timeframe)
        return s in self._subscriptions.get(tf, set())

    def get_latest(self, symbol: str, timeframe: str) -> Optional[dict]:
        key = (symbol.strip().upper(), str(timeframe))
        v = self._latest_cache.get(key)
        return dict(v) if isinstance(v, dict) else None

    # -----------------------
    # Internal: connection & send/receive workers
    # -----------------------
    async def _run_connection_loop(self) -> None:
        """硫붿씤 ?곌껐/?섏떊 猷⑦봽 ??recv() ?덉쇅 湲곕컲?쇰줈 ?덉젙??""
        while self._running:
            try:
                logger.info("[WSManager] Upbit WS ?곌껐 ?쒕룄: %s", self.url)
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                    self._ws = ws
                    self._connected_evt.set()
                    logger.info("[WSManager] WS ?곌껐 ?깃났")
                    # ?ш뎄???꾩넚
                    await self._resubscribe_all()
                    # 諛깆삤??由ъ뀑
                    self._backoff = _BACKOFF_BASE

                    # ?덉쟾???섏떊 猷⑦봽: recv() ?덉쇅濡?醫낅즺 媛먯?
                    while self._running:
                        try:
                            raw = await ws.recv()
                        except websockets.ConnectionClosed as cc:
                            logger.warning("[WSManager] WS ?곌껐 醫낅즺: %s", cc)
                            break
                        except Exception as recv_exc:
                            # ?쇱떆??recv ?ㅻ쪟??濡쒓렇留??④린怨??ъ떆??
                            logger.debug("[WSManager] WS ?섏떊 ?ㅻ쪟(臾댁떆): %s", recv_exc, exc_info=True)
                            await asyncio.sleep(0.5)
                            continue

                        if raw is None:
                            continue

                        obj = _parse_upbit_message(raw)
                        if obj is None:
                            continue

                        if isinstance(obj, dict) and str(obj.get("type", "")).startswith("candle"):
                            candle = _to_candle_from_upbit_msg(obj)
                            if candle:
                                sym = candle["symbol"].upper()
                                tf = candle["timeframe"]
                                self._latest_cache[(sym, tf)] = candle
                                for cb in list(self._callbacks):
                                    try:
                                        res = cb(candle)
                                        if asyncio.iscoroutine(res):
                                            asyncio.create_task(res)
                                    except Exception as cb_exc:
                                        logger.debug("[WSManager] 肄쒕갚 ?몄텧 ?ㅽ뙣: %s", cb_exc)
                    # ?곌껐 醫낅즺 泥섎━
                    self._connected_evt.clear()
                    self._ws = None
            except Exception as conn_exc:
                logger.warning("[WSManager] WS ?곌껐/?섏떊 ?ㅽ뙣: %s", conn_exc, exc_info=True)

            if not self._running:
                break

            # ?ъ젒???湲?(吏??諛깆삤??
            delay = min(self._backoff, _MAX_BACKOFF)
            logger.info("[WSManager] ?ъ젒???湲? %.1fs", delay)
            await asyncio.sleep(delay)
            self._backoff = min(self._backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

    async def _resubscribe_all(self) -> None:
        """(?곌껐 ?? ?대? subscription ?곹깭瑜?諛뷀깢?쇰줈 ?쒕쾭???ㅼ떆 援щ룆 ?붿껌 ?꾩넚"""
        if not self._subscriptions:
            return
        for tf, codes in self._subscriptions.items():
            if not codes:
                continue
            batches = [list(codes)[i : i + self.batch_size] for i in range(0, len(codes), self.batch_size)]
            for batch in batches:
                msg = [
                    {"ticket": "ticket_" + str(int(time.time() * 1000))},
                    {"type": f"candle.{tf}", "codes": batch},
                    {"format": "DEFAULT"},
                ]
                await self._send_queue.put(json.dumps(msg).encode("utf-8"))
                await asyncio.sleep(self.send_delay)

    async def _send_worker(self) -> None:
        """?꾩넚 ?먮? ?쎌뼱 ?ㅼ젣濡?WebSocket???꾩넚 ??rate-limit 蹂댄샇"""
        while self._running:
            try:
                data = await self._send_queue.get()
                # ?곌껐???뚭퉴吏 ?湲?
                await self._connected_evt.wait()
                if self._ws is None:
                    # push back and retry later
                    await asyncio.sleep(0.5)
                    await self._send_queue.put(data)
                    continue
                try:
                    await self._ws.send(data)
                except Exception as send_exc:
                    logger.debug("[WSManager] WS ?꾩넚 ?ㅽ뙣(???ъ궫??: %s", send_exc)
                    try:
                        await self._send_queue.put(data)
                    except Exception:
                        pass
                await asyncio.sleep(self.send_delay)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[WSManager] send_worker ?ㅻ쪟: %s", exc, exc_info=True)
                await asyncio.sleep(0.5)


# -----------------------
# Singleton helper
# -----------------------
_WS_MANAGER_SINGLETON: Optional[WebSocketCandleManager] = None


def get_ws_manager(auto_start: bool = False) -> WebSocketCandleManager:
    """紐⑤뱢 ?덈꺼 ?깃???諛섑솚"""
    global _WS_MANAGER_SINGLETON
    if _WS_MANAGER_SINGLETON is None:
        _WS_MANAGER_SINGLETON = WebSocketCandleManager(auto_start=auto_start)
    return _WS_MANAGER_SINGLETON
