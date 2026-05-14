#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
?먮룞 諛깊븘 愿由ш린 (Gap 泥섎━ ?꾨떞)

Gap 寃異???REST API 諛깊븘 ??candles ?뚯씠釉??????gap_fill_queue ?곹깭 媛깆떊
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("auto_backfill_manager")

# ??????????????????????????????????????????????????????????????????????
# Upbit ?쒓컙? ?곸닔 ??pyupbit get_ohlcv 媛 `to` ?몄옄瑜?naive 臾몄옄?대줈
# 蹂?섑븯硫댁꽌 TZ ?뺣낫瑜??쇨퀬 蹂대궡誘濡? ?쒕쾭????긽 KST 濡??댁꽍?쒕떎.
# UTC datetime ??KST naive 臾몄옄??蹂?????ъ슜.
# ??????????????????????????????????????????????????????????????????????
_KST = timezone(timedelta(hours=9))

__all__ = ["AutoBackfillManager"]


class AutoBackfillManager:
    """Gap 1嫄댁쓣 泥섎━?섎뒗 諛깊븘 愿由ъ옄."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.log = logger or logging.getLogger("auto_backfill_manager")
        # 遺꾨쪟 移댁슫?????ъ씠??泥섎━ 以?遺꾧린蹂?寃곌낵 吏묎퀎??(UI 硫붿떆吏 紐낇솗??.
        # ?몄텧?먭? ?ъ씠???쒖옉 ??reset_classification() ?쇰줈 珥덇린?뷀븳??
        self.classification: Dict[str, int] = {
            "rate_limit_requeued": 0,  # ?덉씠?몃━諛?異붿젙 ??pending ?좎?(?ъ떆???湲?
            "empty_no_data": 0,        # ?곗씠???놁쓬 (?쇱떆 ?μ븷 異붿젙) ??failed (retry 媛??
            "no_listing": 0,           # 30??珥덇낵 媛?+ 鍮?DF ???곸옣 ??遺꾨쪟 (do_not_retry)
            "exception": 0,            # 泥섎━ 以??덉쇅 諛쒖깮 ??failed
            "success": 0,              # ?뺤긽 ?????resolved
        }

    def reset_classification(self) -> None:
        """?ㅼ쓬 ?ъ씠???쒖옉 ??移댁슫?곕? 0?쇰줈 珥덇린??"""
        for k in self.classification:
            self.classification[k] = 0

    def classification_summary(self) -> str:
        """?ъ슜?먯뿉寃??몄텧????以??붿빟 硫붿떆吏 (?섏튂 0????ぉ ?앸왂)."""
        c = self.classification
        parts: List[str] = []
        if c.get("success", 0) > 0:
            parts.append(f"?깃났 {c['success']}嫄?)
        if c.get("rate_limit_requeued", 0) > 0:
            parts.append(f"?ъ떆???湲?{c['rate_limit_requeued']}嫄??덉씠?몃━諛?")
        if c.get("empty_no_data", 0) > 0:
            parts.append(f"?곗씠???놁쓬 {c['empty_no_data']}嫄?)
        if c.get("no_listing", 0) > 0:
            parts.append(f"?곸옣 ??{c['no_listing']}嫄?do_not_retry)")
        if c.get("exception", 0) > 0:
            parts.append(f"?덉쇅 {c['exception']}嫄?)
        return ", ".join(parts) if parts else "泥섎━ 寃곌낵 ?놁쓬"

    @staticmethod
    def _gap_age_days(start: Any) -> Optional[float]:
        """gap_start ?쒓컖???꾩옱(UTC)濡쒕???紐????꾩씤吏 怨꾩궛. ?ㅽ뙣 ??None."""
        try:
            dt = AutoBackfillManager._to_utc_datetime(start)
            if dt is None:
                return None
            now = datetime.now(timezone.utc)
            return (now - dt).total_seconds() / 86400.0
        except Exception:
            return None

    @staticmethod
    def _to_utc_datetime(value: Any) -> Optional[datetime]:
        """?낅젰 ?쒓컙??UTC aware datetime?쇰줈 ?뺢퇋?뷀빀?덈떎."""
        try:
            if value is None:
                return None
            if isinstance(value, datetime):
                dt = value
            elif isinstance(value, (int, float)):
                ts = float(value)
                if ts > 1e12:
                    ts = ts / 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(value, str):
                s = value.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                try:
                    dt = datetime.fromisoformat(s)
                except Exception:
                    dt = datetime.fromtimestamp(float(s), tz=timezone.utc)
            elif hasattr(value, "to_pydatetime"):
                dt = value.to_pydatetime()
            else:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            return None

    async def _process_one_gap(self, gap: Dict) -> bool:
        """
        Gap 1嫄?泥섎━ (諛깊븘 ??寃利???candles ???

        Args:
            gap: Gap ?뺣낫 (symbol, gap_start, gap_end, gap_seconds)

        Returns:
            bool: 泥섎━ ?깃났 ?щ?
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")

        try:
            self.log.info("[AutoBackfill] Gap 泥섎━ ?쒖옉: %s (%s ~ %s)", symbol, start, end)

            # 1?④퀎: Upbit REST API濡?罹붾뱾 議고쉶
            fetch_result = await self._fetch_candles(symbol=symbol, start=start, end=end, interval=timeframe)
            if isinstance(fetch_result, tuple):
                candles, last_error_kind = fetch_result
            else:  # ?명솚?? 怨쇨굅 ?뺥깭(list留?諛섑솚) ?鍮?
                candles, last_error_kind = fetch_result, None

            if not candles:
                # ?덉씠?몃━諛??ㅽ듃?뚰겕 異붿젙 ??'pending' ?좎? + retry_count 利앷? (?ы걧)
                if last_error_kind == "rate_limit":
                    self.log.warning(
                        "[AutoBackfill] %s/%s: ?덉씠?몃━諛?異붿젙 ???ъ떆???먮줈 ?좎?", symbol, timeframe,
                    )
                    await self._requeue_pending(gap, "rate_limit")
                    self.classification["rate_limit_requeued"] = (
                        self.classification.get("rate_limit_requeued", 0) + 1
                    )
                    return False
                # 鍮?寃곌낵 ??媛??곕졊???곕씪 遺꾨쪟:
                #  ??30??珥덇낵 媛?+ 鍮?DF: ?곸옣 ???먮뒗 ?곸옣 ?먯?) 媛?μ꽦 ?믪쓬
                #    ??do_not_retry=true 濡?留덊궧?섏뿬 ?ы걧??李⑤떒
                #  ??30???대궡 媛?+ 鍮?DF: ?쇱떆 ?μ븷 媛?μ꽦 ???쇰컲 failed (retry_count ?꾩쟻)
                gap_age_days = self._gap_age_days(start)
                if gap_age_days is not None and gap_age_days > 30:
                    self.log.warning(
                        "[AutoBackfill] %s/%s: 30??珥덇낵 媛?뿉???곗씠???놁쓬 ???곸옣 ?꾩쑝濡?遺꾨쪟(do_not_retry)",
                        symbol, timeframe,
                    )
                    await self._update_queue_status(
                        gap, "failed", "諛깊븘 ?곗씠???놁쓬 (30??珥덇낵 ???곸옣 ??異붿젙)", 0,
                        do_not_retry=True,
                    )
                    self.classification["no_listing"] = (
                        self.classification.get("no_listing", 0) + 1
                    )
                else:
                    self.log.warning("[AutoBackfill] %s: 諛깊븘 ?곗씠???놁쓬", symbol)
                    await self._update_queue_status(gap, "failed", "諛깊븘 ?곗씠???놁쓬", 0)
                    self.classification["empty_no_data"] = (
                        self.classification.get("empty_no_data", 0) + 1
                    )
                return False

            # 2?④퀎: candles ?뚯씠釉????
            success_count = await self._write_candles(candles)

            # 3?④퀎: gap_fill_queue ?곹깭 ?낅뜲?댄듃
            await self._update_queue_status(gap, "resolved", None, success_count)

            self.log.info(
                "[AutoBackfill] Gap 泥섎━ ?꾨즺: %s (%d媛?罹붾뱾 ???", symbol, success_count
            )
            self.classification["success"] = (
                self.classification.get("success", 0) + 1
            )
            return True

        except Exception as e:
            self.log.error(
                "[AutoBackfill] Gap 泥섎━ ?ㅽ뙣: %s - %s", symbol, e, exc_info=True
            )
            try:
                await self._update_queue_status(gap, "failed", str(e)[:500], 0)
            except Exception:
                pass
            self.classification["exception"] = (
                self.classification.get("exception", 0) + 1
            )
            return False

    async def _fetch_candles(
        self,
        symbol: str,
        start: Any,
        end: Any,
        interval: str = "1m",
        count: int = 200,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Upbit REST API?먯꽌 罹붾뱾 ?곗씠??議고쉶

        Returns:
            (candles, last_error_kind):
              - candles: 罹붾뱾 ?곗씠??紐⑸줉
              - last_error_kind: None | "rate_limit" | "network" ??鍮?寃곌낵???먯씤 遺꾨쪟
                (?몄텧遺?먯꽌 ?ы걧 vs failed 援щ텇???ъ슜)
        """
        # 湲濡쒕쾶 limiter / 諛깆삤???좏떥 ??怨듯넻 紐⑤뱢?먯꽌 濡쒕뱶 (?ㅽ뙣 ??臾댁떆)
        try:
            import importlib.util
            import pathlib
            import sys
            _arl_base = pathlib.Path(__file__).resolve().parents[2]
            _arl_path = _arl_base / "data_01" / "collectors" / "async_rate_limiter.py"
            _arl_mod = sys.modules.get("_async_rate_limiter")
            if _arl_mod is None and _arl_path.exists():
                _spec = importlib.util.spec_from_file_location("_async_rate_limiter", str(_arl_path))
                if _spec and _spec.loader:
                    _arl_mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_async_rate_limiter"] = _arl_mod
                    _spec.loader.exec_module(_arl_mod)
            get_limiter = getattr(_arl_mod, "get_global_upbit_rate_limiter", None) if _arl_mod else None
            is_rl_error = getattr(_arl_mod, "is_rate_limit_error", None) if _arl_mod else None
            backoff_seq = getattr(_arl_mod, "rate_limit_backoff_delays", None) if _arl_mod else None
        except Exception:
            get_limiter = is_rl_error = backoff_seq = None

        last_error_kind: Optional[str] = None

        try:
            try:
                import aiopyupbit  # type: ignore
            except Exception:
                self.log.warning("[AutoBackfill] aiopyupbit ?놁쓬 - 罹붾뱾 議고쉶 遺덇?")
                return [], "network"

            start_dt = self._to_utc_datetime(start)
            end_dt = self._to_utc_datetime(end)
            if start_dt is None or end_dt is None:
                self.log.warning("[AutoBackfill] 鍮꾩젙??gap ?쒓컙媛? start=%s end=%s", start, end)
                return [], None
            if start_dt > end_dt:
                start_dt, end_dt = end_dt, start_dt

            interval_to_upbit = {
                "1m": "minute1",
                "5m": "minute5",
                "15m": "minute15",
                "1h": "minute60",
                "4h": "minute240",
                "1d": "day",
            }
            upbit_interval = interval_to_upbit.get(str(interval), "minute1")
            max_count = max(1, min(int(count), 200))

            limiter = get_limiter() if callable(get_limiter) else None
            backoffs = tuple(backoff_seq()) if callable(backoff_seq) else (0.5, 1.0, 2.0, 4.0)

            candles: List[Dict[str, Any]] = []
            seen_times = set()
            cursor = end_dt + timedelta(seconds=1)
            # ??????????????????????????????????????????????????????????????
            # ?뵩 [洹쇰낯 ?먯씤 ?섏젙 ??5踰덉쓽 ?쒕룄媛 紐⑤몢 ?ㅽ뙣???댁쑀]
            # pyupbit `get_ohlcv` ??`to` ?몄옄瑜?諛쏆쑝硫??대??먯꽌
            #   pd.to_datetime(to).to_pydatetime() ??strftime("%Y-%m-%d %H:%M:%S")
            # 濡?**TZ ?뺣낫瑜??쇨퀬 naive 臾몄옄??*濡?Upbit ?쒕쾭???꾩넚?쒕떎.
            # Upbit ?쒕쾭??naive ?쒓컖??**KST 濡??댁꽍**?섎?濡? UTC `cursor` 瑜?
            # 洹몃?濡?蹂대궡硫??쒕쾭媛 +9 ?쒓컙 誘몃옒濡??몄떇?섏뿬 紐⑤뱺 ?щ낵?먯꽌
            # 鍮?DataFrame ??諛섑솚?쒕떎.
            # ???곕씪??cursor 瑜?KST 濡?蹂?섑븳 ??naive ?뺤떇?쇰줈 ?꾨떖?댁빞 ?쒕떎.
            # 紐⑤뱢 ?곸닔 `_KST` ?ъ슜 (?뚯씪 ?곷떒 ?뺤쓽).
            # 李몄“: pyupbit/quotation_api.py get_ohlcv() ??to 泥섎━ 濡쒖쭅
            # ??????????????????????????????????????????????????????????????
            # max_pages: SSOT(`backfill_scheduler.performance.max_pages_per_gap`)
            # ???섍꼍蹂????湲곕낯 100. UI ?ㅼ씠?쇰줈洹몄뿉??10~500 踰붿쐞 ??議곗젙 媛??
            try:
                from .performance_settings import get_max_pages_per_gap
                max_pages = int(get_max_pages_per_gap())
            except Exception:
                max_pages = 100
            max_pages = max(10, min(max_pages, 500))

            for _ in range(max_pages):
                # cursor(UTC) ??KST 蹂????naive 臾몄옄?대줈 ?꾨떖 (Upbit ?쒕쾭??KST ?댁꽍)
                cursor_kst = cursor.astimezone(_KST)
                to_str = cursor_kst.strftime("%Y-%m-%d %H:%M:%S")

                # 湲濡쒕쾶 ?덉씠?몃━諛?+ 吏??諛깆삤???ъ떆??
                df = None
                page_error_kind: Optional[str] = None
                for attempt in range(len(backoffs) + 1):
                    if limiter is not None:
                        await limiter.acquire()
                    try:
                        df = await aiopyupbit.get_ohlcv(
                            symbol,
                            interval=upbit_interval,
                            to=to_str,
                            count=max_count,
                        )
                        page_error_kind = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        if callable(is_rl_error) and is_rl_error(exc) and attempt < len(backoffs):
                            delay = backoffs[attempt]
                            self.log.info(
                                "[AutoBackfill] %s/%s ?덉씠?몃━諛?媛먯? ??%.1fs ???ъ떆??%d/%d)",
                                symbol, interval, delay, attempt + 1, len(backoffs),
                            )
                            await asyncio.sleep(delay)
                            page_error_kind = "rate_limit"
                            continue
                        self.log.debug(
                            "[AutoBackfill] %s/%s get_ohlcv ?덉쇅: %s", symbol, interval, exc
                        )
                        page_error_kind = "rate_limit" if (callable(is_rl_error) and is_rl_error(exc)) else "network"
                        df = None
                        break

                if df is None or getattr(df, "empty", True):
                    if page_error_kind is not None:
                        last_error_kind = page_error_kind
                    break

                earliest: Optional[datetime] = None
                for idx, row in df.iterrows():
                    candle_time = self._to_utc_datetime(idx)
                    if candle_time is None:
                        continue
                    if candle_time < start_dt or candle_time > end_dt:
                        continue
                    key = candle_time.isoformat()
                    if key in seen_times:
                        continue
                    seen_times.add(key)
                    candles.append(
                        {
                            "symbol": symbol,
                            "timeframe": str(interval),
                            "time": candle_time,
                            "open": float(row.get("open", 0.0)),
                            "high": float(row.get("high", 0.0)),
                            "low": float(row.get("low", 0.0)),
                            "close": float(row.get("close", 0.0)),
                            "volume": float(row.get("volume", 0.0)),
                            "quote_volume": float(row.get("value", 0.0)),
                            "trade_count": int(row.get("trade_count", 0) or 0),
                            "is_complete": True,
                            "exchange": "upbit",
                        }
                    )
                    if earliest is None or candle_time < earliest:
                        earliest = candle_time

                if earliest is None or earliest <= start_dt:
                    break
                cursor = earliest - timedelta(seconds=1)

            candles.sort(key=lambda x: x.get("time"))
            return candles, last_error_kind
        except Exception as e:
            self.log.error("[AutoBackfill] 罹붾뱾 議고쉶 ?ㅽ뙣: %s", e)
            kind = "rate_limit" if (callable(is_rl_error) and is_rl_error(e)) else "network"
            return [], kind

    async def _write_candles(self, candles: List[Dict[str, Any]]) -> int:
        """
        candles ?뚯씠釉붿뿉 吏곸젒 ???(CandleWriter ?ъ슜)

        Returns:
            int: ????깃났 嫄댁닔
        """
        if not candles:
            return 0
        try:
            import importlib.util
            import pathlib
            import sys

            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "data_01" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None
            if TimescaleConnector is None:
                self.log.warning("[AutoBackfill] TimescaleConnector ?놁쓬 - 罹붾뱾 ???遺덇?")
                return 0

            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                self.log.warning("[AutoBackfill] TimescaleDB ?곌껐 ?ㅽ뙣 - 罹붾뱾 ???遺덇?")
                return 0

            grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for candle in candles:
                sym = str(candle.get("symbol", ""))
                tf = str(candle.get("timeframe", "1m"))
                if not sym:
                    continue
                grouped.setdefault((sym, tf), []).append(candle)

            success_count = 0
            for (sym, tf), items in grouped.items():
                try:
                    inserted = conn.write_candles(sym, tf, items, exchange="upbit")
                    success_count += int(inserted or 0)
                except Exception as e:
                    self.log.debug("[AutoBackfill] write_candles ?ㅽ뙣 (%s/%s): %s", sym, tf, e)
            return success_count
        except Exception as e:
            self.log.error("[AutoBackfill] 罹붾뱾 ?곌린 ?ㅽ뙣: %s", e)
            return 0

    async def _update_queue_status(
        self,
        gap: Dict,
        status: str,
        error_message: Optional[str],
        filled_candles: int,
        do_not_retry: bool = False,
    ) -> None:
        """gap_fill_queue ?뚯씠釉??곹깭 ?낅뜲?댄듃.

        Args:
            do_not_retry: True 硫?do_not_retry=true 濡?留덊궧?섏뿬 GapFinder 媛
                ?숈씪 (symbol, timeframe, gap_start) 媛?쓣 ?ㅼ떆 ?먯뿉 ?ｌ? 紐삵븯寃??쒕떎.
                (?곸옣 ???먯? 異붿젙 ???ъ슜)
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")

        try:
            import importlib.util, pathlib, sys
            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "data_01" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None

            if TimescaleConnector is None:
                return

            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return

            if status == "resolved":
                sql = (
                    "UPDATE gap_fill_queue "
                    "SET status = 'resolved', resolved_at = NOW(), filled_candles = %s "
                    "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                )
                params = (filled_candles, symbol, timeframe, start, end)
            else:
                # do_not_retry=true ??寃쎌슦 而щ읆??議댁옱?섎㈃ ?④퍡 ?낅뜲?댄듃.
                # (援??ㅽ궎留덉뿉??而щ읆 遺?????덉쇅 ???대갚?쇰줈 而щ읆 ?놁씠 ?ъ떆??
                if do_not_retry:
                    sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s, do_not_retry = TRUE "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                else:
                    sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                params = (error_message, symbol, timeframe, start, end)

            try:
                with conn.conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.conn.commit()
            except Exception as ie:
                # do_not_retry 而щ읆???녿뒗 援??ㅽ궎留??대갚 (psycopg2 UndefinedColumn ?곗꽑 寃??
                # ?쇱씠釉뚮윭由?媛?⑹꽦 李⑥씠瑜?怨좊젮??臾몄옄??留ㅼ묶??蹂댁“ ?좏샇濡??ъ슜)
                _is_undefined_column = False
                try:
                    import psycopg2.errors as _pgerr  # type: ignore
                    if isinstance(ie, _pgerr.UndefinedColumn):  # type: ignore[attr-defined]
                        _is_undefined_column = True
                except Exception:
                    pass
                if not _is_undefined_column:
                    # ?대갚 ?좏샇: pgcode '42703' ?먮뒗 硫붿떆吏??而щ읆紐??ы븿
                    pgcode = getattr(ie, "pgcode", None)
                    if pgcode == "42703" or "do_not_retry" in str(ie):
                        _is_undefined_column = True
                if do_not_retry and _is_undefined_column:
                    try:
                        conn.conn.rollback()
                    except Exception:
                        pass
                    fb_sql = (
                        "UPDATE gap_fill_queue "
                        "SET status = 'failed', error_message = %s "
                        "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
                    )
                    with conn.conn.cursor() as cur:
                        cur.execute(fb_sql, params)
                    conn.conn.commit()
                    self.log.debug(
                        "[AutoBackfill] do_not_retry 而щ읆 誘몄〈?????쇰컲 failed ?대갚 (00_schema.sql 留덉씠洹몃젅?댁뀡 ?꾩슂)"
                    )
                else:
                    raise
        except Exception as e:
            self.log.debug("[AutoBackfill] ???곹깭 ?낅뜲?댄듃 ?ㅽ뙣: %s", e)

    async def _requeue_pending(self, gap: Dict, reason: str) -> None:
        """?덉씠?몃━諛??쇱떆 ?μ븷濡?鍮?寃곌낵媛 ?섏삩 gap ??'pending' ?쇰줈 ?좎??섍퀬
        ``retry_count`` 瑜?1 利앷??쒗궓?? ?ㅼ쓬 ?ㅼ?以꾨윭 ?ъ씠?댁뿉???ъ떆?꾨맂??

        Args:
            gap: gap ?뺣낫
            reason: ?ы걧 ?ъ쑀 (error_message ??湲곕줉)
        """
        symbol = gap.get("symbol", "")
        timeframe = gap.get("timeframe", "1m")
        start = gap.get("gap_start")
        end = gap.get("gap_end")
        try:
            import importlib.util
            import pathlib
            import sys
            _base = pathlib.Path(__file__).resolve().parents[2]
            _ts_db_path = _base / "data_01" / "timescale" / "timescale_db.py"
            _mod = sys.modules.get("_timescale_db")
            if _mod is None and _ts_db_path.exists():
                _spec = importlib.util.spec_from_file_location("_timescale_db", str(_ts_db_path))
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    sys.modules["_timescale_db"] = _mod
                    _spec.loader.exec_module(_mod)
            TimescaleConnector = getattr(_mod, "TimescaleConnector", None) if _mod else None
            if TimescaleConnector is None:
                return
            conn = TimescaleConnector()
            if not conn.connect() or not conn.conn or conn.conn.closed:
                return

            sql = (
                "UPDATE gap_fill_queue "
                "SET status = 'pending', "
                "    retry_count = COALESCE(retry_count, 0) + 1, "
                "    error_message = %s "
                "WHERE symbol = %s AND timeframe = %s AND gap_start = %s AND gap_end = %s"
            )
            params = (f"requeued: {reason}", symbol, timeframe, start, end)
            with conn.conn.cursor() as cur:
                cur.execute(sql, params)
            conn.conn.commit()
        except Exception as e:
            self.log.debug("[AutoBackfill] ???ы걧 ?ㅽ뙣: %s", e)

