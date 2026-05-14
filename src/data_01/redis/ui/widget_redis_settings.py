#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sentinel_manager - 비동기 우선, 동기 폴백 방식 (sync 예외 안전 실행 보강)

설계 요지:
- aioredis (비동기)를 우선 사용하되, SENTINEL 명령을 지원하지 않거나 예외가 발생하면
  aioredis 경로를 비활성화하고 안전한 sync 폴백을 시도합니다.
- sync 폴백의 execute_command는 스레드 내부에서 발생하는 예외를 캡처하여
  호출자에게 에러 딕셔너리로 반환하도록 하여 프로세스 스택트레이스를 방지합니다.
- 모든 블로킹 동작은 run_in_executor로 실행됩니다.
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

# aioredis (비동기) 시도
try:
    import redis.asyncio as aioredis  # type: ignore
except Exception:
    aioredis = None  # type: ignore
    logger.debug("redis.asyncio not available; will use sync fallback if possible")

# redis.exceptions.ResponseError 추출 (있을 경우)
try:
    import redis.exceptions as _rexc  # type: ignore
    RedisResponseError = getattr(_rexc, "ResponseError", Exception)
except Exception:
    RedisResponseError = Exception

# get_redis_client 팩토리 동적 로드(상대 import 실패 회피)
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
    """블로킹 함수를 기본 스레드풀에서 실행"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _safe_sync_exec(sync_client: Any, *cmd_args) -> Any:
    """
    sync client.execute_command를 안전하게 호출하는 헬퍼.
    - 스레드에서 실행되며 내부 예외는 잡아서 {'_error': str(e)} 형태로 반환.
    - 반환값이 dict이고 '_error' 키가 있으면 실패를 의미.
    """
    try:
        # some clients expose execute_command on client, others may not.
        exec_fn = getattr(sync_client, "execute_command", None)
        if exec_fn is None:
            # fallback: try to call client.sentinel or raw commands (best-effort)
            raise RuntimeError("sync client has no execute_command")
        return exec_fn(*cmd_args)
    except Exception as e:
        # 스레드 내부에서 예외 흘러나가는 것을 막기 위해 에러 정보를 반환
        try:
            return {"_error": str(e)}
        except Exception:
            return {"_error": "unknown error in _safe_sync_exec"}


class SentinelManager:
    """
    Redis Sentinel 질의 관리자.
    - sentinel_hosts: [(host, port), ...]
    - master_name: Sentinel이 모니터링하는 master 이름 (기본 'mymaster')
    - password: optional
    """

    def __init__(self, sentinel_hosts: List[SentinelHost], master_name: str = "mymaster", password: Optional[str] = None) -> None:
        self._sentinel_hosts = list(sentinel_hosts or [])
        self._master_name = master_name
        self._password = password
        self._sentinel: Optional[Any] = None      # aioredis.Sentinel 인스턴스(있을 경우)
        self._sync_client: Optional[Any] = None   # sync low-level client 폴백
        self._aioredis_available = bool(aioredis)

    async def connect(self) -> None:
        """
        Sentinel 연결 준비.
        - aioredis 가용하면 aioredis.Sentinel 생성 시도.
        - 항상 sync 폴백 준비(존재하면 raw client를 _sync_client에 저장).
        """
        # aioredis 경로 시도
        if aioredis and self._aioredis_available:
            try:
                self._sentinel = aioredis.Sentinel(self._sentinel_hosts, password=self._password)
                logger.info("SentinelManager: aioredis Sentinel 객체 생성 시도: %s", self._sentinel_hosts)
            except Exception as exc:
                logger.warning("SentinelManager: aioredis Sentinel 생성 실패: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        # sync 폴백 준비 (get_redis_client 팩토리 사용)
        try:
            factory = _get_redis_client
            if factory:
                wrapper = factory(use_cached=True)
                raw = getattr(wrapper, "_client", None) or getattr(wrapper, "client", None) or wrapper
                self._sync_client = raw
                logger.info("SentinelManager: sync redis client fallback 준비")
            else:
                logger.debug("SentinelManager: get_redis_client factory 없음 - sync fallback 불가")
        except Exception as exc:
            logger.warning("SentinelManager: sync client fallback 준비 실패: %s", exc, exc_info=True)
            self._sync_client = None

    async def close(self) -> None:
        """연결 정리: aioredis 객체는 상위에서 처리가능, sync 폴백은 close 시도"""
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
            logger.exception("SentinelManager.close 예외")

    async def master_info(self) -> Dict[str, Any]:
        """
        모니터링 중인 master의 INFO 반환.
        - aioredis 우선, 실패 시 안전한 sync 폴백 시도
        """
        # aioredis 경로
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
                logger.warning("master_info (aioredis) 실패: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        # sync 안전 실행 폴백
        if self._sync_client:
            try:
                res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "MASTERS")
                if isinstance(res, dict) and res.get("_error"):
                    logger.warning("master_info (sync) 실패: %s", res.get("_error"))
                else:
                    return {"masters_raw": res}
            except Exception as exc:
                logger.warning("master_info (sync) 예외: %s", exc, exc_info=True)

        logger.debug("master_info: sentinel 연결 없음")
        return {}

    async def slaves_info(self) -> List[Dict[str, Any]]:
        """
        슬레이브 정보 반환.
        - aioredis 우선, 실패 시 sync 안전 폴백
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
                logger.warning("slaves_info (aioredis) 실패: %s", exc, exc_info=True)
                self._sentinel = None
                self._aioredis_available = False

        if self._sync_client:
            try:
                res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "SLAVES", self._master_name)
                if isinstance(res, dict) and res.get("_error"):
                    logger.warning("slaves_info (sync) 실패: %s", res.get("_error"))
                    return []
                return [{"slaves_raw": res}]
            except Exception as exc:
                logger.warning("slaves_info (sync) 예외: %s", exc, exc_info=True)

        return []

    async def sentinels_info(self) -> List[Dict[str, Any]]:
        """
        Sentinel 노드들의 메타 정보 반환.
        - aioredis가 있으면 먼저 시도, 실패하면 sync 안전 폴백
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
                    logger.warning("sentinels_info (aioredis) %s:%s 실패: %s", host, port, exc)
            if results:
                return results

        if self._sync_client:
            for host, port in self._sentinel_hosts:
                try:
                    res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "SENTINELS", self._master_name)
                    if isinstance(res, dict) and res.get("_error"):
                        logger.warning("sentinels_info (sync) %s:%s 실패: %s", host, port, res.get("_error"))
                    else:
                        results.append({"host": host, "port": port, "data": res})
                except Exception as exc:
                    logger.warning("sentinels_info (sync) %s:%s 예외: %s", host, port, exc, exc_info=True)
            return results

        return results

    async def failover(self) -> bool:
        """
        수동 페일오버 트리거 (성공 시 True).
        - aioredis 우선, 실패 시 sync 안전 폴백
        """
        if self._sentinel and aioredis:
            for host, port in self._sentinel_hosts:
                try:
                    r = aioredis.Redis(host=host, port=port, password=self._password)
                    await r.execute_command("SENTINEL", "FAILOVER", self._master_name)
                    await r.close()
                    logger.info("failover 트리거 성공 via %s:%s", host, port)
                    return True
                except RedisResponseError as exc:
                    logger.warning("failover (aioredis) ResponseError %s:%s: %s", host, port, exc)
                    self._sentinel = None
                    self._aioredis_available = False
                    break
                except Exception as exc:
                    logger.warning("failover (aioredis) via %s:%s 실패: %s", host, port, exc)

        if self._sync_client:
            for host, port in self._sentinel_hosts:
                try:
                    res = await _run_blocking(_safe_sync_exec, self._sync_client, "SENTINEL", "FAILOVER", self._master_name)
                    if isinstance(res, dict) and res.get("_error"):
                        logger.warning("failover (sync) via %s:%s 실패: %s", host, port, res.get("_error"))
                    else:
                        logger.info("failover 트리거 성공 via %s:%s", host, port)
                        return True
                except Exception as exc:
                    logger.warning("failover (sync) via %s:%s 예외: %s", host, port, exc, exc_info=True)

        return False