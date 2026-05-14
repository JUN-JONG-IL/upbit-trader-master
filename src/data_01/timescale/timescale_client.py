# -*- coding: utf-8 -*-
"""
TimescaleClient (鍮꾨룞湲? - DSN ?뺢퇋??蹂닿컯??

蹂寃??붿?:
- DSN ?낅젰媛믪쓣 ?щ윭 ?뺥깭(libpq ??媛?臾몄옄?? dict, ?먮뒗 URI)濡??덉슜?섍퀬 ?덉쟾?섍쾶
  postgresql:// URI濡?蹂?섑븯??asyncpg.create_pool???꾨떖?⑸땲??
- 鍮??섎せ??DSN??寃쎌슦 pool ?앹꽦???쒕룄?섏? ?딄퀬 紐낇솗???먮윭瑜??섏쭛?덈떎.
- SyncTimescaleClient??湲곗〈?濡??숆린 ?섑띁 ??븷???좎??⑸땲??

?꾩튂: src/data_01/timescale/timescale_client.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List, Optional, Tuple, Any, Dict
from datetime import datetime, timezone
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# asyncpg lazy import
_asyncpg = None
try:
    import asyncpg  # type: ignore
    _asyncpg = asyncpg
except Exception:
    _asyncpg = None
    logger.debug("asyncpg 誘몄꽕移??먮뒗 濡쒕뱶 遺덇? - TimescaleClient ?쇰? 湲곕뒫 ?쒗븳")

# try to use existing pool helper if present
_get_external_pool = None
try:
    from .core.connection import get_pool as _external_get_pool  # type: ignore
    _get_external_pool = _external_get_pool
except Exception:
    _get_external_pool = None


def _is_uri_like(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    return bool(re.match(r"^(postgres|postgresql)://", s, re.IGNORECASE))


def _parse_libpq_string(libpq: str) -> Dict[str, str]:
    """
    libpq ?ㅽ???"key=val key2='val2 with spaces'" 媛숈? 臾몄옄?댁쓣 ?뚯떛(媛꾨떒 援ы쁽).
    留ㅼ슦 蹂듭옟??寃쎌슦瑜?紐⑤몢 而ㅻ쾭?섏????딆?留?common case 而ㅻ쾭.
    """
    out: Dict[str, str] = {}
    # split by spaces not inside quotes
    token_re = re.compile(r'''(\w+)=('.*?'|".*?"|\S+)''')
    for m in token_re.finditer(libpq):
        k = m.group(1)
        v = m.group(2)
        if v and ((v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"'))):
            v = v[1:-1]
        out[k] = v
    return out


def _cfg_to_uri(cfg: Dict[str, Any]) -> Optional[str]:
    """
    cfg: {'host':..., 'port':..., 'dbname':..., 'user':..., 'password':...}
    諛섑솚: postgres URI ?먮뒗 None
    """
    host = cfg.get("host") or cfg.get("hostname") or ""
    port = str(cfg.get("port") or cfg.get("port", "") or "")
    dbname = cfg.get("dbname") or cfg.get("db") or cfg.get("database") or ""
    user = cfg.get("user") or cfg.get("username") or ""
    password = cfg.get("password") or cfg.get("passwd") or cfg.get("pass") or ""

    if not host or not dbname:
        return None

    # quote user/password/dbname
    user_q = quote_plus(str(user)) if user else ""
    pwd_q = quote_plus(str(password)) if password else ""
    db_q = quote_plus(str(dbname))

    # construct authority
    auth = ""
    if user_q:
        auth = user_q
        if pwd_q:
            auth += f":{pwd_q}"
        auth += "@"

    # host:port
    hostpart = host
    if port:
        hostpart = f"{host}:{port}"

    uri = f"postgresql://{auth}{hostpart}/{db_q}"
    return uri


def _normalize_dsn(dsn: Optional[str]) -> Optional[str]:
    """
    ?낅젰 dsn??None ?먮뒗 鍮?臾몄옄?댁씠硫?None 諛섑솚.
    1) ?대? URI(postgres://)?대㈃ 洹몃?濡?諛섑솚
    2) libpq ??媛?臾몄옄?댁씠硫??뚯떛?섏뿬 URI ?앹꽦
    3) 湲고?: None 諛섑솚
    """
    if not dsn:
        return None
    s = str(dsn).strip()
    if not s:
        return None
    if _is_uri_like(s):
        return s
    # ??媛?臾몄옄??寃??
    parsed = _parse_libpq_string(s)
    if parsed and ("host" in parsed or "hostname" in parsed) and ("db" in parsed or "dbname" in parsed):
        uri = _cfg_to_uri(parsed)
        return uri
    # ?뱀떆 "key1=val1;key2=val2" 媛숈? 援щ텇?먮씪硫?';'->' ' 移섑솚?댁꽌 ?ㅼ떆 ?쒕룄
    if ";" in s:
        parsed = _parse_libpq_string(s.replace(";", " "))
        uri = _cfg_to_uri(parsed) if parsed else None
        if uri:
            return uri
    return None


class TimescaleClient:
    """
    鍮꾨룞湲?Timescale ?대씪?댁뼵??
    - pool: ?몃? asyncpg.Pool ?쒓났 媛??
    - dsn: 臾몄옄??URI ?먮뒗 libpq) ?먮뒗 None
    """
    def __init__(self, pool: Optional[Any] = None, dsn: Optional[str] = None, min_size: int = 1, max_size: int = 5):
        self._external_pool_supplied = pool is not None
        self._pool = pool
        self._raw_dsn = dsn or os.environ.get("TIMESCALE_DSN", "") or None
        self._dsn = None  # normalized URI or None
        self._min_size = min_size
        self._max_size = max_size

        # ?뺢퇋???쒕룄 利됱떆 ?섑뻾 (so we can detect invalid early)
        try:
            self._dsn = _normalize_dsn(self._raw_dsn)
            if self._raw_dsn and not self._dsn:
                # raw provided but normalization failed ??log warning
                logger.warning("TimescaleClient: ?꾨떖??DSN???뺢퇋?뷀븯吏 紐삵뻽?듬땲?? raw=%r", self._raw_dsn)
        except Exception as e:
            logger.debug("TimescaleClient: DSN ?뺢퇋??以??덉쇅: %s", e, exc_info=True)
            self._dsn = None

    async def _ensure_pool(self):
        """? ?뺣낫: ?몃? ? ?곗꽑, ?대? ?앹꽦 ??DSN???꾩슂"""
        if self._pool is not None:
            return self._pool

        # try external helper
        if _get_external_pool is not None:
            try:
                p = await _get_external_pool()
                if p:
                    self._pool = p
                    return self._pool
            except Exception as e:
                logger.debug("?몃? get_pool ?몄텧 ?ㅽ뙣: %s", e)

        if _asyncpg is None:
            raise RuntimeError("asyncpg 媛 ?꾩슂?⑸땲?? ?ㅼ튂 ???ъ떆?꾪븯?몄슂.")

        # DSN ?꾩슂 寃??
        if not self._dsn:
            raise RuntimeError("?좏슚??DSN???놁뒿?덈떎. TimescaleClient ?앹꽦 ???щ컮瑜?DSN???꾨떖?섏꽭??(postgresql://... ?먮뒗 host=... dbname=...).")

        # create pool with normalized URI
        try:
            self._pool = await _asyncpg.create_pool(dsn=self._dsn, min_size=self._min_size, max_size=self._max_size)
            logger.info("TimescaleClient: asyncpg pool ?앹꽦 ?깃났 (dsn_present=True)")
            return self._pool
        except Exception as e:
            logger.error("TimescaleClient: asyncpg pool ?앹꽦 ?ㅽ뙣: %s", e)
            raise

    async def close(self):
        """?먯껜 ?앹꽦 ?留??レ쓬"""
        if self._pool and not self._external_pool_supplied:
            try:
                await self._pool.close()
            except Exception:
                logger.debug("? 醫낅즺 ?ㅽ뙣", exc_info=True)
        self._pool = None

    # ------------------------------------------------------------------
    # 鍮꾨룞湲??곗씠??議고쉶
    # ------------------------------------------------------------------
    async def get_all_symbols(self, limit: Optional[int] = None) -> List[str]:
        pool = await self._ensure_pool()
        q = "SELECT DISTINCT symbol FROM market_ticks ORDER BY symbol"
        if limit:
            q = q + f" LIMIT {int(limit)}"
        async with pool.acquire() as conn:
            rows = await conn.fetch(q)
            return [r["symbol"] for r in rows if r and r["symbol"]]

    async def get_last_exchange_ts(self, symbol: str) -> Optional[datetime]:
        pool = await self._ensure_pool()
        q = "SELECT MAX(exchange_ts) AS last_ts FROM market_ticks WHERE symbol = $1"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(q, symbol)
            ts = row["last_ts"] if row and "last_ts" in row else None
            if ts is None:
                return None
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts
            return None

    async def get_symbols_last_stats(self, symbols: List[str]) -> List[Tuple[str, Optional[datetime], int]]:
        pool = await self._ensure_pool()
        out: List[Tuple[str, Optional[datetime], int]] = []
        async with pool.acquire() as conn:
            # ?⑥쑉?? ?щ윭 ?щ낵????踰덉뿉 泥섎━?섎뒗 荑쇰━濡?媛쒖꽑 媛?? PoC???щ낵 ?쒗쉶
            for s in symbols:
                row = await conn.fetchrow("SELECT MAX(exchange_ts) as last_ts, COUNT(1) as cnt FROM market_ticks WHERE symbol = $1", s)
                last_ts = row["last_ts"] if row and "last_ts" in row else None
                cnt = int(row["cnt"]) if row and "cnt" in row else 0
                if isinstance(last_ts, datetime) and last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                out.append((s, last_ts, cnt))
        return out


# ----------------------------
# ?숆린 ?섑띁: ?꾧뎄/?ㅽ겕由쏀듃?먯꽌 ?명엳 ?ъ슜
# ----------------------------
class SyncTimescaleClient:
    """
    ?숆린 ?섍꼍?먯꽌 鍮꾨룞湲?TimescaleClient瑜??ъ슜?섎뒗 媛꾨떒 ?섑띁.
    ?대??곸쑝濡?asyncio.run ???ъ슜?⑸땲??
    """
    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or os.environ.get("TIMESCALE_DSN", "") or None
        self._client: Optional[TimescaleClient] = None

    def _ensure_client(self):
        if self._client is None:
            self._client = TimescaleClient(pool=None, dsn=self._dsn)
        return self._client

    def get_all_symbols(self, limit: Optional[int] = None) -> List[str]:
        c = self._ensure_client()
        return asyncio.run(c.get_all_symbols(limit=limit))

    def get_last_exchange_ts(self, symbol: str) -> Optional[datetime]:
        c = self._ensure_client()
        return asyncio.run(c.get_last_exchange_ts(symbol))

    def get_symbols_last_stats(self, symbols: List[str]) -> List[Tuple[str, Optional[datetime], int]]:
        c = self._ensure_client()
        return asyncio.run(c.get_symbols_last_stats(symbols))
