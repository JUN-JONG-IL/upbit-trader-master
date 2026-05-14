#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit API ?곗씠???쒓났??

pyupbit ?먮뒗 aiopyupbit瑜??듯빐 ?ㅼ젣 Upbit 嫄곕옒???곗씠?곕? 議고쉶?⑸땲??
?쇱씠釉뚮윭由ш? ?녿뒗 寃쎌슦 鍮?媛믪쓣 諛섑솚?⑸땲??

CHANGELOG:
- 2026-03-19 | Copilot | src/06_ai/priority/services/ ??src/data_01/clients/ ?쇰줈 ?대룞
              Upbit ?곗씠??怨듦툒?먮뒗 ?곗씠???덉씠??data_01)???랁븯誘濡?clients/ ?섏쐞濡??щ같移?
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
    logger.warning("pyupbit 誘몄꽕移???UpbitDataProvider??鍮?媛믪쓣 諛섑솚?⑸땲??")


class UpbitDataProvider:
    """Upbit API ?곗씠???쒓났??

    pyupbit???숆린 ?⑥닔瑜?asyncio.to_thread()瑜??듯빐 鍮꾨룞湲곕줈 ?섑븨?⑸땲??
    pyupbit媛 ?ㅼ튂?섏? ?딆? ?섍꼍?먯꽌??紐⑤뱺 硫붿꽌?쒓? 鍮?媛믪쓣 諛섑솚?⑸땲??
    """

    # ------------------------------------------------------------------
    # ?꾩옱媛
    # ------------------------------------------------------------------

    async def get_ticker_data(self, symbol: str) -> Dict:
        """?꾩옱媛 ?뺣낫 議고쉶

        Args:
            symbol: ?щ낵 (?? "BTC")

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
            logger.error("?꾩옱媛 議고쉶 ?ㅽ뙣 (%s): %s", symbol, exc)
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
        """OHLCV ?곗씠??議고쉶

        Args:
            symbol: ?щ낵 (?? "BTC")
            interval: ?쒓컙 ?⑥쐞 ("day", "minute60", "minute30", "minute5", "minute1", ...)
            count: 議고쉶??罹붾뱾 ??

        Returns:
            OHLCV ?뺤뀛?덈━ 紐⑸줉 (媛??뺤뀛?덈━??open, high, low, close, volume ?ы븿)
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
            logger.error("OHLCV 議고쉶 ?ㅽ뙣 (%s): %s", symbol, exc)
            return []

    # ------------------------------------------------------------------
    # ?멸?
    # ------------------------------------------------------------------

    async def get_orderbook(self, symbol: str) -> Dict:
        """?멸? ?뺣낫 議고쉶

        Args:
            symbol: ?щ낵 (?? "BTC")

        Returns:
            ?멸? ?뺤뀛?덈━ (orderbook_units, total_ask_size, total_bid_size ??
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
            logger.error("?멸? 議고쉶 ?ㅽ뙣 (%s): %s", symbol, exc)
            return {}

    # ------------------------------------------------------------------
    # ?곗빱 紐⑸줉
    # ------------------------------------------------------------------

    async def get_all_tickers(self) -> List[str]:
        """紐⑤뱺 KRW 留덉폆 ?곗빱 議고쉶

        Returns:
            ?щ낵 紐⑸줉 (?? ["BTC", "ETH", ...])
        """
        if not _PYUPBIT_AVAILABLE:
            return []
        try:
            tickers = await asyncio.to_thread(pyupbit.get_tickers, fiat="KRW")
            if not tickers:
                return []
            return [t.replace("KRW-", "") for t in tickers]
        except Exception as exc:
            logger.error("?곗빱 紐⑸줉 議고쉶 ?ㅽ뙣: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 24?쒓컙 嫄곕옒??
    # ------------------------------------------------------------------

    async def get_volume_24h(self, symbol: str) -> float:
        """24?쒓컙 嫄곕옒??議고쉶

        Args:
            symbol: ?щ낵 (?? "BTC")

        Returns:
            嫄곕옒??(float). 議고쉶 ?ㅽ뙣 ??0.0
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
            logger.error("24?쒓컙 嫄곕옒??議고쉶 ?ㅽ뙣 (%s): %s", symbol, exc)
            return 0.0

    # ------------------------------------------------------------------
    # ?쒓?珥앹븸
    # ------------------------------------------------------------------

    async def get_market_cap(self, symbol: str) -> float:
        """?쒓?珥앹븸 異붿젙移?怨꾩궛 (?꾩옱媛 湲곕컲)

        Note:
            ?뺥솗???좏넻???곗씠?곕뒗 CoinGecko ???몃? API ?곕룞???꾩슂?⑸땲??
            ?꾩옱???꾩옱媛瑜?湲곕컲?쇰줈 ??異붿젙移섎? 諛섑솚?⑸땲??

        Args:
            symbol: ?щ낵 (?? "BTC")

        Returns:
            ?쒓?珥앹븸 異붿젙移?(float). 議고쉶 ?ㅽ뙣 ??0.0
        """
        if not _PYUPBIT_AVAILABLE:
            return 0.0
        try:
            ticker_data = await self.get_ticker_data(symbol)
            price = ticker_data.get("price", 0.0)
            if not price:
                return 0.0
            # ?ㅼ젣 ?좏넻?됱씠 ?놁쑝誘濡??꾩떆 異붿젙移??ъ슜
            return float(price) * 1_000_000
        except Exception as exc:
            logger.error("?쒓?珥앹븸 怨꾩궛 ?ㅽ뙣 (%s): %s", symbol, exc)
            return 0.0

    # ------------------------------------------------------------------
    # 媛寃?蹂?붿쑉
    # ------------------------------------------------------------------

    async def get_price_change_rate(self, symbol: str) -> Optional[float]:
        """?꾩씪 ?鍮?媛寃?蹂?붿쑉 怨꾩궛

        Args:
            symbol: ?щ낵 (?? "BTC")

        Returns:
            蹂?붿쑉(%) ?먮뒗 None
        """
        ohlcv = await self.get_ohlcv(symbol, interval="day", count=2)
        if len(ohlcv) < 2:
            return None
        prev_close = ohlcv[-2].get("close", 0)
        curr_close = ohlcv[-1].get("close", 0)
        if prev_close == 0:
            return None
        return ((curr_close - prev_close) / prev_close) * 100

