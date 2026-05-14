"""
[Purpose]
- coinlist에서 사용하는 백그라운드 워커 모음.

[Key Rule]
- Worker는 UI(위젯)를 직접 만지지 않는다.
  (UI 접근은 메인스레드에서만)

Workers
- CoinListWorker: 5초 주기로 static.chart.coins 스냅샷 emit
- TradeWorker: 업비트 웹소켓 체결 수신 → (ticker, ask_bid, amount) signal emit
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

from PyQt5.QtCore import QThread, pyqtSignal

try:
    import static  # type: ignore[import]
except ImportError:
    try:
        from app import static  # type: ignore[import]
    except ImportError:
        static = None  # type: ignore[assignment]

try:
    import websocket  # websocket-client
    _HAS_WEBSOCKET = True
except ImportError:
    _HAS_WEBSOCKET = False
    websocket = None  # type: ignore[assignment]


def _get_chart_coins() -> list:
    """static.chart.coins에 안전하게 접근하여 coin 값 리스트를 반환."""
    try:
        chart = getattr(static, "chart", None)
        if chart is None:
            return []
        coins = getattr(chart, "coins", None)
        if not coins:
            return []
        return list(coins.values())
    except Exception:
        return []


def _get_chart_codes() -> list:
    """static.chart.codes에 안전하게 접근하여 코드 리스트를 반환."""
    try:
        chart = getattr(static, "chart", None)
        if chart is None:
            return []
        codes = getattr(chart, "codes", None)
        if not codes:
            return []
        return list(codes)
    except Exception:
        return []


class CoinListWorker(QThread):
    dataSent = pyqtSignal(list)

    def __init__(self, interval_sec: int = 5):
        super().__init__()
        self.alive = False
        self.interval_sec = interval_sec

    def run(self):
        self.alive = True
        while self.alive:
            time.sleep(self.interval_sec)
            coins = _get_chart_coins()
            self.dataSent.emit(coins)

    def close(self):
        self.alive = False
        self.quit()
        self.wait()


class TradeWorker(QThread):
    """
    Signals
    - status(str): 상태 메시지(연결/오류/종료)
    - tradeAccum(ticker:str, ask_bid:str['BID'|'ASK'], amount:Decimal)
    """
    status = pyqtSignal(str)
    tradeAccum = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self.alive = True
        self.ws = None

    def run(self):
        if not _HAS_WEBSOCKET:
            self.status.emit("웹소켓 라이브러리 없음 (websocket-client 미설치)")
            return
        backoff = 5
        while self.alive:
            try:
                self.ws = websocket.WebSocketApp(
                    "wss://api.upbit.com/websocket/v1",
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    on_open=self.on_open,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                self.status.emit(f"웹소켓 오류: {e}")
                if "429" in str(e):
                    time.sleep(60)
                    backoff = min(backoff * 2, 300)
                else:
                    time.sleep(backoff)

    def on_open(self, ws):
        try:
            self.status.emit("웹소켓 연결중")
            codes = _get_chart_codes()
            subscribe = [{"ticket": "trade"}, {"type": "trade", "codes": codes}]
            ws.send(json.dumps(subscribe))
            self.status.emit("웹소켓 연결 완료")
        except Exception as e:
            self.status.emit(f"웹소켓 subscribe 오류: {e}")

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get("type") != "trade":
                return
            ticker = data["code"].split("-")[1]
            ask_bid = data.get("ask_bid")
            if ask_bid not in ("BID", "ASK"):
                return
            amount = Decimal(str(data["trade_price"])) * Decimal(str(data["trade_volume"]))
            self.tradeAccum.emit(ticker, ask_bid, amount)
        except Exception as e:
            self.status.emit(f"웹소켓 파싱 오류: {e}")

    def on_error(self, ws, error):
        self.status.emit(f"웹소켓 오류: {error}")

    def on_close(self, ws, close_status_code=None, close_msg=None):
        self.status.emit("웹소켓 연결 종료됨")

    def close(self):
        self.alive = False
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.quit()
        self.wait()
