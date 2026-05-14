# -*- coding: utf-8 -*-
"""
query_helpers — QueryHelperMixin
캔들/심볼/타임프레임 조회 담당 믹스인.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("timescale_db")


class QueryHelperMixin:
    """캔들/심볼/타임프레임 조회 담당 믹스인."""

    def get_distinct_symbols(self) -> List[str]:
        """candles 테이블의 고유 심볼 목록 반환."""
        try:
            rows = self.run_query("SELECT DISTINCT symbol FROM public.candles ORDER BY symbol;")
            out: List[str] = []
            for r in rows or []:
                if isinstance(r, dict):
                    v = r.get("symbol")
                elif isinstance(r, (list, tuple)):
                    v = r[0] if r else None
                else:
                    v = r
                if v is not None:
                    out.append(str(v))
            return out
        except Exception:
            logger.exception("get_distinct_symbols 실패")
            return []

    def get_distinct_timeframes(self, symbol: str) -> List[str]:
        """특정 심볼의 고유 타임프레임 목록 반환."""
        try:
            rows = self.run_query(
                "SELECT DISTINCT timeframe FROM public.candles WHERE symbol = %s ORDER BY timeframe;",
                (symbol,),
            )
            out: List[str] = []
            for r in rows or []:
                if isinstance(r, dict):
                    v = r.get("timeframe")
                elif isinstance(r, (list, tuple)):
                    v = r[0] if r else None
                else:
                    v = r
                if v is not None:
                    out.append(str(v))
            return out
        except Exception:
            logger.exception("get_distinct_timeframes 실패")
            return []

    def select_recent(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
    ) -> List[Dict[str, Any]]:
        """최근 캔들 조회 (time DESC 정렬)."""
        sql = (
            "SELECT time, open, high, low, close, volume "
            "FROM public.candles "
            "WHERE symbol = %s AND timeframe = %s "
            "ORDER BY time DESC LIMIT %s;"
        )
        return self.run_query(sql, (symbol, timeframe, limit))

    def select_since(
        self,
        symbol: str,
        timeframe: str,
        since: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """특정 시각 이후 캔들 조회 (time ASC 정렬)."""
        sql = (
            "SELECT time, open, high, low, close, volume "
            "FROM public.candles "
            "WHERE symbol = %s AND timeframe = %s AND time > %s "
            "ORDER BY time ASC LIMIT %s;"
        )
        return self.run_query(sql, (symbol, timeframe, since, limit))

    def get_last_timestamp(self, symbol: str, timeframe: str) -> Optional[str]:
        """특정 심볼+타임프레임의 마지막 캔들 시각 반환."""
        try:
            rows = self.run_query(
                "SELECT time FROM public.candles WHERE symbol = %s AND timeframe = %s ORDER BY time DESC LIMIT 1;",
                (symbol, timeframe),
            )
            if rows and len(rows) > 0:
                r = rows[0]
                if isinstance(r, dict):
                    return str(r.get("time"))
                elif isinstance(r, (list, tuple)):
                    return str(r[0]) if r else None
            return None
        except Exception:
            logger.exception("get_last_timestamp 실패")
            return None
