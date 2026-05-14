# -*- coding: utf-8 -*-
"""
[Purpose]
- ScannerFrameWidget에서 분리된 백그라운드 스캔 워커 (QThread)

[Responsibilities]
- 종목별 OHLCV 데이터 조회 (aiopyupbit)
- 조건 검사 실행 (RSI, MA 골든크로스 등)
- 진행률 시그널 발생 (update_progress)
- 결과 시그널 발생 (update_table)
- 남은 시간 시그널 발생 (update_remaining)

[Main Flow]
- ScannerFrameWidget에서 ScannerWorker 인스턴스 생성 후 start() 호출
- run() → scan_loop() 실행 (asyncio 이벤트 루프)
- update_table 시그널로 결과 전달
- update_progress 시그널로 진행률(0-100) 전달

[Dependencies]
- PyQt5.QtCore (QThread, pyqtSignal)
- aiopyupbit: OHLCV 데이터 조회
- numpy: 지표 계산
- src.app.lib.static: 종목 목록

CHANGELOG:
- 2026-03-16 | Copilot | import 경로 수정 (server.static → src.app.lib.static)
"""
from __future__ import annotations

import asyncio as aio
import logging
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Tuple
from pathlib import Path

import numpy as np

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:
    from utils.qt_stub import QtCore
    QThread = QtCore.QThread
    pyqtSignal = QtCore.pyqtSignal

# static 모듈 import (src/server/app/static/static.py 기준)
try:
    import importlib as _il
    static = _il.import_module("src.server.app.static.static")
    HAS_STATIC = True
except (ImportError, ModuleNotFoundError, Exception):
    # Fallback: static 없이 실행
    static = None  # type: ignore[assignment]
    HAS_STATIC = False

try:
    import aiopyupbit
    HAS_AIOPYUPBIT = True
except ImportError:
    HAS_AIOPYUPBIT = False

try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False

logger = logging.getLogger(__name__)


class _RateLimitErrorTracker:
    """Rate Limit 에러를 집계하여 5분에 1회 요약 출력하는 트래커"""

    _REPORT_INTERVAL = 300  # 5분(초)

    def __init__(self) -> None:
        self.errors: Counter = Counter()
        self._last_report: float = time.monotonic()

    def record(self, symbol: str) -> None:
        self.errors[symbol] += 1
        now = time.monotonic()
        if now - self._last_report >= self._REPORT_INTERVAL:
            self._flush()

    def _flush(self) -> None:
        if self.errors:
            total = sum(self.errors.values())
            top_n = self.errors.most_common(5)
            logger.warning(
                "[ScannerWorker] Rate Limit 에러 요약 (최근 5분): 총 %d건, 영향받은 심볼 %d개 / 상위 %d개: %s",
                total, len(self.errors), len(top_n), top_n,
            )
            self.errors.clear()
        self._last_report = time.monotonic()


# 모듈 수준 Rate Limit 트래커 (워커 인스턴스 간 공유)
_rate_limit_tracker = _RateLimitErrorTracker()


class ScannerWorker(QThread):
    """
    백그라운드 스캔 워커.

    [Signals]
    - update_table(list): 스캔 결과 리스트 [(symbol, interval), ...]
    - update_progress(int): 진행률 0-100
    - update_remaining(str): 남은 시간 문자열 (예: "남은 시간: 01:30")
    """

    update_table = pyqtSignal(list)
    update_progress = pyqtSignal(int)
    update_remaining = pyqtSignal(str)

    def __init__(self, settings: Dict[str, Any], parent=None):
        """
        Args:
            settings: 사용자 스캔 설정 dict
            parent: 부모 QObject (선택)
        """
        super().__init__(parent)
        self.settings = settings
        self.alive = True

    def run(self) -> None:
        """QThread 실행 진입점 - 스캔 루프를 비동기로 실행한다."""
        self.alive = True
        # ✅ Windows에서 SelectorEventLoop 강제 사용 (aiodns 오류 방지)
        if sys.platform == "win32":
            aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        # ✅ 매 실행마다 새 이벤트 루프 생성 (재진입 방지)
        loop = aio.new_event_loop()
        aio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.scan_loop())
        except Exception as e:
            logger.exception("[ScannerWorker] 실행 에러: %s", e)
        finally:
            loop.close()

    async def scan_loop(self) -> None:
        """
        종목 스캔 루프.

        종목별 OHLCV 조회 후 RSI/MA 조건 검사를 수행하고
        결과를 update_table 시그널로 발행한다.
        """
        try:
            results: List[Tuple[str, str]] = []

            # 종목 목록 가져오기
            codes: List[str] = []
            
            # 1순위: static.chart.coins 사용
            if HAS_STATIC and hasattr(static, 'chart') and static.chart:
                try:
                    if hasattr(static.chart, 'coins'):
                        codes = [coin.code for coin in static.chart.coins.values()]
                    elif hasattr(static.chart, 'get_symbols'):
                        codes = static.chart.get_symbols()
                except Exception as e:
                    logger.warning("[ScannerWorker] static.chart 접근 실패: %s", e)

            # 2순위: aiopyupbit 직접 조회
            if not codes and HAS_AIOPYUPBIT:
                try:
                    tickers = await aiopyupbit.get_tickers(fiat="KRW")
                    codes = tickers if tickers else []
                except Exception as e:
                    logger.warning("[ScannerWorker] aiopyupbit.get_tickers 실패: %s", e)
                    codes = []

            if not codes:
                logger.warning("[ScannerWorker] 종목 목록이 비어있습니다.")
                self.update_table.emit([])
                return

            total = len(codes)

            for i, code in enumerate(codes):
                if not self.alive:
                    break

                interval = self.settings.get("interval", "minute1")
                try:
                    if HAS_AIOPYUPBIT:
                        df = await aiopyupbit.get_ohlcv(code, interval=interval, count=200)
                    else:
                        df = None
                except Exception as api_err:
                    err_msg = str(api_err)
                    # Rate Limit 에러는 트래커로 집계하여 5분에 1회 요약 출력
                    if "요청 수 제한" in err_msg or "too_many_requests" in err_msg or "429" in err_msg:
                        _rate_limit_tracker.record(code)
                    else:
                        logger.warning("[ScannerWorker] aiopyupbit 에러: %s (코드: %s, interval: %s)", api_err, code, interval)
                    self.update_progress.emit(int((i + 1) / total * 100))
                    continue

                if df is None or df.empty:
                    self.update_progress.emit(int((i + 1) / total * 100))
                    continue

                # DataFrame 변환 (polars 사용 가능 시)
                if HAS_POLARS:
                    try:
                        pdf = pl.from_pandas(df)
                    except Exception:
                        pdf = df  # pandas fallback
                else:
                    pdf = df  # pandas DataFrame fallback

                rsi_period = int(self.settings.get("rsi_period", 14))
                ma_short_period = int(self.settings.get("ma_short", 5))
                ma_long_period = int(self.settings.get("ma_long", 20))
                ma_direction = self.settings.get("ma_direction", "우상향")
                rsi_value = float(self.settings.get("rsi_value", 30))

                rsi = await self.calculate_rsi(pdf, rsi_period)
                ma_short = await self.calculate_ma(pdf, ma_short_period)
                ma_long = await self.calculate_ma(pdf, ma_long_period)

                # NOTE: 현재 구현은 "골든크로스 + RSI 임계" 최소 조건만 반영.
                if (
                    self.check_golden_cross(ma_short, ma_long, ma_direction)
                    and len(rsi) > 0
                    and not np.isnan(rsi[-1])
                    and rsi[-1] < rsi_value
                ):
                    results.append((code, interval))

                self.update_progress.emit(int((i + 1) / total * 100))
                await aio.sleep(0.1)  # rate limit 완화(보수적)

            self.update_table.emit(results)

        except Exception as e:
            logger.exception("[ScannerWorker] scan_loop 에러: %s", e)
            self.update_table.emit([])

    async def calculate_rsi(self, df: Any, period: int) -> np.ndarray:
        """RSI 계산."""
        try:
            if HAS_POLARS and hasattr(df, 'to_pandas'):
                closes = df["close"].to_numpy()
            elif hasattr(df, 'values'):
                closes = df["close"].values
            else:
                closes = np.array(df["close"])
        except Exception:
            return np.array([])

        if len(closes) < period + 1:
            return np.full(len(closes), np.nan)

        delta = np.diff(closes)
        up = np.maximum(delta, 0)
        down = np.maximum(-delta, 0)

        # 단순 평균 - 기존 구현 유지
        avg_up = np.convolve(up, np.ones(period) / period, mode="valid")[-1]
        avg_down = np.convolve(down, np.ones(period) / period, mode="valid")[-1]

        rs = avg_up / avg_down if avg_down != 0 else np.inf
        rsi_val = 100 - (100 / (1 + rs))

        # 마지막 값 사용을 위해 padding
        return np.concatenate((np.full(period, np.nan), np.array([rsi_val])))

    async def calculate_ma(self, df: Any, period: int) -> np.ndarray:
        """이동평균 계산."""
        try:
            if HAS_POLARS and hasattr(df, 'to_pandas'):
                closes = df["close"].to_numpy()
            elif hasattr(df, 'values'):
                closes = df["close"].values
            else:
                closes = np.array(df["close"])
        except Exception:
            return np.array([])

        if len(closes) < period:
            return np.full(len(closes), np.nan)
        return np.convolve(closes, np.ones(period) / period, mode="valid")

    def check_golden_cross(self, short: np.ndarray, long: np.ndarray, direction: str) -> bool:
        """골든크로스 조건 검사."""
        if short is None or long is None:
            return False
        if len(short) < 2 or len(long) < 2:
            return False

        if direction == "우상향":
            return bool(short[-1] > long[-1] and short[-2] < long[-2])

        return False

    def stop(self) -> None:
        """스캔 중단 요청."""
        self.alive = False
        self.quit()
        self.wait()

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """
        스캔 설정 업데이트.

        Args:
            settings: 새로운 설정 dict
        """
        self.settings = settings


# End of file