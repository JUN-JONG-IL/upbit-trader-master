#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit 과거 4년 치 OHLCV 데이터 일괄 다운로드

기능:
1. Upbit API로 지정 기간(기본 4년) 1분봉 데이터 다운로드
2. TimescaleDB candles 테이블에 직접 삽입 (ON CONFLICT DO NOTHING)
3. 중단 지점 복구 (resume 파일)
4. 진행률 표시 (tqdm 없이도 로그로 진행률 출력)

데이터 규모 (참고):
- 1개 종목: 약 210만 개 (4년 치 1분봉)
- KRW 마켓 전체(~248개): 약 5억 2천만 개
- 압축 후 디스크 사용량: 약 2GB (TimescaleDB 압축)

실행 방법:
    python src/data_01/scripts/bulk_download_historical.py
    python src/data_01/scripts/bulk_download_historical.py --years 4 --symbols KRW-BTC KRW-ETH

환경변수 (TimescaleDB 접속):
    DATABASE_URL  또는  PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

# 프로젝트 루트를 PYTHONPATH에 추가
_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
for p in (str(_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)

# aiopyupbit 옵셔널 로드
try:
    import aiopyupbit  # type: ignore
    _AIOPYUPBIT_AVAILABLE = True
except ImportError:
    _AIOPYUPBIT_AVAILABLE = False

# tqdm 옵셔널 로드
try:
    from tqdm import tqdm as _tqdm  # type: ignore
    _TQDM_AVAILABLE = True
except ImportError:
    _TQDM_AVAILABLE = False


def _make_progress_bar(total: int, desc: str, leave: bool = True):
    """tqdm이 없으면 None을 반환하는 팩토리."""
    if _TQDM_AVAILABLE:
        return _tqdm(total=total, desc=desc, leave=leave)
    return None


def _progress_update(pbar, n: int = 1) -> None:
    if pbar is not None:
        pbar.update(n)


def _progress_close(pbar) -> None:
    if pbar is not None:
        pbar.close()


class BulkHistoricalDownloader:
    """Upbit 과거 OHLCV 데이터 일괄 다운로드"""

    # Upbit API 최대 요청 간격 (초) - Rate Limit 준수
    _REQUEST_DELAY = 0.12

    def __init__(
        self,
        years: int = 4,
        batch_size: int = 5000,
        resume_file: Optional[Path] = None,
        timeframe: str = "1m",
    ):
        """
        Args:
            years: 다운로드할 기간 (년). 기본 4년.
            batch_size: DB 배치 INSERT 크기. 기본 5000건.
            resume_file: 완료된 심볼 목록을 저장할 파일. 기본 프로젝트 루트의 resume_bulk_download.txt.
            timeframe: 다운로드할 캔들 단위. 기본 "1m" (1분봉).
        """
        self.years = years
        self.batch_size = batch_size
        self.timeframe = timeframe
        self.resume_file = resume_file or (_ROOT / "resume_bulk_download.txt")
        self._connector = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def download_all_symbols(
        self, symbols: Optional[List[str]] = None
    ) -> int:
        """
        전체(또는 지정) 심볼에 대해 과거 데이터를 다운로드합니다.

        Args:
            symbols: 다운로드할 심볼 목록. None이면 KRW 전체 마켓을 사용합니다.

        Returns:
            저장된 총 레코드 수.
        """
        if not _AIOPYUPBIT_AVAILABLE:
            logger.error(
                "aiopyupbit 패키지가 설치되지 않았습니다. "
                "'pip install aiopyupbit' 후 재시도하세요."
            )
            return 0

        self._connector = self._build_connector()
        if self._connector is None:
            logger.error("TimescaleDB 연결 실패 — 다운로드를 중단합니다.")
            return 0

        if symbols is None:
            symbols = await self._get_all_symbols()
            logger.info("KRW 마켓 전체 심볼 %d개 로드", len(symbols))

        completed = self._load_resume()
        remaining = [s for s in symbols if s not in completed]
        logger.info(
            "이미 완료: %d개 / 남은 심볼: %d개",
            len(completed),
            len(remaining),
        )

        total_downloaded = 0
        pbar = _make_progress_bar(len(remaining), "전체 진행률")
        try:
            for idx, symbol in enumerate(remaining, start=1):
                try:
                    count = await self._download_symbol(symbol)
                    total_downloaded += count
                    self._save_resume(symbol)
                    _progress_update(pbar)
                    if idx % 10 == 0 or idx == len(remaining):
                        logger.info(
                            "진행률: %d/%d 완료 (마지막: %s, %d건, 누적: %d건)",
                            idx, len(remaining), symbol, count, total_downloaded,
                        )
                except Exception:
                    logger.error("심볼 처리 중 예외 발생: %s", symbol, exc_info=True)
        finally:
            _progress_close(pbar)

        logger.info("전체 다운로드 완료: 심볼 %d개, 총 %d건", len(remaining), total_downloaded)
        return total_downloaded

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    async def _download_symbol(self, symbol: str) -> int:
        """단일 심볼의 지정 기간 과거 데이터를 다운로드하고 DB에 저장합니다."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=365 * self.years)

        # Upbit interval 코드 변환
        interval_map = {
            "1m": "minute1", "3m": "minute3", "5m": "minute5",
            "10m": "minute10", "15m": "minute15", "30m": "minute30",
            "1h": "minute60", "4h": "minute240",
            "1d": "day", "1w": "week", "1M": "month",
        }
        interval = interval_map.get(self.timeframe, "minute1")

        all_candles: List[Dict] = []
        current_time = end_time
        total_saved = 0

        expected_calls = max(1, (365 * self.years * 24 * 60) // 200)
        pbar = _make_progress_bar(expected_calls, symbol, leave=False)
        try:
            while current_time > start_time:
                try:
                    df = await aiopyupbit.get_ohlcv(
                        ticker=symbol,
                        interval=interval,
                        to=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                        count=200,
                    )

                    if df is None or df.empty:
                        break

                    for ts, row in df.iterrows():
                        candle_time = ts.to_pydatetime()
                        if candle_time.tzinfo is None:
                            candle_time = candle_time.replace(tzinfo=timezone.utc)
                        all_candles.append({
                            "exchange": "upbit",
                            "symbol": symbol,
                            "symbol_full": symbol,
                            "timeframe": self.timeframe,
                            "time": candle_time,
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "volume": float(row["volume"]),
                            "trade_count": int(row.get("value", 0)) if "value" in row.index else 0,
                            "is_closed": True,
                        })

                    # 배치 크기 초과 시 저장
                    if len(all_candles) >= self.batch_size:
                        saved = self._save_batch(all_candles)
                        total_saved += saved
                        all_candles = []

                    oldest = df.index.min().to_pydatetime()
                    if oldest.tzinfo is None:
                        oldest = oldest.replace(tzinfo=timezone.utc)
                    current_time = oldest - timedelta(seconds=1)
                    _progress_update(pbar)

                    await asyncio.sleep(self._REQUEST_DELAY)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("%s API 호출 중 예외 (재시도 생략)", symbol, exc_info=True)
                    await asyncio.sleep(1.0)
                    break
        finally:
            _progress_close(pbar)

        # 나머지 저장
        if all_candles:
            saved = self._save_batch(all_candles)
            total_saved += saved

        logger.debug("%s 완료: %d건 저장", symbol, total_saved)
        return total_saved

    def _save_batch(self, candles: List[Dict]) -> int:
        """캔들 배치를 candles 테이블에 INSERT합니다. (ON CONFLICT DO NOTHING)"""
        if not candles or self._connector is None:
            return 0

        try:
            conn = self._connector.conn
            if conn is None or conn.closed:
                if not self._connector.connect():
                    logger.warning("_save_batch: DB 재연결 실패")
                    return 0
                conn = self._connector.conn

            import psycopg2.extras  # type: ignore

            rows = [
                (
                    c["exchange"], c["symbol"], c.get("symbol_full", c["symbol"]),
                    c["timeframe"], c["time"],
                    c["open"], c["high"], c["low"], c["close"],
                    c["volume"], c["trade_count"], c["is_closed"],
                    datetime.now(timezone.utc),
                )
                for c in candles
            ]

            insert_sql = """
                INSERT INTO candles
                    (exchange, symbol, symbol_full, timeframe, time,
                     open, high, low, close, volume, trade_count, is_closed, ts)
                VALUES %s
                ON CONFLICT (time, symbol, timeframe) DO NOTHING
            """

            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, insert_sql, rows, page_size=1000)
            conn.commit()
            return len(rows)

        except Exception:
            logger.error("_save_batch: 배치 저장 실패", exc_info=True)
            try:
                if self._connector and self._connector.conn:
                    self._connector.conn.rollback()
            except Exception:
                pass
            return 0

    def _build_connector(self):
        """TimescaleConnector 인스턴스를 반환합니다."""
        try:
            import importlib.util

            ts_db_path = _SRC / "data_01" / "timescale" / "timescale_db.py"
            spec = importlib.util.spec_from_file_location("_ts_db_bulk", str(ts_db_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            connector_cls = getattr(mod, "TimescaleConnector", None)
            if connector_cls is None:
                return None
            connector = connector_cls()
            if connector.connect():
                return connector
            return None
        except Exception:
            logger.error("_build_connector: 연결 실패", exc_info=True)
            return None

    async def _get_all_symbols(self) -> List[str]:
        """Upbit KRW 마켓 전체 심볼 목록을 반환합니다."""
        try:
            tickers = await aiopyupbit.get_tickers(fiat="KRW")
            if not tickers:
                return []
            return sorted(tickers)
        except Exception:
            logger.error("심볼 목록 로드 실패", exc_info=True)
            return []

    def _load_resume(self) -> List[str]:
        """완료된 심볼 목록을 파일에서 로드합니다."""
        if not self.resume_file.exists():
            return []
        try:
            lines = self.resume_file.read_text(encoding="utf-8").splitlines()
            return [line.strip() for line in lines if line.strip()]
        except Exception:
            return []

    def _save_resume(self, symbol: str) -> None:
        """완료된 심볼을 파일에 기록합니다."""
        try:
            with open(self.resume_file, "a", encoding="utf-8") as f:
                f.write(f"{symbol}\n")
        except Exception:
            logger.debug("resume 파일 저장 실패: %s", symbol)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

async def _async_main(args) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _SEP = "=" * 70
    logger.info(_SEP)
    logger.info("Upbit 과거 데이터 일괄 다운로드 시작")
    logger.info("  기간: %d년 / 타임프레임: %s", args.years, args.timeframe)
    logger.info(_SEP)

    symbols: Optional[List[str]] = None
    if args.symbols:
        symbols = args.symbols
        logger.info("지정 심볼: %s", ", ".join(symbols))

    downloader = BulkHistoricalDownloader(
        years=args.years,
        batch_size=args.batch_size,
        timeframe=args.timeframe,
    )
    total = await downloader.download_all_symbols(symbols=symbols)

    logger.info(_SEP)
    logger.info("다운로드 완료: 총 %d건 저장", total)
    logger.info(_SEP)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upbit 과거 OHLCV 데이터 일괄 다운로드"
    )
    parser.add_argument(
        "--years", type=int, default=4,
        help="다운로드할 기간 (년). 기본값: 4",
    )
    parser.add_argument(
        "--timeframe", default="1m",
        choices=["1m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w"],
        help="캔들 단위. 기본값: 1m",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5000, dest="batch_size",
        help="DB 배치 INSERT 크기. 기본값: 5000",
    )
    parser.add_argument(
        "--symbols", nargs="*",
        help="다운로드할 심볼 목록 (공백 구분). 생략하면 KRW 전체 마켓.",
    )
    args = parser.parse_args()

    asyncio.run(_async_main(args))
