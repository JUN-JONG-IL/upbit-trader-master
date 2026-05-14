#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit API 데이터 제공자

pyupbit 또는 aiopyupbit를 통해 실제 Upbit 거래소 데이터를 조회합니다.
라이브러리가 없는 경우 빈 값을 반환합니다.

CHANGELOG:
- 2026-03-19 | Copilot | src/06_ai/priority/services/ → src/02_data/clients/ 으로 이동
              Upbit 데이터 공급자는 데이터 레이어(02_data)에 속하므로 clients/ 하위로 재배치
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import pyupbit  # type: ignore

    _PYUPBIT_AVAILABLE = True
except ImportError:
    _PYUPBIT_AVAILABLE = False
    logger.warning("pyupbit 미설치 — UpbitDataProvider는 빈 값을 반환합니다.")


class UpbitDataProvider:
    """Upbit API 데이터 제공자

    pyupbit의 동기 함수를 asyncio.to_thread()를 통해 비동기로 래핑합니다.
    pyupbit가 설치되지 않은 환경에서는 모든 메서드가 빈 값을 반환합니다.
    """

    # ------------------------------------------------------------------
    # 현재가
    # ------------------------------------------------------------------

    async def get_ticker_data(self, symbol: str) -> Dict:
        """현재가 정보 조회

        Args:
            symbol: 심볼 (예: "BTC")

        Returns:
            {"price": float, "timestamp": datetime}
        """
        if not _PYUPBIT_AVAILABLE:
            return {}
        try:
            price = await asyncio.to_thread(
                pyupbit.get_current_price, f"KRW-{symbol}"
            )
            if price is None:
                return {}
            return {"price": float(price), "timestamp": datetime.now()}
        except Exception as exc:
            logger.error("현재가 조회 실패 (%s): %s", symbol, exc)
            return {}

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "day",
        count: int = 200,
    ) -> List[Dict]:
        """OHLCV 데이터 조회

        Args:
            symbol: 심볼 (예: "BTC")
            interval: 시간 단위 ("day", "minute60", "minute30", "minute5", "minute1", ...)
            count: 조회할 캔들 수

        Returns:
            OHLCV 딕셔너리 목록 (각 딕셔너리에 open, high, low, close, volume 포함)
        """
        if not _PYUPBIT_AVAILABLE:
            return []
        try:
            df = await asyncio.to_thread(
                pyupbit.get_ohlcv, f"KRW-{symbol}", interval=interval, count=count
            )
            if df is None or df.empty:
                return []
            return df.reset_index().rename(columns={"index": "date"}).to_dict("records")
        except Exception as exc:
            logger.error("OHLCV 조회 실패 (%s): %s", symbol, exc)
            return []

    # ------------------------------------------------------------------
    # 호가
    # ------------------------------------------------------------------

    async def get_orderbook(self, symbol: str) -> Dict:
        """호가 정보 조회

        Args:
            symbol: 심볼 (예: "BTC")

        Returns:
            호가 딕셔너리 (orderbook_units, total_ask_size, total_bid_size 등)
        """
        if not _PYUPBIT_AVAILABLE:
            return {}
        try:
            orderbook = await asyncio.to_thread(
                pyupbit.get_orderbook, f"KRW-{symbol}"
            )
            if not orderbook:
                return {}
            return orderbook[0] if isinstance(orderbook, list) else orderbook
        except Exception as exc:
            logger.error("호가 조회 실패 (%s): %s", symbol, exc)
            return {}

    # ------------------------------------------------------------------
    # 티커 목록
    # ------------------------------------------------------------------

    async def get_all_tickers(self) -> List[str]:
        """모든 KRW 마켓 티커 조회

        Returns:
            심볼 목록 (예: ["BTC", "ETH", ...])
        """
        if not _PYUPBIT_AVAILABLE:
            return []
        try:
            tickers = await asyncio.to_thread(pyupbit.get_tickers, fiat="KRW")
            if not tickers:
                return []
            return [t.replace("KRW-", "") for t in tickers]
        except Exception as exc:
            logger.error("티커 목록 조회 실패: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 24시간 거래량
    # ------------------------------------------------------------------

    async def get_volume_24h(self, symbol: str) -> float:
        """24시간 거래량 조회

        Args:
            symbol: 심볼 (예: "BTC")

        Returns:
            거래량 (float). 조회 실패 시 0.0
        """
        if not _PYUPBIT_AVAILABLE:
            return 0.0
        try:
            df = await asyncio.to_thread(
                pyupbit.get_ohlcv, f"KRW-{symbol}", interval="day", count=1
            )
            if df is None or df.empty:
                return 0.0
            return float(df["volume"].iloc[-1])
        except Exception as exc:
            logger.error("24시간 거래량 조회 실패 (%s): %s", symbol, exc)
            return 0.0

    # ------------------------------------------------------------------
    # 시가총액
    # ------------------------------------------------------------------

    async def get_market_cap(self, symbol: str) -> float:
        """시가총액 추정치 계산 (현재가 기반)

        Note:
            정확한 유통량 데이터는 CoinGecko 등 외부 API 연동이 필요합니다.
            현재는 현재가를 기반으로 한 추정치를 반환합니다.

        Args:
            symbol: 심볼 (예: "BTC")

        Returns:
            시가총액 추정치 (float). 조회 실패 시 0.0
        """
        if not _PYUPBIT_AVAILABLE:
            return 0.0
        try:
            ticker_data = await self.get_ticker_data(symbol)
            price = ticker_data.get("price", 0.0)
            if not price:
                return 0.0
            # 실제 유통량이 없으므로 임시 추정치 사용
            return float(price) * 1_000_000
        except Exception as exc:
            logger.error("시가총액 계산 실패 (%s): %s", symbol, exc)
            return 0.0

    # ------------------------------------------------------------------
    # 가격 변화율
    # ------------------------------------------------------------------

    async def get_price_change_rate(self, symbol: str) -> Optional[float]:
        """전일 대비 가격 변화율 계산

        Args:
            symbol: 심볼 (예: "BTC")

        Returns:
            변화율(%) 또는 None
        """
        ohlcv = await self.get_ohlcv(symbol, interval="day", count=2)
        if len(ohlcv) < 2:
            return None
        prev_close = ohlcv[-2].get("close", 0)
        curr_close = ohlcv[-1].get("close", 0)
        if prev_close == 0:
            return None
        return ((curr_close - prev_close) / prev_close) * 100
