# -*- coding: utf-8 -*-
"""
TimescaleClient (비동기) - DSN 정규화 보강판

변경 요지:
- DSN 입력값을 여러 형태(libpq 키=값 문자열, dict, 또는 URI)로 허용하고 안전하게
  postgresql:// URI로 변환하여 asyncpg.create_pool에 전달합니다.
- 빈/잘못된 DSN일 경우 pool 생성을 시도하지 않고 명확한 에러를 던집니다.
- SyncTimescaleClient는 기존대로 동기 래퍼 역할을 유지합니다.

위치: src/02_data/timescale/timescale_client.py
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
    logger.debug("asyncpg 미설치 또는 로드 불가 - TimescaleClient 일부 기능 제한")

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
    libpq 스타일 "key=val key2='val2 with spaces'" 같은 문자열을 파싱(간단 구현).
    매우 복잡한 경우를 모두 커버하지는 않지만 common case 커버.
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
    반환: postgres URI 또는 None
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
    입력 dsn이 None 또는 빈 문자열이면 None 반환.
    1) 이미 URI(postgres://)이면 그대로 반환
    2) libpq 키=값 문자열이면 파싱하여 URI 생성
    3) 기타: None 반환
    """
    if not dsn:
        return None
    s = str(dsn).strip()
    if not s:
        return None
    if _is_uri_like(s):
        return s
    # 키=값 문자열 검사
    parsed = _parse_libpq_string(s)
    if parsed and ("host" in parsed or "hostname" in parsed) and ("db" in parsed or "dbname" in parsed):
        uri = _cfg_to_uri(parsed)
        return uri
    # 혹시 "key1=val1;key2=val2" 같은 구분자라면 ';'->' ' 치환해서 다시 시도
    if ";" in s:
        parsed = _parse_libpq_string(s.replace(";", " "))
        uri = _cfg_to_uri(parsed) if parsed else None
        if uri:
            return uri
    return None


class TimescaleClient:
    """
    비동기 Timescale 클라이언트
    - pool: 외부 asyncpg.Pool 제공 가능
    - dsn: 문자열(URI 또는 libpq) 또는 None
    """
    def __init__(self, pool: Optional[Any] = None, dsn: Optional[str] = None, min_size: int = 1, max_size: int = 5):
        self._external_pool_supplied = pool is not None
        self._pool = pool
        self._raw_dsn = dsn or os.environ.get("TIMESCALE_DSN", "") or None
        self._dsn = None  # normalized URI or None
        self._min_size = min_size
        self._max_size = max_size

        # 정규화 시도 즉시 수행 (so we can detect invalid early)
        try:
            self._dsn = _normalize_dsn(self._raw_dsn)
            if self._raw_dsn and not self._dsn:
                # raw provided but normalization failed — log warning
                logger.warning("TimescaleClient: 전달된 DSN을 정규화하지 못했습니다. raw=%r", self._raw_dsn)
        except Exception as e:
            logger.debug("TimescaleClient: DSN 정규화 중 예외: %s", e, exc_info=True)
            self._dsn = None

    async def _ensure_pool(self):
        """풀 확보: 외부 풀 우선, 내부 생성 시 DSN이 필요"""
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
                logger.debug("외부 get_pool 호출 실패: %s", e)

        if _asyncpg is None:
            raise RuntimeError("asyncpg 가 필요합니다. 설치 후 재시도하세요.")

        # DSN 필요 검사
        if not self._dsn:
            raise RuntimeError("유효한 DSN이 없습니다. TimescaleClient 생성 시 올바른 DSN을 전달하세요 (postgresql://... 또는 host=... dbname=...).")

        # create pool with normalized URI
        try:
            self._pool = await _asyncpg.create_pool(dsn=self._dsn, min_size=self._min_size, max_size=self._max_size)
            logger.info("TimescaleClient: asyncpg pool 생성 성공 (dsn_present=True)")
            return self._pool
        except Exception as e:
            logger.error("TimescaleClient: asyncpg pool 생성 실패: %s", e)
            raise

    async def close(self):
        """자체 생성 풀만 닫음"""
        if self._pool and not self._external_pool_supplied:
            try:
                await self._pool.close()
            except Exception:
                logger.debug("풀 종료 실패", exc_info=True)
        self._pool = None

    # ------------------------------------------------------------------
    # 비동기 데이터 조회
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
            # 효율성: 여러 심볼을 한 번에 처리하는 쿼리로 개선 가능; PoC는 심볼 순회
            for s in symbols:
                row = await conn.fetchrow("SELECT MAX(exchange_ts) as last_ts, COUNT(1) as cnt FROM market_ticks WHERE symbol = $1", s)
                last_ts = row["last_ts"] if row and "last_ts" in row else None
                cnt = int(row["cnt"]) if row and "cnt" in row else 0
                if isinstance(last_ts, datetime) and last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                out.append((s, last_ts, cnt))
        return out


# ----------------------------
# 동기 래퍼: 도구/스크립트에서 편히 사용
# ----------------------------
class SyncTimescaleClient:
    """
    동기 환경에서 비동기 TimescaleClient를 사용하는 간단 래퍼.
    내부적으로 asyncio.run 을 사용합니다.
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