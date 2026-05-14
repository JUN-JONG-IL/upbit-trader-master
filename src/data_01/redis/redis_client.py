#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 클라이언트 헬퍼 모듈 (안정판)
- 목적: 레포 전체에서 일관된 방식으로 Redis 연결을 얻고,
  자주 쓰이는 작업(키/JSON 저장, LPUSH/BRPOP, XADD, PUBLISH 등)을 제공.
- 특징:
  - 외부 redis 패키지 우선 로드 시도 (로컬 패키지 충돌 방지)
  - 환경변수(REDIS_URL, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD) 기반 연결 팩토리
  - 모듈 수준 캐시 및 스레드 잠금으로 커넥션 재사용 보장
  - JSON/리스트/스트림/퍼블리시 헬퍼 제공
  - 한글 주석과 최소한의 로깅 포함
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import site
import sys
import threading
import json
from typing import Optional, Any, Dict, List
from urllib.parse import urlparse, unquote
from pathlib import Path

logger = logging.getLogger("data.redis.client")
# 중복 핸들러 추가 방지
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] [redis_client] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# -------------------------
# 안전하게 redis 모듈 로드 (로컬 충돌 시 site-packages에서 외부 모듈 시도)
# -------------------------
def _load_external_redis_from_sitepackages() -> Optional[object]:
    """
    site-packages 경로들을 검사해 외부 redis 패키지를 파일로 로드하여 반환.
    로컬 패키지명이 redis여서 충돌하는 상황을 우회하기 위해 사용합니다.
    """
    candidates = list(dict.fromkeys(sys.path + (site.getsitepackages() if hasattr(site, "getsitepackages") else [])))
    for base in candidates:
        if not base:
            continue
        try:
            pkg_init = Path(base) / "redis" / "__init__.py"
            if pkg_init.exists():
                spec = importlib.util.spec_from_file_location("redis_external_sitepkg", str(pkg_init))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    logger.debug("loaded external redis from site-packages: %s", pkg_init)
                    return mod
        except Exception:
            logger.debug("failed to load candidate redis at %s", base, exc_info=True)
            continue
    return None

_redis_mod = None
AuthenticationError = Exception
RedisError = Exception

try:
    # 일반적으로 설치된 redis 패키��� import 시도
    _loaded = importlib.import_module("redis")
    mod_file = getattr(_loaded, "__file__", "") or ""
    is_local = False
    try:
        # 레포 내부 경로 여부 판별: src/... 경로 내에 모듈 파일이 있으면 로컬 패키지로 간주
        repo_src = str(Path(__file__).resolve().parents[3])
        if mod_file and str(Path(mod_file).resolve()).startswith(repo_src):
            is_local = True
    except Exception:
        is_local = False

    if is_local:
        logger.debug("imported redis appears local (%s). trying to load external redis from site-packages", mod_file)
        ext = _load_external_redis_from_sitepackages()
        if ext:
            _redis_mod = ext
        else:
            # 외부 못 찾으면 기존 로컬 모듈을 사용하되 경고
            logger.warning("could not find external redis in site-packages; using imported redis (may be local package)")
            _redis_mod = _loaded
    else:
        _redis_mod = _loaded

    try:
        # redis.exceptions를 가져와 예외 타입을 맞춤
        from redis.exceptions import AuthenticationError as _AE, RedisError as _RE  # type: ignore
        AuthenticationError = _AE  # type: ignore
        RedisError = _RE  # type: ignore
    except Exception:
        AuthenticationError = Exception  # type: ignore
        RedisError = Exception  # type: ignore

except Exception as exc:
    logger.warning("redis import failed: %s", exc)
    _redis_mod = None
    AuthenticationError = Exception  # type: ignore
    RedisError = Exception  # type: ignore

# -------------------------
# 모듈 수준 캐시 및 잠금
# -------------------------
_CLIENT: Optional[Any] = None
_CLIENT_LOCK = threading.Lock()

def _build_client_from_parts(host: str, port: int, password: Optional[str], db: int = 0, timeout: int = 2):
    """
    주어진 호스트/포트/비밀번호/DB로부터 redis client 인스턴스를 생성 시도.
    redis-py 버전 차이에 따라 인자 호환성을 고려하여 생성합니다.
    max_connections=10: 연결 풀 최대 10개로 포트 고갈 방지.
    """
    if _redis_mod is None:
        logger.debug("_build_client_from_parts: redis module unavailable")
        return None
    try:
        ClientCls = getattr(_redis_mod, "Redis", None) or getattr(getattr(_redis_mod, "client", None), "Redis", None) or getattr(_redis_mod, "StrictRedis", None)
        if not ClientCls:
            logger.debug("_build_client_from_parts: no Redis class found in redis module")
            return None
        try:
            client = ClientCls(host=host, port=port, password=password, db=db,
                               socket_connect_timeout=timeout, decode_responses=True,
                               max_connections=10)
        except TypeError:
            # 일부 버전에서는 decode_responses/max_connections 인자를 못 받음
            try:
                client = ClientCls(host=host, port=port, password=password, db=db,
                                   socket_connect_timeout=timeout, decode_responses=True)
            except TypeError:
                client = ClientCls(host=host, port=port, password=password, db=db,
                                   socket_connect_timeout=timeout)
        return client
    except Exception:
        logger.exception("_build_client_from_parts failed")
        return None

def _build_client_from_url(url: str, timeout: int = 2):
    """
    REDIS_URL (redis://[:password@]host:port/db) 로부터 client 생성 시도.
    redis.from_url 함수가 있으면 우선 사용하고, 없으면 URL을 파싱해 생성합니다.
    """
    if _redis_mod is None:
        logger.debug("_build_client_from_url: redis module unavailable")
        return None
    try:
        from_url = getattr(_redis_mod, "from_url", None)
        if from_url:
            try:
                return from_url(url, socket_connect_timeout=timeout, decode_responses=True)
            except Exception:
                # fallback to manual parse
                pass
        p = urlparse(url)
        host = p.hostname or "localhost"
        port = p.port or 6379
        pwd = p.password and unquote(p.password) or None
        db = 0
        if p.path and p.path.strip("/").isdigit():
            db = int(p.path.strip("/"))
        return _build_client_from_parts(host, port, pwd, db=db, timeout=timeout)
    except Exception:
        logger.exception("_build_client_from_url fallback failed")
        return None

def connect_from_env(timeout: int = 2):
    """
    환경변수에서 Redis 연결을 얻는다.
    우선순위: REDIS_URL -> REDIS_HOST/REDIS_PORT/REDIS_DB (+ REDIS_PASSWORD) -> localhost
    """
    if _redis_mod is None:
        logger.warning("redis package not available; Redis features disabled")
        return None

    # 1) REDIS_URL
    url = os.getenv("REDIS_URL")
    if url:
        try:
            client = _build_client_from_url(url, timeout=timeout)
            if client:
                try:
                    client.ping()
                    logger.debug("connected via REDIS_URL")
                    return client
                except AuthenticationError:
                    logger.warning("auth error with REDIS_URL")
                except Exception:
                    logger.debug("ping failed using REDIS_URL", exc_info=True)
        except Exception:
            logger.exception("exception building from REDIS_URL")

    # 2) REDIS_HOST/REDIS_PORT/REDIS_DB
    host = os.getenv("REDIS_HOST")
    try:
        port = int(os.getenv("REDIS_PORT", "6379") or 6379)
    except Exception:
        port = 6379
    try:
        db = int(os.getenv("REDIS_DB", "0") or 0)
    except Exception:
        db = 0
    pwd = os.getenv("REDIS_PASSWORD") or None
    if host:
        try:
            client = _build_client_from_parts(host, port, pwd, db=db, timeout=timeout)
            if client:
                try:
                    client.ping()
                    logger.debug("connected via REDIS_HOST/PORT")
                    return client
                except AuthenticationError:
                    logger.warning("auth error using REDIS_HOST/PORT")
                except Exception:
                    logger.debug("ping failed using REDIS_HOST/PORT", exc_info=True)
        except Exception:
            logger.exception("exception building from host/port")

    # 3) localhost fallback
    try:
        client = _build_client_from_parts("localhost", 6379, None, timeout=timeout)
        if client:
            try:
                client.ping()
                logger.debug("connected to localhost")
                return client
            except Exception:
                logger.debug("localhost ping failed")
    except Exception:
        pass

    logger.error("connect_from_env failed")
    return None

def get_client(timeout: int = 2):
    """
    모듈 수준으로 캐시된 low-level redis client 반환.
    internal 용도: RedisClient 래퍼에서 사용됨.
    """
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            try:
                _CLIENT.ping()
                return _CLIENT
            except Exception:
                logger.debug("cached client ping failed; recreating", exc_info=True)
                try:
                    if hasattr(_CLIENT, "close"):
                        _CLIENT.close()
                except Exception:
                    logger.debug("cached client close failed", exc_info=True)
                _CLIENT = None
        client = connect_from_env(timeout=timeout)
        if client:
            _CLIENT = client
        return _CLIENT

def close_client():
    """모듈 수준 클라이언트 안전 종료"""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT:
            try:
                if hasattr(_CLIENT, "close"):
                    _CLIENT.close()
            except Exception:
                logger.debug("close_client: close failed", exc_info=True)
            _CLIENT = None
            logger.debug("close_client: Redis client closed")

# -------------------------
# RedisClient 클래스: 편의 래퍼
# -------------------------
class RedisClient:
    """
    고수준 Redis 유틸리티 클래스
    - 내부에 low-level client 인스턴스를 보관하며 편의 메서드를 제공
    - use_cached=True 시 모듈 수준 캐시(get_client)를 우선 사용

    싱글톤 패턴 적용 (thread-safe Double-Checked Locking):
    - 동일한 프로세스 내에서 인스턴스를 하나만 생성하여 포트 고갈 방지
    """
    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # 싱글톤 인스턴스 생성 (Double-Checked Locking)
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, db: int = 0, use_cached: bool = True, timeout: int = 2):
        # 중복 초기화 방지
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._timeout = timeout
        self._client = None
        # 모듈 수준 캐시 사용 시 get_client로부터 low-level client를 얻음
        if use_cached:
            self._client = get_client(timeout=timeout)
        if self._client is None:
            h = host or os.getenv("REDIS_HOST", "localhost")
            try:
                p = int(port or os.getenv("REDIS_PORT", "6379"))
            except Exception:
                p = 6379
            pwd = os.getenv("REDIS_PASSWORD") or None
            self._client = _build_client_from_parts(h, p, pwd, db=db, timeout=timeout)
        if self._client is None:
            raise RuntimeError("Redis 클라이언트를 생성할 수 없습니다. redis 패키지 설치/환경변수 확인 필요")

    # ---------- 기본 키/값 ----------
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """문자열 값 저장 (ttl 초 단위)"""
        try:
            if ttl:
                return bool(self._client.setex(key, ttl, value))
            return bool(self._client.set(key, value))
        except Exception:
            logger.exception("set failed")
            return False

    def get(self, key: str) -> Optional[str]:
        """문자열 값 조회"""
        try:
            return self._client.get(key)
        except Exception:
            logger.exception("get failed")
            return None

    def ping(self) -> bool:
        """Ping으로 연결 확인"""
        try:
            return bool(self._client.ping())
        except Exception:
            logger.debug("ping failed", exc_info=True)
            return False

    def close(self) -> None:
        """클라이언트 종료(있을 경우)"""
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            logger.debug("close failed", exc_info=True)

    # ---------- JSON 헬퍼 ----------
    def set_json(self, key: str, obj: Any, ttl: Optional[int] = None) -> bool:
        """객체를 JSON 직렬화하여 저장"""
        try:
            s = json.dumps(obj, default=str, ensure_ascii=False)
            return self.set(key, s, ttl=ttl)
        except Exception:
            logger.exception("set_json failed")
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """JSON 역직렬화하여 반환"""
        try:
            v = self.get(key)
            if v is None:
                return None
            return json.loads(v)
        except Exception:
            logger.exception("get_json failed")
            return None

    # ---------- 리스트 기반 큐 헬퍼 (LPUSH / BRPOP) ----------
    def lpush_json(self, queue: str, obj: Any) -> bool:
        """객체를 JSON으로 직렬화하여 LPUSH"""
        try:
            s = json.dumps(obj, default=str, ensure_ascii=False)
            self._client.lpush(queue, s)
            return True
        except AuthenticationError:
            logger.exception("lpush_json auth error")
            return False
        except Exception:
            logger.exception("lpush_json failed")
            return False

    def brpop_json(self, queue: str, timeout: int = 5) -> Optional[Any]:
        """BRPOP으로 블록킹 팝(튜플 또는 None). JSON 파싱 반환"""
        try:
            item = self._client.brpop(queue, timeout=timeout)
            if not item:
                return None
            payload = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else item
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return json.loads(payload)
        except AuthenticationError:
            logger.exception("brpop_json auth error")
            return None
        except Exception:
            logger.exception("brpop_json failed")
            return None

    # ---------- Streams (XADD) 간단 헬퍼 ----------
    def xadd_json(self, stream: str, obj: Dict[str, Any], maxlen: Optional[int] = None) -> Optional[str]:
        """
        Redis Streams에 JSON 필드로 추가.
        - maxlen: 트림 길이 (approx) 예: 10000
        """
        try:
            payload = json.dumps(obj, default=str, ensure_ascii=False)
            if maxlen:
                return self._client.xadd(stream, {"data": payload}, maxlen=maxlen, approximate=True)
            return self._client.xadd(stream, {"data": payload})
        except Exception:
            logger.exception("xadd_json failed")
            return None

    # ---------- Pub/Sub publish 헬퍼 ----------
    def publish_json(self, channel: str, obj: Any) -> bool:
        """채널에 JSON 메시지 publish"""
        try:
            payload = json.dumps(obj, default=str, ensure_ascii=False)
            self._client.publish(channel, payload)
            return True
        except Exception:
            logger.exception("publish_json failed")
            return False

    # ---------- 편의 유틸 ----------
    def keys(self, pattern: str) -> List[str]:
        """주의: 운영에서는 SCAN 권장"""
        try:
            return list(self._client.keys(pattern))
        except Exception:
            logger.exception("keys failed")
            return []

    def llen(self, key: str) -> int:
        try:
            return int(self._client.llen(key) or 0)
        except Exception:
            logger.exception("llen failed")
            return 0

# -------------------------
# 외부용 팩토리 함수
# -------------------------
def get_redis_client(host: Optional[str] = None, port: Optional[int] = None, db: int = 0, use_cached: bool = True, timeout: int = 2) -> RedisClient:
    """
    편의 팩토리: RedisClient 인스턴스 반환
    - 다른 모듈들은 이 함수명을 사용하여 일관적으로 클라이언트를 얻습니다.
    """
    return RedisClient(host=host, port=port, db=db, use_cached=use_cached, timeout=timeout)

__all__ = ["get_redis_client", "RedisClient", "get_client", "close_client"]