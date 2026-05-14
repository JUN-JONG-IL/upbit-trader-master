# -*- coding: utf-8 -*-
"""
Upbit REST Collector - 전체 심볼(또는 지정된 심볼 목록)을 주기적으로 폴링해
최신 캔들(1m)을 Redis pub/sub 채널에 publish 합니다.

설치/운영:
- 이 모듈은 CollectorManager에서 UpbitWebSocket 구현이 없을 때 자동으로 사용됩니다.
- 환경 변수로 RATE_DELAY(초 단위 요청 딜레이), REDIS_URL 등을 조정 가능합니다.
"""
from __future__ import annotations

import threading
import time
import logging
import json
from typing import List, Optional, Dict, Any
import os

try:
    import requests
except Exception:
    requests = None  # 실행 시 requests 필요

try:
    import redis as _redis
except Exception:
    _redis = None

logger = logging.getLogger("UpbitRestCollector")
logger.addHandler(logging.NullHandler())


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[2] / "core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_urc", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


DEFAULT_REDIS_URL = _get_default_redis_url()
# 기본 요청 지연: 0.2초 => 약 5 req/sec (안전하게 조정하세요)
DEFAULT_DELAY = float(os.getenv("UPBIT_POLL_DELAY", "0.2"))


class UpbitRestCollector:
    """
    Upbit REST 기반 수집기(간단한 구현)
    - symbols: 리스트로 심볼들 (예: ["KRW-BTC", "KRW-ETH", ...])
    - redis_url: Redis connection URL (publish 용)
    - delay: 요청 간 지연 (초) — rate-limit 대응용
    """

    def __init__(self, redis_url: str = DEFAULT_REDIS_URL, delay: float = DEFAULT_DELAY) -> None:
        if requests is None:
            raise RuntimeError("requests 패키지 필요: pip install requests")
        if _redis is None:
            raise RuntimeError("redis 패키지 필요: pip install redis")
        self._redis_url = redis_url
        self._delay = float(delay)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._symbols: List[str] = []
        self._stop_event = threading.Event()
        self._rclient = None

    def _ensure_redis(self):
        if self._rclient is None:
            try:
                self._rclient = _redis.from_url(self._redis_url, decode_responses=True)
            except Exception as e:
                logger.exception("Redis 연결 실패: %s", e)
                self._rclient = None

    def start(self, symbols: List[str]) -> None:
        """수집 시작(블로킹하지 않음). symbols는 전체 심볼 리스트"""
        if self._running:
            logger.info("UpbitRestCollector 이미 실행 중")
            return
        if not symbols:
            logger.error("UpbitRestCollector: 심볼 목록이 비어 있음")
            return
        self._symbols = list(symbols)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="UpbitRestCollectorThread")
        self._running = True
        self._thread.start()
        logger.info("UpbitRestCollector 시작 (symbols=%d, delay=%.3fs)", len(self._symbols), self._delay)

    def stop(self) -> None:
        """수집 중지"""
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("UpbitRestCollector 중지됨")

    def _publish(self, payload: Dict[str, Any]) -> None:
        try:
            self._ensure_redis()
            if not self._rclient:
                return
            # 기존 앱이 구독하는 채널명 'ui.chart' 를 사용
            self._rclient.publish("ui.chart", json.dumps(payload, default=str, ensure_ascii=False))
        except Exception:
            logger.exception("Redis publish 실패")

    def _fetch_latest_candle(self, market: str) -> Optional[Dict[str, Any]]:
        """
        Upbit public /v1/candles/minutes/1 API를 사용해 최신 1분 캔들 하나를 가져옵니다.
        반환값은 pipeline이 기대하는 형태(딕셔너리)로 가공합니다.
        """
        try:
            url = "https://api.upbit.com/v1/candles/minutes/1"
            resp = requests.get(url, params={"market": market, "count": 1}, timeout=10)
            if resp.status_code != 200:
                logger.debug("Upbit API 실패(%s): %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            if not data:
                return None
            c = data[0]
            # Map to a generic candle dict used by UI/pipeline
            candle = {
                "symbol": market,
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
            return candle
        except Exception:
            logger.exception("Upbit API 호출 중 예외 (market=%s)", market)
            return None

    def _run_loop(self) -> None:
        """메인 루프(스레드 내부에서 실행)"""
        self._ensure_redis()
        idx = 0
        total = len(self._symbols)
        while not self._stop_event.is_set():
            try:
                market = self._symbols[idx % total]
                # fetch
                candle = self._fetch_latest_candle(market)
                if candle:
                    # publish to redis (ui.chart)
                    self._publish(candle)
                # advance index
                idx += 1
                # sleep short delay to respect rate-limit
                time.sleep(self._delay)
            except Exception:
                logger.exception("UpbitRestCollector 루프 예외 (무시)")
        logger.info("UpbitRestCollector 루프 종료")