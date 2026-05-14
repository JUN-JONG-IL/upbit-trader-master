#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sentinel_manager - 鍮꾨룞湲??곗꽑, ?숆린 ?대갚 諛⑹떇 (sync ?덉쇅 ?덉쟾 ?ㅽ뻾 蹂닿컯)

?ㅺ퀎 ?붿?:
- aioredis (鍮꾨룞湲?瑜??곗꽑 ?ъ슜?섎릺, SENTINEL 紐낅졊??吏?먰븯吏 ?딄굅???덉쇅媛 諛쒖깮?섎㈃
  aioredis 寃쎈줈瑜?鍮꾪솢?깊솕?섍퀬 ?덉쟾??sync ?대갚???쒕룄?⑸땲??
- sync ?대갚??execute_command???ㅻ젅???대??먯꽌 諛쒖깮?섎뒗 ?덉쇅瑜?罹≪쿂?섏뿬
  ?몄텧?먯뿉寃??먮윭 ?뺤뀛?덈━濡?諛섑솚?섎룄濡??섏뿬 ?꾨줈?몄뒪 ?ㅽ깮?몃젅?댁뒪瑜?諛⑹??⑸땲??
- 紐⑤뱺 釉붾줈???숈옉? run_in_executor濡??ㅽ뻾?⑸땲??
"""
from __future__ import annotations
import logging
import asyncio
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

logger = logging.getLogger("redis.sentinel_manager")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] [sentinel_manager] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# aioredis (鍮꾨룞湲? ?쒕룄
try:
    import redis.asyncio as aioredis  # type: ignore
except Exception:
    aioredis = None  # type: ignore
    logger.debug("redis.asyncio not available; will use sync fallback if possible")

# redis.exceptions.ResponseError 異붿텧 (?덉쓣 寃쎌슦)
try:
    import redis.exceptions as _rexc  # type: ignore
    RedisResponseError = getattr(_rexc, "ResponseError", Exception)
except Exception:
    RedisResponseError = Exception

# get_redis_client ?⑺넗由??숈쟻 濡쒕뱶(?곷? import ?ㅽ뙣 ?뚰뵾)
def _load_get_redis_client() -> Optional[Callable[..., Any]]:
    try:
        from .redis_client import get_redis_client  # type: ignore
        return get_redis_client
    except Exception:
        logger.debug("relative import of .redis_client failed; attempting file-based dynamic load")
    try:
        repo_root = Path(__file__).resolve().parents[3]
        candidate = repo_root / "src" / "data_01" / "redis" / "redis_client.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("redis_client_dynamic", str(candidate))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                return getattr(mod, "get_redis_client", None)
    except Exception:
        logger.debug("dynamic load of redis_client failed", exc_info=True)
    return None

_get_redis_client = _load_get_redis_client()

SentinelHost = Tuple[str, int]


async def _run_blocking(func, *args, **kwargs):
    """釉붾줈???⑥닔瑜?湲곕낯 ?ㅻ젅?쒗??먯꽌 ?ㅽ뻾"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _safe_sync_exec(sync_client: Any, *cmd_args) -> Any:
    """
    sync client.execute_command瑜??덉쟾?섍쾶 ?몄텧?섎뒗 ?ы띁.
    - ?ㅻ젅?쒖뿉???ㅽ뻾?섎ŉ ?대? ?덉쇅???≪븘??{'_error': str(e)} ?뺥깭濡?諛섑솚.
    - 諛섑솚媛믪씠 dict?닿퀬 '_error' ?ㅺ? ?덉쑝硫??ㅽ뙣瑜??섎?.
    """
    try:
        # some clients expose execute_command on client, others may not.
        exec_fn = getattr(sync_client, "execute_command", None)
        if exec_fn is None:
            # fallback: try to call client.sentinel or raw commands (best-effort)
            raise RuntimeError("sync client has no execute_command")
        return exec_fn(*cmd_args)
    except Exception as e:
        # ?ㅻ젅???대??먯꽌 ?덉쇅 ?섎윭?섍???寃껋쓣 留됯린 ?꾪빐 ?먮윭 ?뺣낫瑜?諛섑솚
        try:
            return {"_error": str(e)}
        except Exception:
            return {"_error": "unknown error in _safe_sync_exec"}


class SentinelManager:
    """
    Redis Sentinel 吏덉쓽 愿由ъ옄.
    - sentinel_hosts: [(host, port), ...]
    - master_name: Sentinel??紐⑤땲?곕쭅?섎뒗 master ?대쫫 (湲곕낯 'mymaster')
    - password: optional
    """

    def __init__(self, sentinel_hosts: List[SentinelHost], master_name: str = "mymaster", password: Optional[str] = None) -> None:
        self._sentinel_hosts = list(sentinel_hosts or [])
        self._master_name = master_name
        self._password = password
        self._sentinel: Optional[Any] = None      # aioredis.Sentinel ?몄뒪?댁뒪(?덉쓣 寃쎌슦)
        self._sync_client: Optional[Any] = None   # sync low-level client ?대갚
        self._aioredis_available = bool(aioredis)

    async def connect(self) -> None:
        """
        Sentinel ?곌껐 以鍮?
        - aioredis 媛?⑺븯硫?aioredis.Sentinel ?앹꽦 ?쒕룄.
        - ??긽 sync ?대갚 以鍮?議댁옱?섎㈃ raw client瑜?_sync_client?????.
        """
        # aioredis 寃쎈줈 ?쒕룄
        if aioredis and self._aioredis_available:
            try:
                self._sentinel = aioredis.Sentinel(self._sentinel_hosts, password=self._password)
                logger.info("SentinelManager: aioredis Sentinel 媛앹껜 ?앹꽦 ?쒕룄: %s", self._sentinel_hosts)
            except Exception as exc:
                logger.warning("SentinelManager: aioredis Sentinel ?앹꽦 ?ㅽ뙣: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        # sync ?대갚 以鍮?(get_redis_client ?⑺넗由??ъ슜)
        try:
            factory = _get_redis_client
            if factory:
                wrapper = factory(use_cached=True)
                raw = getattr(wrapper, "_client", None) or getattr(wrapper, "client", None) or wrapper
                self._sync_client = raw
                logger.info("SentinelManager: sync redis client fallback 以鍮?)
            else:
                logger.debug("SentinelManager: get_redis_client factory ?놁쓬 - sync fallback 遺덇?")
        except Exception as exc:
            logger.warning("SentinelManager: sync client fallback 以鍮??ㅽ뙣: %s", exc, exc_info=True)
            self._sync_client = None

    async def close(self) -> None:
        """?곌껐 ?뺣━: aioredis 媛앹껜???곸쐞?먯꽌 泥섎━媛?? sync ?대갚? close ?쒕룄"""
        try:
            self._sentinel = None
            if self._sync_client:
                try:
                    if hasattr(self._sync_client, "close"):
                        await _run_blocking(self._sync_client.close)
                except Exception:
                    pass
                self._sync_client = None
        except Exception:
            logger.exception("SentinelManager.close ?덉쇅")

    async def master_info(self) -> Dict[str, Any]:
        """
        紐⑤땲?곕쭅 以묒씤 master??INFO 諛섑솚.
        - aioredis ?곗꽑, ?ㅽ뙣 ???덉쟾??sync ?대갚 ?쒕룄
        """
        # aioredis 寃쎈줈
        if self._sentinel and aioredis:
            try:
                master = self._sentinel.master_for(self._master_name, password=self._password)
                info = await master.info()
                return dict(info or {})
            except RedisResponseError as exc:
                logger.warning("master_info (aioredis) ResponseError: %s", exc)
                self._sentinel = None
                self._aioredis_available = False
            except Exception as exc:
                logger.warning("master_info (aioredis) ?ㅽ뙣: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        # sync ?덉쟾 ?ㅽ뻾 ?대갚
        if self._sync_client:
            try:
                res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "MASTERS")
                if isinstance(res, dict) and res.get("_error"):
                    logger.warning("master_info (sync) ?ㅽ뙣: %s", res.get("_error"))
                else:
                    return {"masters_raw": res}
            except Exception as exc:
                logger.warning("master_info (sync) ?덉쇅: %s", exc, exc_info=True)

        logger.debug("master_info: sentinel ?곌껐 ?놁쓬")
        return {}

    async def slaves_info(self) -> List[Dict[str, Any]]:
        """
        ?щ젅?대툕 ?뺣낫 諛섑솚.
        - aioredis ?곗꽑, ?ㅽ뙣 ??sync ?덉쟾 ?대갚
        """
        if self._sentinel and aioredis:
            try:
                slave = self._sentinel.slave_for(self._master_name, password=self._password)
                info = await slave.info()
                return [dict(info or {})]
            except RedisResponseError as exc:
                logger.warning("slaves_info (aioredis) ResponseError: %s", exc)
                self._sentinel = None
                self._aioredis_available = False
            except Exception as exc:
                logger.warning("slaves_info (aioredis) ?ㅽ뙣: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        if self._sync_client:
            try:
                res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "SLAVES", self._master_name)
                if isinstance(res, dict) and res.get("_error"):
                    logger.warning("slaves_info (sync) ?ㅽ뙣: %s", res.get("_error"))
                    return []
                return [{"slaves_raw": res}]
            except Exception as exc:
                logger.warning("slaves_info (sync) ?덉쇅: %s", exc, exc_info=True)

        return []

    async def sentinels_info(self) -> List[Dict[str, Any]]:
        """
        Sentinel ?몃뱶?ㅼ쓽 硫뷀? ?뺣낫 諛섑솚.
        - aioredis媛 ?덉쑝硫?癒쇱? ?쒕룄, ?ㅽ뙣?섎㈃ sync ?덉쟾 ?대갚
        """
        results: List[Dict[str, Any]] = []
        if self._sentinel and aioredis:
            for host, port in self._sentinel_hosts:
                try:
                    r = aioredis.Redis(host=host, port=port, password=self._password)
                    data = await r.execute_command("SENTINEL", "SENTINELS", self._master_name)
                    await r.close()
                    results.append({"host": host, "port": port, "data": data})
                except RedisResponseError as exc:
                    logger.warning("sentinels_info (aioredis) ResponseError %s:%s: %s", host, port, exc)
                    self._sentinel = None
                    self._aioredis_available = False
                    break
                except Exception as exc:
                    logger.warning("sentinels_info (aioredis) %s:%s ?ㅽ뙣: %s", host, port, exc)
            if results:
                return results

        if self._sync_client:
            for host, port in self._sentinel_hosts:
                try:
                    res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "SENTINELS", self._master_name)
                    if isinstance(res, dict) and res.get("_error"):
                        logger.warning("sentinels_info (sync) %s:%s ?ㅽ뙣: %s", host, port, res.get("_error"))
                    else:
                        results.append({"host": host, "port": port, "data": res})
                except Exception as exc:
                    logger.warning("sentinels_info (sync) %s:%s ?덉쇅: %s", host, port, exc, exc_info=True)
            return results

        return results

    async def failover(self) -> bool:
        """
        ?섎룞 ?섏씪?ㅻ쾭 ?몃━嫄?(?깃났 ??True).
        - aioredis ?곗꽑, ?ㅽ뙣 ??sync ?덉쟾 ?대갚
        """
        if self._sentinel and aioredis:
            for host, port in self._sentinel_hosts:
                try:
                    r = aioredis.Redis(host=host, port=port, password=self._password)
                    await r.execute_command("SENTINEL", "FAILOVER", self._master_name)
                    await r.close()
                    logger.info("failover ?몃━嫄??깃났 via %s:%s", host, port)
                    return True
                except RedisResponseError as exc:
                    logger.warning("failover (aioredis) ResponseError %s:%s: %s", host, port, exc)
                    self._sentinel = None
                    self._aioredis_available = False
                    break
                except Exception as exc:
                    logger.warning("failover (aioredis) via %s:%s ?ㅽ뙣: %s", host, port, exc)

        if self._sync_client:
            for host, port in self._sentinel_hosts:
                try:
                    res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "FAILOVER", self._master_name)
                    if isinstance(res, dict) and res.get("_error"):
                        logger.warning("failover (sync) via %s:%s ?ㅽ뙣: %s", host, port, res.get("_error"))
                    else:
                        logger.info("failover ?몃━嫄??깃났 via %s:%s", host, port)
                        return True
                except Exception as exc:
                    logger.warning("failover (sync) via %s:%s ?덉쇅: %s", host, port, exc, exc_info=True)

        return False
