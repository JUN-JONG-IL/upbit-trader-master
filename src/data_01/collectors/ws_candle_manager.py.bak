# -*- coding: utf-8 -*-
"""
WebSocket Candle Manager for Upbit (ws_candle_manager.py)

기능 요약:
- Upbit WebSocket (wss://api.upbit.com/websocket/v1) 에 연결/재접속
- subscribe(timeframe, codes) API: 내부에서 codes를 배치하여 전송
- 메시지 전송 rate-limit 보호 (Upbit: websocket-message 초당 5회 권장)
- 수신된 캔들 파싱 → 표준 candle dict로 캐시 및 등록된 콜백으로 전달
- get_latest(symbol, timeframe)으로 최근 값 조회 가능
- register_callback(callback)로 pipeline 콜백 등록 (콜백은 sync 또는 async 가능)

사용법 (간단):
from src.02_data.collectors.ws_candle_manager import get_ws_manager
ws = get_ws_manager()
await ws.start()
ws.register_callback(my_pipeline_callback)
await ws.subscribe(['KRW-BTC','KRW-ETH'], '1m')
...
await ws.stop()

의존:
- Python websockets 라이브러리 (pip install websockets)
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

# 안전 마진을 둔 전송 지연 (초당 약 4회 전송 권장)
_DEFAULT_SEND_DELAY = 0.26

# 한 구독 메시지에 포함할 코드 수(배치)
_DEFAULT_BATCH_SIZE = 30

# 재접속 백오프 파라미터
_BACKOFF_BASE = 1.0
_BACKOFF_FACTOR = 2.0
_MAX_BACKOFF = 60.0


def _gzip_decompress_if_needed(data: bytes) -> bytes:
    """Upbit은 websocket에서 gzipped binary를 보낼 수 있음 — 안전하게 복원."""
    try:
        return gzip.decompress(data)
    except Exception:
        return data


def _parse_upbit_message(raw: Any) -> Optional[dict]:
    """수신된 raw frame을 JSON dict로 파싱(문자열이거나 gzip-compressed bytes 가능)."""
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
        logger.debug("[WSManager] 메시지 파싱 실패, raw=%s", raw)
        return None


def _to_candle_from_upbit_msg(msg: dict) -> Optional[dict]:
    """
    Upbit websocket의 candle 메시지(JSON)를 표준 candle dict로 변환.
    반환 포맷: {
      "symbol","timeframe","time","open","high","low","close","volume","quote_volume","exchange","stream_raw"
    }
    시간은 가능한 경우 문자열(ISO)로 보존합니다. 호출자에서 필요하면 datetime으로 파싱하세요.
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
        logger.debug("[WSManager] upbit 메시지->캔들 ��싱 실패: %s", exc)
        return None


class WebSocketCandleManager:
    """Upbit WebSocket 연결 및 캔들 구독 매니저"""

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
            logger.debug("[WSManager] auto_start=True 요청됨 — start() 호출 필요 (await)")

    # -----------------------
    # Public API
    # -----------------------
    async def start(self) -> None:
        """비동기적으로 WS 매니저 시작"""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._recv_task = asyncio.create_task(self._run_connection_loop())
            self._send_task = asyncio.create_task(self._send_worker())
            logger.info("[WSManager] 시작됨")

    async def stop(self) -> None:
        """매니저 중지: 태스크 취소 및 연결 종료"""
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
            logger.info("[WSManager] 중지됨")

    def register_callback(self, cb: Callable[[dict], None]) -> None:
        """수신된 candle을 처리할 콜백 등록 (동기 또는 코루틴 콜백 허용)"""
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    async def subscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """timeframe에 대해 codes를 구독(내부에 등록하고 실제 전송은 send_worker가 처리)"""
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

        # 배치로 나눠 전송 큐에 추가
        batches = [list(added)[i : i + self.batch_size] for i in range(0, len(added), self.batch_size)]
        for batch in batches:
            msg = [
                {"ticket": "ticket_" + str(int(time.time() * 1000))},
                {"type": f"candle.{tf}", "codes": batch},
                {"format": "DEFAULT"},
            ]
            await self._send_queue.put(json.dumps(msg).encode("utf-8"))

    async def unsubscribe(self, codes: Iterable[str], timeframe: str) -> None:
        """구독 해제(내부 상태만 정리). 서버 동기화는 재연결시 처리"""
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
        """메인 연결/수신 루프 — recv() 예외 기반으로 안정화"""
        while self._running:
            try:
                logger.info("[WSManager] Upbit WS 연결 시도: %s", self.url)
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                    self._ws = ws
                    self._connected_evt.set()
                    logger.info("[WSManager] WS 연결 성공")
                    # 재구독 전송
                    await self._resubscribe_all()
                    # 백오프 리셋
                    self._backoff = _BACKOFF_BASE

                    # 안전한 수신 루프: recv() 예외로 종료 감지
                    while self._running:
                        try:
                            raw = await ws.recv()
                        except websockets.ConnectionClosed as cc:
                            logger.warning("[WSManager] WS 연결 종료: %s", cc)
                            break
                        except Exception as recv_exc:
                            # 일시적 recv 오류는 로그만 남기고 재시도
                            logger.debug("[WSManager] WS 수신 오류(무시): %s", recv_exc, exc_info=True)
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
                                        logger.debug("[WSManager] 콜백 호출 실패: %s", cb_exc)
                    # 연결 종료 처리
                    self._connected_evt.clear()
                    self._ws = None
            except Exception as conn_exc:
                logger.warning("[WSManager] WS 연결/수신 실패: %s", conn_exc, exc_info=True)

            if not self._running:
                break

            # 재접속 대기 (지수 백오프)
            delay = min(self._backoff, _MAX_BACKOFF)
            logger.info("[WSManager] 재접속 대기: %.1fs", delay)
            await asyncio.sleep(delay)
            self._backoff = min(self._backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

    async def _resubscribe_all(self) -> None:
        """(연결 후) 내부 subscription 상태를 바탕으로 서버에 다시 구독 요청 전송"""
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
        """전송 큐를 읽어 실제로 WebSocket에 전송 — rate-limit 보호"""
        while self._running:
            try:
                data = await self._send_queue.get()
                # 연결될 때까지 대기
                await self._connected_evt.wait()
                if self._ws is None:
                    # push back and retry later
                    await asyncio.sleep(0.5)
                    await self._send_queue.put(data)
                    continue
                try:
                    await self._ws.send(data)
                except Exception as send_exc:
                    logger.debug("[WSManager] WS 전송 실패(큐 재삽입): %s", send_exc)
                    try:
                        await self._send_queue.put(data)
                    except Exception:
                        pass
                await asyncio.sleep(self.send_delay)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[WSManager] send_worker 오류: %s", exc, exc_info=True)
                await asyncio.sleep(0.5)


# -----------------------
# Singleton helper
# -----------------------
_WS_MANAGER_SINGLETON: Optional[WebSocketCandleManager] = None


def get_ws_manager(auto_start: bool = False) -> WebSocketCandleManager:
    """모듈 레벨 싱글톤 반환"""
    global _WS_MANAGER_SINGLETON
    if _WS_MANAGER_SINGLETON is None:
        _WS_MANAGER_SINGLETON = WebSocketCandleManager(auto_start=auto_start)
    return _WS_MANAGER_SINGLETON