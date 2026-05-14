#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit 怨쇨굅 4??移?OHLCV ?곗씠???쇨큵 ?ㅼ슫濡쒕뱶

湲곕뒫:
1. Upbit API濡?吏??湲곌컙(湲곕낯 4?? 1遺꾨큺 ?곗씠???ㅼ슫濡쒕뱶
2. TimescaleDB candles ?뚯씠釉붿뿉 吏곸젒 ?쎌엯 (ON CONFLICT DO NOTHING)
3. 以묐떒 吏??蹂듦뎄 (resume ?뚯씪)
4. 吏꾪뻾瑜??쒖떆 (tqdm ?놁씠??濡쒓렇濡?吏꾪뻾瑜?異쒕젰)

?곗씠??洹쒕え (李멸퀬):
- 1媛?醫낅ぉ: ??210留?媛?(4??移?1遺꾨큺)
- KRW 留덉폆 ?꾩껜(~248媛?: ??5??2泥쒕쭔 媛?
- ?뺤텞 ???붿뒪???ъ슜?? ??2GB (TimescaleDB ?뺤텞)

?ㅽ뻾 諛⑸쾿:
    python src/data_01/scripts/bulk_download_historical.py
    python src/data_01/scripts/bulk_download_historical.py --years 4 --symbols KRW-BTC KRW-ETH

?섍꼍蹂??(TimescaleDB ?묒냽):
    DATABASE_URL  ?먮뒗  PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
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

# ?꾨줈?앺듃 猷⑦듃瑜?PYTHONPATH??異붽?
_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
for p in (str(_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)

# aiopyupbit ?듭뀛??濡쒕뱶
try:
    import aiopyupbit  # type: ignore
    _AIOPYUPBIT_AVAILABLE = True
except ImportError:
    _AIOPYUPBIT_AVAILABLE = False

# tqdm ?듭뀛??濡쒕뱶
try:
    from tqdm import tqdm as _tqdm  # type: ignore
    _TQDM_AVAILABLE = True
except ImportError:
    _TQDM_AVAILABLE = False


def _make_progress_bar(total: int, desc: str, leave: bool = True):
    """tqdm???놁쑝硫?None??諛섑솚?섎뒗 ?⑺넗由?"""
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
    """Upbit 怨쇨굅 OHLCV ?곗씠???쇨큵 ?ㅼ슫濡쒕뱶"""

    # Upbit API 理쒕? ?붿껌 媛꾧꺽 (珥? - Rate Limit 以??
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
            years: ?ㅼ슫濡쒕뱶??湲곌컙 (??. 湲곕낯 4??
            batch_size: DB 諛곗튂 INSERT ?ш린. 湲곕낯 5000嫄?
            resume_file: ?꾨즺???щ낵 紐⑸줉????ν븷 ?뚯씪. 湲곕낯 ?꾨줈?앺듃 猷⑦듃??resume_bulk_download.txt.
            timeframe: ?ㅼ슫濡쒕뱶??罹붾뱾 ?⑥쐞. 湲곕낯 "1m" (1遺꾨큺).
        """
        self.years = years
        self.batch_size = batch_size
        self.timeframe = timeframe
        self.resume_file = resume_file or (_ROOT / "resume_bulk_download.txt")
        self._connector = None

    # ------------------------------------------------------------------
    # 怨듦컻 API
    # ------------------------------------------------------------------

    async def download_all_symbols(
        self, symbols: Optional[List[str]] = None
    ) -> int:
        """
        ?꾩껜(?먮뒗 吏?? ?щ낵?????怨쇨굅 ?곗씠?곕? ?ㅼ슫濡쒕뱶?⑸땲??

        Args:
            symbols: ?ㅼ슫濡쒕뱶???щ낵 紐⑸줉. None?대㈃ KRW ?꾩껜 留덉폆???ъ슜?⑸땲??

        Returns:
            ??λ맂 珥??덉퐫????
        """
        if not _AIOPYUPBIT_AVAILABLE:
            logger.error(
                "aiopyupbit ?⑦궎吏媛 ?ㅼ튂?섏? ?딆븯?듬땲?? "
                "'pip install aiopyupbit' ???ъ떆?꾪븯?몄슂."
            )
            return 0

        self._connector = self._build_connector()
        if self._connector is None:
            logger.error("TimescaleDB ?곌껐 ?ㅽ뙣 ???ㅼ슫濡쒕뱶瑜?以묐떒?⑸땲??")
            return 0

        if symbols is None:
            symbols = await self._get_all_symbols()
            logger.info("KRW 留덉폆 ?꾩껜 ?щ낵 %d媛?濡쒕뱶", len(symbols))

        completed = self._load_resume()
        remaining = [s for s in symbols if s not in completed]
        logger.info(
            "?대? ?꾨즺: %d媛?/ ?⑥? ?щ낵: %d媛?,
            len(completed),
            len(remaining),
        )

        total_downloaded = 0
        pbar = _make_progress_bar(len(remaining), "?꾩껜 吏꾪뻾瑜?)
        try:
            for idx, symbol in enumerate(remaining, start=1):
                try:
                    count = await self._download_symbol(symbol)
                    total_downloaded += count
                    self._save_resume(symbol)
                    _progress_update(pbar)
                    if idx % 10 == 0 or idx == len(remaining):
                        logger.info(
                            "吏꾪뻾瑜? %d/%d ?꾨즺 (留덉?留? %s, %d嫄? ?꾩쟻: %d嫄?",
                            idx, len(remaining), symbol, count, total_downloaded,
                        )
                except Exception:
                    logger.error("?щ낵 泥섎━ 以??덉쇅 諛쒖깮: %s", symbol, exc_info=True)
        finally:
            _progress_close(pbar)

        logger.info("?꾩껜 ?ㅼ슫濡쒕뱶 ?꾨즺: ?щ낵 %d媛? 珥?%d嫄?, len(remaining), total_downloaded)
        return total_downloaded

    # ------------------------------------------------------------------
    # ?대? 援ы쁽
    # ------------------------------------------------------------------

    async def _download_symbol(self, symbol: str) -> int:
        """?⑥씪 ?щ낵??吏??湲곌컙 怨쇨굅 ?곗씠?곕? ?ㅼ슫濡쒕뱶?섍퀬 DB????ν빀?덈떎."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=365 * self.years)

        # Upbit interval 肄붾뱶 蹂??
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

                    # 諛곗튂 ?ш린 珥덇낵 ?????
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
                    logger.warning("%s API ?몄텧 以??덉쇅 (?ъ떆???앸왂)", symbol, exc_info=True)
                    await asyncio.sleep(1.0)
                    break
        finally:
            _progress_close(pbar)

        # ?섎㉧吏 ???
        if all_candles:
            saved = self._save_batch(all_candles)
            total_saved += saved

        logger.debug("%s ?꾨즺: %d嫄????, symbol, total_saved)
        return total_saved

    def _save_batch(self, candles: List[Dict]) -> int:
        """罹붾뱾 諛곗튂瑜?candles ?뚯씠釉붿뿉 INSERT?⑸땲?? (ON CONFLICT DO NOTHING)"""
        if not candles or self._connector is None:
            return 0

        try:
            conn = self._connector.conn
            if conn is None or conn.closed:
                if not self._connector.connect():
                    logger.warning("_save_batch: DB ?ъ뿰寃??ㅽ뙣")
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
            logger.error("_save_batch: 諛곗튂 ????ㅽ뙣", exc_info=True)
            try:
                if self._connector and self._connector.conn:
                    self._connector.conn.rollback()
            except Exception:
                pass
            return 0

    def _build_connector(self):
        """TimescaleConnector ?몄뒪?댁뒪瑜?諛섑솚?⑸땲??"""
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
            logger.error("_build_connector: ?곌껐 ?ㅽ뙣", exc_info=True)
            return None

    async def _get_all_symbols(self) -> List[str]:
        """Upbit KRW 留덉폆 ?꾩껜 ?щ낵 紐⑸줉??諛섑솚?⑸땲??"""
        try:
            tickers = await aiopyupbit.get_tickers(fiat="KRW")
            if not tickers:
                return []
            return sorted(tickers)
        except Exception:
            logger.error("?щ낵 紐⑸줉 濡쒕뱶 ?ㅽ뙣", exc_info=True)
            return []

    def _load_resume(self) -> List[str]:
        """?꾨즺???щ낵 紐⑸줉???뚯씪?먯꽌 濡쒕뱶?⑸땲??"""
        if not self.resume_file.exists():
            return []
        try:
            lines = self.resume_file.read_text(encoding="utf-8").splitlines()
            return [line.strip() for line in lines if line.strip()]
        except Exception:
            return []

    def _save_resume(self, symbol: str) -> None:
        """?꾨즺???щ낵???뚯씪??湲곕줉?⑸땲??"""
        try:
            with open(self.resume_file, "a", encoding="utf-8") as f:
                f.write(f"{symbol}\n")
        except Exception:
            logger.debug("resume ?뚯씪 ????ㅽ뙣: %s", symbol)


# ---------------------------------------------------------------------------
# CLI 吏꾩엯??
# ---------------------------------------------------------------------------

async def _async_main(args) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _SEP = "=" * 70
    logger.info(_SEP)
    logger.info("Upbit 怨쇨굅 ?곗씠???쇨큵 ?ㅼ슫濡쒕뱶 ?쒖옉")
    logger.info("  湲곌컙: %d??/ ??꾪봽?덉엫: %s", args.years, args.timeframe)
    logger.info(_SEP)

    symbols: Optional[List[str]] = None
    if args.symbols:
        symbols = args.symbols
        logger.info("吏???щ낵: %s", ", ".join(symbols))

    downloader = BulkHistoricalDownloader(
        years=args.years,
        batch_size=args.batch_size,
        timeframe=args.timeframe,
    )
    total = await downloader.download_all_symbols(symbols=symbols)

    logger.info(_SEP)
    logger.info("?ㅼ슫濡쒕뱶 ?꾨즺: 珥?%d嫄????, total)
    logger.info(_SEP)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upbit 怨쇨굅 OHLCV ?곗씠???쇨큵 ?ㅼ슫濡쒕뱶"
    )
    parser.add_argument(
        "--years", type=int, default=4,
        help="?ㅼ슫濡쒕뱶??湲곌컙 (??. 湲곕낯媛? 4",
    )
    parser.add_argument(
        "--timeframe", default="1m",
        choices=["1m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w"],
        help="罹붾뱾 ?⑥쐞. 湲곕낯媛? 1m",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5000, dest="batch_size",
        help="DB 諛곗튂 INSERT ?ш린. 湲곕낯媛? 5000",
    )
    parser.add_argument(
        "--symbols", nargs="*",
        help="?ㅼ슫濡쒕뱶???щ낵 紐⑸줉 (怨듬갚 援щ텇). ?앸왂?섎㈃ KRW ?꾩껜 留덉폆.",
    )
    args = parser.parse_args()

    asyncio.run(_async_main(args))

