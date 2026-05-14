"""
[Purpose]
- 데이터 fetch 전용 워커 - OHLCV 데이터를 백그라운드에서 일괄 취득

[Responsibilities]
- 여러 종목의 OHLCV 데이터를 병렬로 취득 (QThread)
- 레이트리밋 준수 (초당 최대 10 요청)
- 취득된 데이터를 시그널로 전달

[Main Flow]
- DataFetcher(symbols, interval, count).start()
- run() → fetch_all() → data_fetched 시그널 발생

[Dependencies]
- PyQt5.QtCore (QThread, pyqtSignal)
- aiopyupbit: Upbit OHLCV API
- asyncio: 비동기 실행

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import asyncio as aio
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    from utils.qt_stub import QtCore
    QThread = QtCore.QThread
    pyqtSignal = QtCore.pyqtSignal

try:
    import aiopyupbit
    HAS_AIOPYUPBIT = True
except ImportError:
    HAS_AIOPYUPBIT = False

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore


# 레이트리밋: 초당 최대 10 요청
_RATE_LIMIT_PER_SEC = 10
_MIN_INTERVAL = 1.0 / _RATE_LIMIT_PER_SEC  # 0.1초


class DataFetcher(QThread):
    """
    OHLCV 데이터 일괄 취득 워커.

    [Signals]
    - data_fetched(str, object): (symbol, DataFrame) 단일 종목 데이터 취득 완료
    - fetch_all_done(dict): {symbol: DataFrame} 전체 취득 완료
    - progress_updated(int, int): (current, total) 진행률
    - error_occurred(str): 오류 발생 메시지

    Examples:
        >>> fetcher = DataFetcher(['KRW-BTC', 'KRW-ETH'], 'minute5', 200)
        >>> fetcher.fetch_all_done.connect(on_done)
        >>> fetcher.start()
    """

    data_fetched = pyqtSignal(str, object)
    fetch_all_done = pyqtSignal(dict)
    progress_updated = pyqtSignal(int, int)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        symbols: List[str],
        interval: str = "minute1",
        count: int = 200,
        parent=None,
    ) -> None:
        """
        Args:
            symbols: 취득할 종목 코드 리스트
            interval: OHLCV 타임프레임 (예: 'minute1', 'minute5', 'day')
            count: 봉 수 (기본값: 200)
            parent: 부모 QObject
        """
        super().__init__(parent)
        self._symbols = symbols
        self._interval = interval
        self._count = count
        self._is_running = False
        self._results: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # QThread interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """QThread 실행 진입점."""
        self._is_running = True
        try:
            loop = aio.new_event_loop()
            aio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self._fetch_all_async())
            finally:
                loop.close()
            self.fetch_all_done.emit(results)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self._is_running = False

    def stop(self) -> None:
        """취득 중단 요청."""
        self._is_running = False
        self.quit()
        self.wait()

    # ------------------------------------------------------------------
    # Async fetch
    # ------------------------------------------------------------------

    async def _fetch_all_async(self) -> Dict[str, Any]:
        """
        모든 종목 OHLCV 비동기 취득.

        Returns:
            {symbol: DataFrame} 딕셔너리
        """
        results: Dict[str, Any] = {}
        total = len(self._symbols)

        for i, symbol in enumerate(self._symbols):
            if not self._is_running:
                break
            df = await self._fetch_one(symbol)
            if df is not None:
                results[symbol] = df
                self.data_fetched.emit(symbol, df)
            self.progress_updated.emit(i + 1, total)
            # 레이트리밋 준수
            await aio.sleep(_MIN_INTERVAL)

        return results

    async def _fetch_one(self, symbol: str) -> Optional[Any]:
        """
        단일 종목 OHLCV 취득.

        Args:
            symbol: 종목 코드

        Returns:
            OHLCV DataFrame 또는 None
        """
        if not HAS_AIOPYUPBIT:
            return None
        try:
            df = await aiopyupbit.get_ohlcv(
                symbol, interval=self._interval, count=self._count
            )
            return df
        except Exception:
            return None
