# -*- coding: utf-8 -*-
"""
WebSocket Candle Manager for Upbit (ws_candle_manager.py)

ê¸°ëŠ¥ ?”ì•½:
- Upbit WebSocket (wss://api.upbit.com/websocket/v1) ???°ê²°/?¬ì ‘??
- subscribe(timeframe, codes) API: ?´ë??ì„œ codesë¥?ë°°ì¹˜?˜ì—¬ ?„ì†¡
- ë©”ì‹œì§€ ?„ì†¡ rate-limit ë³´í˜¸ (Upbit: websocket-message ì´ˆë‹¹ 5??ê¶Œìž¥)
- ?˜ì‹ ??ìº”ë“¤ ?Œì‹± ???œì? candle dictë¡?ìºì‹œ ë°??±ë¡??ì½œë°±?¼ë¡œ ?„ë‹¬
- get_latest(symbol, timeframe)?¼ë¡œ ìµœê·¼ ê°?ì¡°íšŒ ê°€??
- register_callback(callback)ë¡?pipeline ì½œë°± ?±ë¡ (ì½œë°±?€ sync ?ëŠ” async ê°€??

?¬ìš©ë²?(ê°„ë‹¨):
from src.data_01.collectors.ws_candle_manager import get_ws_manager
ws = get_ws_manager()
await ws.start()
ws.register_callback(my_pipeline_callback)
await ws.subscribe(['KRW-BTC','KRW-ETH'], '1m')
...
await ws.stop()

?˜ì¡´:
- Python websockets ?¼ì´ë¸ŒëŸ¬ë¦?(pip install websockets)
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

# ?ˆì „ ë§ˆì§„?????„ì†¡ ì§€??(ì´ˆë‹¹ ??4???„ì†¡ ê¶Œìž¥)
_DEFAULT_SEND_DELAY = 0.26

# ??êµ¬ë… ë©”ì‹œì§€???¬í•¨??ì½”ë“œ ??ë°°ì¹˜)
_DEFAULT_BATCH_SIZE = 30

# ?¬ì ‘??ë°±ì˜¤???Œë¼ë¯¸í„°
_BACKOFF_BASE = 1.0
_BACKOFF_FACTOR = 2.0
_MAX_BACKOFF = 60.0


def _gzip_decompress_if_needed(data: bytes) -> bytes:
    """Upbit?€ websocket?ì„œ gzipped binaryë¥?ë³´ë‚¼ ???ˆìŒ ???ˆì „?˜ê²Œ ë³µì›."""
    try:
        return gzip.decompress(data)
    except Exception:
        return data


def _parse_upbit_message(raw: Any) -> Optional[dict]:
    """?˜ì‹ ??raw frame??JSON dictë¡??Œì‹±(ë¬¸ìž?´ì´ê±°ë‚˜ gzip-compressed bytes ê°€??."""
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
        logger.debug("[WSManager] ë©”ì‹œì§€ ?Œì‹± ?¤íŒ¨, raw=%s", raw)
        return None


def _to_candle_from_upbit_msg(msg: dict) -> Optional[dict]:
    """
    Upbit websocket??candle ë©”ì‹œì§€(JSON)ë¥??œì? candle dictë¡?ë³€??
    ë°˜í™˜ ?¬ë§·: {
      "symbol","timeframe","time","open","high","low","close","volume","quote_volume","exchange","stream_raw"
    }
    ?œê°„?€ ê°€?¥í•œ ê²½ìš° ë¬¸ìž??ISO)ë¡?ë³´ì¡´?©ë‹ˆ?? ?¸ì¶œ?ì—???„ìš”?˜ë©´ datetime?¼ë¡œ ?Œì‹±?˜ì„¸??
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
        logger.debug("[WSManager] upbit ë©”ì‹œì§€->ìº”ë“¤ ï¿½ï¿½???¤íŒ¨: %s", exc)
        return None


class WebSocketCandleManager:
    """Upbit WebSocket ?°ê²° ë°?ìº”ë“¤ êµ¬ë… ë§¤ë‹ˆ?€"""

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
            logger.debug("[WSManager] auto_start=True ?”ì²­????start() ?¸ì¶œ ?„ìš” (await)")

    # -----------------------
    # Public API
    # -----------------------
    async def start(self) -> None:
        """ë¹„ë™ê¸°ì ?¼ë¡œ WS ë§¤ë‹ˆ?€ ?œìž‘"""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._recv_task = asyncio.create_task(self._run_connection_loop())
            self._send_task = asyncio.create_task(self._send_worker())
            logger.info("[WSManager] ?œìž‘??)

    async def stop(self) -> None:
        """ë§¤ë‹ˆ?€ ì¤‘ì?: ?œìŠ¤??ì·¨ì†Œ ë°??°ê²° ì¢…ë£Œ"""
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
            logger.info("[WSManager] ì¤‘ì???)

    def register_callback(self, cb: Callable[[dict], None]) -> None:
        """?˜ì‹ ??candle??ì²˜ë¦¬??ì½œë°± ?±ë¡ (?™ê¸° ?ëŠ” ì½”ë£¨??ì½œë°± ?ˆìš©)"""
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    async def subscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """timeframe???€??codesë¥?êµ¬ë…(?´ë????±ë¡?˜ê³  ?¤ì œ ?„ì†¡?€ send_workerê°€ ì²˜ë¦¬)"""
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

        # ë°°ì¹˜ë¡??˜ëˆ  ?„ì†¡ ?ì— ì¶”ê?
        batches = [list(added)[i : i + self.batch_size] for i in range(0, len(added), self.batch_size)]
        for batch in batches:
            msg = [
                {"ticket": "ticket_" + str(int(time.time() * 1000))},
                {"type": f"candle.{tf}", "codes": batch},
                {"format": "DEFAULT"},
            ]
            await self._send_queue.put(json.dumps(msg).encode("utf-8"))

    async def unsubscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """êµ¬ë… ?´ì œ(?´ë? ?íƒœë§??•ë¦¬). ?œë²„ ?™ê¸°?”ëŠ” ?¬ì—°ê²°ì‹œ ì²˜ë¦¬"""
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
        """ë©”ì¸ ?°ê²°/?˜ì‹  ë£¨í”„ ??recv() ?ˆì™¸ ê¸°ë°˜?¼ë¡œ ?ˆì •??""
        while self._running:
            try:
                logger.info("[WSManager] Upbit WS ?°ê²° ?œë„: %s", self.url)
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                    self._ws = ws
                    self._connected_evt.set()
                    logger.info("[WSManager] WS ?°ê²° ?±ê³µ")
                    # ?¬êµ¬???„ì†¡
                    await self._resubscribe_all()
                    # ë°±ì˜¤??ë¦¬ì…‹
                    self._backoff = _BACKOFF_BASE

                    # ?ˆì „???˜ì‹  ë£¨í”„: recv() ?ˆì™¸ë¡?ì¢…ë£Œ ê°ì?
                    while self._running:
                        try:
                            raw = await ws.recv()
                        except websockets.ConnectionClosed as cc:
                            logger.warning("[WSManager] WS ?°ê²° ì¢…ë£Œ: %s", cc)
                            break
                        except Exception as recv_exc:
                            # ?¼ì‹œ??recv ?¤ë¥˜??ë¡œê·¸ë§??¨ê¸°ê³??¬ì‹œ??
                            logger.debug("[WSManager] WS ?˜ì‹  ?¤ë¥˜(ë¬´ì‹œ): %s", recv_exc, exc_info=True)
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
                                        logger.debug("[WSManager] ì½œë°± ?¸ì¶œ ?¤íŒ¨: %s", cb_exc)
                    # ?°ê²° ì¢…ë£Œ ì²˜ë¦¬
                    self._connected_evt.clear()
                    self._ws = None
            except Exception as conn_exc:
                logger.warning("[WSManager] WS ?°ê²°/?˜ì‹  ?¤íŒ¨: %s", conn_exc, exc_info=True)

            if not self._running:
                break

            # ?¬ì ‘???€ê¸?(ì§€??ë°±ì˜¤??
            delay = min(self._backoff, _MAX_BACKOFF)
            logger.info("[WSManager] ?¬ì ‘???€ê¸? %.1fs", delay)
            await asyncio.sleep(delay)
            self._backoff = min(self._backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

    async def _resubscribe_all(self) -> None:
        """(?°ê²° ?? ?´ë? subscription ?íƒœë¥?ë°”íƒ•?¼ë¡œ ?œë²„???¤ì‹œ êµ¬ë… ?”ì²­ ?„ì†¡"""
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
        """?„ì†¡ ?ë? ?½ì–´ ?¤ì œë¡?WebSocket???„ì†¡ ??rate-limit ë³´í˜¸"""
        while self._running:
            try:
                data = await self._send_queue.get()
                # ?°ê²°???Œê¹Œì§€ ?€ê¸?
                await self._connected_evt.wait()
                if self._ws is None:
                    # push back and retry later
                    await asyncio.sleep(0.5)
                    await self._send_queue.put(data)
                    continue
                try:
                    await self._ws.send(data)
                except Exception as send_exc:
                    logger.debug("[WSManager] WS ?„ì†¡ ?¤íŒ¨(???¬ì‚½??: %s", send_exc)
                    try:
                        await self._send_queue.put(data)
                    except Exception:
                        pass
                await asyncio.sleep(self.send_delay)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[WSManager] send_worker ?¤ë¥˜: %s", exc, exc_info=True)
                await asyncio.sleep(0.5)


# -----------------------
# Singleton helper
# -----------------------
_WS_MANAGER_SINGLETON: Optional[WebSocketCandleManager] = None


def get_ws_manager(auto_start: bool = False) -> WebSocketCandleManager:
    """ëª¨ë“ˆ ?ˆë²¨ ?±ê???ë°˜í™˜"""
    global _WS_MANAGER_SINGLETON
    if _WS_MANAGER_SINGLETON is None:
        _WS_MANAGER_SINGLETON = WebSocketCandleManager(auto_start=auto_start)
    return _WS_MANAGER_SINGLETON
