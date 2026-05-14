#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
timescale_redis.py

Redis 연결/큐/publish 헬퍼 (최종 안정판)

- 환경변수 우선순위: REDIS_URL -> REDIS_URL_CONTAINER -> REDIS_HOST/REDIS_PORT -> localhost:6379
- REDIS_URL 실패 시 로컬 127.0.0.1:6379로 안전 폴백
- publish_status에서 채널 레지스트리(pubsub:channels) SADD 추가
- 한글 주석 포함
"""
from __future__ import annotations

import os
import json
import logging
import threading
import importlib
import importlib.util
import site
import sys
import socket
import time
from typing import Optional, Any, Dict, List, Tuple
from urllib.parse import urlparse, unquote
from pathlib import Path

# 로거 설정
logger = logging.getLogger("data.timescale.redis")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(asctime)s] [timescale_redis] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# -------------------------
# 안전 로깅 래퍼: 모든 로깅 호출을 안전하게 감싸서
# 핸들러/스트림이 닫혀 있을 때 ValueError 발생을 방지
# -------------------------
def _safe_log(func, *args, **kwargs):
    """
    안전 로깅:
    - logger.handlers의 stream 속성이 닫혀 있으면 logger 호출을 피하고 stderr로 직접 출력합니다.
    - 그렇지 않으면 logger 호출을 시도하되 예외는 무시합니다.
    """
    try:
        # 검사: 어떤 핸들러라도 닫힌 stream이 있는지 확인
        try:
            handlers = getattr(logger, "handlers", []) or []
            stream_is_closed = False
            for h in handlers:
                # 일부 핸들러는 stream 대신 'stream' 속성을 갖지 않을 수 있음
                stream = getattr(h, "stream", None)
                if stream is not None:
                    try:
                        if getattr(stream, "closed", False):
                            stream_is_closed = True
                            break
                    except Exception:
                        # 안전하게 무시
                        pass
        except Exception:
            handlers = []
            stream_is_closed = False

        if stream_is_closed:
            # 핸들러 스트림이 닫혀있으면 logging 모듈 호출을 피함
            try:
                # 포맷 맞춰 stderr에 남김. args[0]이 포맷 문자열일 경우 포맷 적용 시도.
                if args:
                    try:
                        msg = args[0] % args[1:] if isinstance(args[0], str) else str(args)
                    except Exception:
                        msg = str(args)
                else:
                    msg = ""
                print(f"[timescale_redis] LOG (fallback): {msg}", file=sys.stderr)
            except Exception:
                try:
                    print(f"[timescale_redis] LOG (fallback) - args: {args}", file=sys.stderr)
                except Exception:
                    pass
            return

        # 정상 경로: logger 호출 (추가 예외 방지)
        try:
            func(*args, **kwargs)
        except Exception:
            # logger 호출 도중 문제가 생기면 stderr로 최소 메시지 출력
            try:
                if args:
                    try:
                        msg = args[0] % args[1:] if isinstance(args[0], str) else str(args)
                    except Exception:
                        msg = str(args)
                else:
                    msg = ""
                print(f"[timescale_redis] logging failed during emit: {msg}", file=sys.stderr)
            except Exception:
                pass
    except Exception:
        # 최후 수단: 아무것도 못함(무시)
        try:
            print(f"[timescale_redis] _safe_log unexpected failure", file=sys.stderr)
        except Exception:
            pass

def _info(*a, **k):
    _safe_log(logger.info, *a, **k)

def _debug(*a, **k):
    _safe_log(logger.debug, *a, **k)

def _warning(*a, **k):
    _safe_log(logger.warning, *a, **k)

def _error(*a, **k):
    _safe_log(logger.error, *a, **k)

def _exception(*a, **k):
    # logger.exception appends traceback; keep behavior but wrap
    _safe_log(logger.exception, *a, **k)

# -------------------------
# 외부 redis 패키지 우회 로드 (site-packages 검색)
# -------------------------
def _load_external_redis_from_sitepackages() -> Optional[object]:
    candidates = []
    try:
        candidates.extend(sys.path)
    except Exception:
        pass
    try:
        if hasattr(site, "getsitepackages"):
            candidates.extend(site.getsitepackages())
    except Exception:
        pass
    seen = set()
    for base in candidates:
        if not base or base in seen:
            continue
        seen.add(base)
        try:
            pkg_init = Path(base) / "redis" / "__init__.py"
            if pkg_init.exists():
                spec = importlib.util.spec_from_file_location("redis_external_sitepkg", str(pkg_init))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    _debug("loaded external redis from site-packages: %s", str(pkg_init))
                    return mod
        except Exception:
            _debug("failed to load candidate redis at %s", str(base), exc_info=True)
            continue
    return None

# -------------------------
# redis 모듈 로드 및 예외 타입 확보
# -------------------------
redis = None
AuthenticationError = Exception
RedisError = Exception

try:
    loaded = importlib.import_module("redis")
    mod_file = getattr(loaded, "__file__", "") or ""
    is_local = False
    try:
        repo_src = str(Path(__file__).resolve().parents[3])
        if mod_file and str(Path(mod_file).resolve()).startswith(repo_src):
            is_local = True
    except Exception:
        is_local = False

    if is_local:
        ext = _load_external_redis_from_sitepackages()
        if ext:
            redis = ext
        else:
            _warning("redis import appears local; external redis not found in site-packages; using imported module (may be local)")
            redis = loaded
    else:
        redis = loaded

    try:
        from redis.exceptions import AuthenticationError as _AE, RedisError as _RE  # type: ignore
        AuthenticationError = _AE  # type: ignore
        RedisError = _RE  # type: ignore
    except Exception:
        AuthenticationError = Exception  # type: ignore
        RedisError = Exception  # type: ignore

    _has_redis_client = False
    try:
        if redis is not None:
            if hasattr(redis, "Redis") or hasattr(redis, "StrictRedis"):
                _has_redis_client = True
            else:
                client_mod = getattr(redis, "client", None)
                if client_mod and (hasattr(client_mod, "Redis") or hasattr(client_mod, "StrictRedis")):
                    _has_redis_client = True
    except Exception:
        _has_redis_client = False

    if not _has_redis_client:
        _warning("Imported 'redis' module does not expose Redis client class — Redis features disabled.")
        redis = None

except Exception as exc:
    _warning("redis package import failed or unavailable: %s", exc)
    redis = None
    AuthenticationError = Exception
    RedisError = Exception

# -------------------------
# 기본 구성
# -------------------------
DEFAULT_QUEUE = os.getenv("TIMESCALE_REDIS_QUEUE", "gap_fill_queue")
DEFAULT_STATUS_CHANNEL = os.getenv("TIMESCALE_REDIS_STATUS_CHANNEL", "timescale:backfill:status")

_CLIENT: Optional[Any] = None
_CLIENT_LOCK = threading.Lock()

# -------------------------
# 네트워크 헬퍼
# -------------------------
def _tcp_probe(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

# -------------------------
# 클라이언트 빌드 유틸
# -------------------------
def _build_client_from_parts(host: str, port: int, password: Optional[str], db: int = 0, timeout: int = 5):
    if redis is None:
        _debug("_build_client_from_parts: redis module unavailable")
        return None
    try:
        client_cls = getattr(redis, "Redis", None) or getattr(getattr(redis, "client", None), "Redis", None) or getattr(redis, "StrictRedis", None)
        if not client_cls:
            _debug("_build_client_from_parts: no Redis class found in redis module")
            return None
        try:
            client = client_cls(host=host, port=port, password=password, db=db,
                                socket_connect_timeout=timeout, decode_responses=True)
        except TypeError:
            client = client_cls(host=host, port=port, password=password, db=db,
                                socket_connect_timeout=timeout)
        return client
    except Exception:
        _exception("_build_client_from_parts failed")
        return None

def _build_client_from_url(url: str, timeout: int = 5):
    if redis is None:
        _debug("_build_client_from_url: redis module unavailable")
        return None
    try:
        from_url = getattr(redis, "from_url", None)
        if from_url:
            try:
                return from_url(url, socket_connect_timeout=timeout, decode_responses=True)
            except Exception:
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
        _exception("_build_client_from_url fallback failed")
        return None

# -------------------------
# 환경변수 기반 연결 시도 및 안전 폴백 로직
# -------------------------
def _parse_url_host_port(url: str) -> Tuple[str, int]:
    try:
        p = urlparse(url)
        return (p.hostname or "127.0.0.1", p.port or 6379)
    except Exception:
        return ("127.0.0.1", 6379)

def connect_redis_from_env(timeout: int = 5) -> Optional[Any]:
    if redis is None:
        _warning("redis package not installed or invalid; Redis features disabled")
        return None

    tried: List[str] = []

    url = os.getenv("REDIS_URL")
    if url:
        tried.append(f"REDIS_URL={url}")
        host, port = _parse_url_host_port(url)
        _debug("connect_redis_from_env: parsing REDIS_URL -> %s:%s", host, port)
        try:
            client = _build_client_from_url(url, timeout=timeout)
            if client:
                try:
                    client.ping()
                    _info("connected via REDIS_URL: %s", url)
                    return client
                except AuthenticationError:
                    _warning("Authentication error using REDIS_URL")
                except Exception:
                    _debug("ping failed using REDIS_URL, will probe and maybe fallback", exc_info=True)
            else:
                _debug("client build from REDIS_URL returned None")
        except Exception:
            _exception("exception building from REDIS_URL")

        try:
            if host in ("127.0.0.1", "localhost") and port != 6379:
                _info("REDIS_URL host is local but port=%s != 6379; probing default 127.0.0.1:6379 as fallback", port)
                if _tcp_probe("127.0.0.1", 6379, timeout=1.0):
                    _info("fallback probe succeeded: trying 127.0.0.1:6379")
                    tried.append("FALLBACK=127.0.0.1:6379")
                    client = _build_client_from_parts("127.0.0.1", 6379, None, timeout=timeout)
                    if client:
                        try:
                            client.ping()
                            _info("connected via FALLBACK 127.0.0.1:6379")
                            return client
                        except Exception:
                            _debug("fallback ping failed", exc_info=True)
                else:
                    _debug("fallback probe 127.0.0.1:6379 failed")
        except Exception:
            _debug("fallback probe exception", exc_info=True)

    urlc = os.getenv("REDIS_URL_CONTAINER") or os.getenv("REDIS_URL_C") or None
    if urlc:
        tried.append(f"REDIS_URL_CONTAINER={urlc}")
        try:
            client = _build_client_from_url(urlc, timeout=timeout)
            if client:
                try:
                    client.ping()
                    _info("connected via REDIS_URL_CONTAINER")
                    return client
                except Exception:
                    _debug("ping failed using REDIS_URL_CONTAINER", exc_info=True)
        except Exception:
            _exception("exception building from REDIS_URL_CONTAINER")

    host = os.getenv("REDIS_HOST")
    try:
        port = int(os.getenv("REDIS_PORT", "6379") or 6379)
    except Exception:
        port = 6379
    pwd = os.getenv("REDIS_PASSWORD") or None
    if host:
        tried.append(f"REDIS_HOST={host} REDIS_PORT={port}")
        if not _tcp_probe(host, port, timeout=1.0):
            _debug("TCP probe failed for %s:%s before build; will still attempt client build (redis client may use different sockets).", host, port)
        try:
            client = _build_client_from_parts(host, port, pwd, timeout=timeout)
            if client:
                try:
                    client.ping()
                    _info("connected via REDIS_HOST/PORT: %s:%s", host, port)
                    return client
                except AuthenticationError:
                    _warning("AuthenticationError using REDIS_HOST/PORT")
                except Exception:
                    _exception("ping failed using REDIS_HOST/PORT")
        except Exception:
            _exception("exception building from host/port")

    tried.append("localhost:6379 (final fallback)")
    try:
        if _tcp_probe("127.0.0.1", 6379, timeout=1.0):
            client = _build_client_from_parts("127.0.0.1", 6379, None, timeout=timeout)
            if client:
                try:
                    client.ping()
                    _info("connected to localhost:6379 (final fallback)")
                    return client
                except Exception:
                    _debug("final fallback ping failed", exc_info=True)
        else:
            _debug("final fallback tcp probe 127.0.0.1:6379 failed")
    except Exception:
        _exception("exception trying final fallback")

    _error("connect_redis_from_env failed; tried endpoints: %s", tried)
    return None

# (나머지 파일 내용은 변경되지 않았습니다)
# -------------------------
# 모듈 수준 클라이언트 캐시
# -------------------------
def get_client(timeout: int = 5) -> Optional[Any]:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            try:
                _CLIENT.ping()
                return _CLIENT
            except Exception:
                _debug("get_client: cached client ping failed; reconnecting", exc_info=True)
                try:
                    if hasattr(_CLIENT, "close"):
                        _CLIENT.close()
                except Exception:
                    _debug("get_client: cached client close failed", exc_info=True)
                _CLIENT = None
        client = connect_redis_from_env(timeout=timeout)
        if client:
            _CLIENT = client
        return _CLIENT

def close_client() -> None:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT:
            try:
                if hasattr(_CLIENT, "close"):
                    _CLIENT.close()
            except Exception:
                _debug("close_client: close failed", exc_info=True)
            _CLIENT = None
            _debug("close_client: Redis client closed")

# -------------------------
# get_status 구현 추가
# -------------------------
def get_status(timeout: int = 3, queue_preview_count: int = 10) -> Dict[str, Any]:
    """
    Redis 상태를 조회하여 UI/헬퍼에 전달할 정보 반환.
    반환 형식(예시):
    {
        "connected": True/False,
        "redis_version": "7.4.7",
        "used_memory": "1.23M",
        "keyspace": {"db0": 3, "db1": 0},
        "server_time": 1670000000.0,
        "queue_preview": ["item1", "item2", ...],  # 최대 queue_preview_count개
        "error": "error message if any"
    }

    - 안전성: Redis 클라이언트가 없거나 명령 실패 시 예외를 흘려보내지 않고 에러 정보를 포함하여 False 상태를 반환합니다.
    - 한글 주석 포함.
    """
    status: Dict[str, Any] = {"connected": False}
    client = None
    try:
        client = get_client(timeout=timeout)
        if client is None:
            status["error"] = "redis client unavailable"
            _warning("get_status: redis client unavailable")
            return status

        # 연결 확인(ping)
        try:
            pong = client.ping()
            status["connected"] = bool(pong)
        except AuthenticationError:
            status["connected"] = False
            status["error"] = "authentication error"
            _warning("get_status: authentication error")
            return status
        except Exception as e:
            status["connected"] = False
            status["error"] = f"ping failed: {e}"
            _debug("get_status: ping failed", exc_info=True)
            return status

        # INFO 조회
        try:
            info = client.info() or {}
            # 주요 필드 발췌
            status["redis_version"] = info.get("redis_version")
            status["used_memory"] = info.get("used_memory_human") or info.get("used_memory")
            status["uptime_in_seconds"] = info.get("uptime_in_seconds")
            # keyspace 파싱 (예: {'db0': 'keys=3,expires=0,avg_ttl=0'})
            keyspace = {}
            raw_keyspace = info.get("keyspace", {}) or {}
            try:
                for dbk, v in raw_keyspace.items():
                    if isinstance(v, dict):
                        # redis-py 4.x may already parse keyspace into dict
                        keyspace[dbk] = int(v.get("keys", 0))
                    else:
                        # 문자열 파싱
                        parts = {}
                        for p in str(v).split(","):
                            if "=" in p:
                                k2, v2 = p.split("=", 1)
                                try:
                                    parts[k2] = int(v2)
                                except Exception:
                                    parts[k2] = v2
                        keyspace[dbk] = int(parts.get("keys", 0))
            except Exception:
                _debug("get_status: keyspace parsing failed", exc_info=True)
            status["keyspace"] = keyspace

            # 서버 시간 (INFO의 server_time이 없으면 TIME 명령 사용)
            try:
                server_time = info.get("server_time")
                if not server_time:
                    # client.time() returns [seconds, microseconds]
                    t = client.time()
                    if isinstance(t, (list, tuple)) and len(t) >= 1:
                        server_time = float(t[0]) + (float(t[1]) / 1_000_000.0 if len(t) > 1 else 0.0)
                status["server_time"] = server_time
            except Exception:
                _debug("get_status: server time retrieval failed", exc_info=True)

        except Exception as e:
            status["error"] = f"info failed: {e}"
            _debug("get_status: info failed", exc_info=True)
            return status

        # 큐(리스트) 프리뷰: DEFAULT_QUEUE 의 상위 N개
        try:
            # lrange 사용 시 decode_responses=True일 경우 문자열로 복원됨
            if client.exists(DEFAULT_QUEUE):
                preview = client.lrange(DEFAULT_QUEUE, 0, max(0, queue_preview_count - 1))
                status["queue_preview"] = preview
                status["queue_length"] = client.llen(DEFAULT_QUEUE)
            else:
                status["queue_preview"] = []
                status["queue_length"] = 0
        except Exception:
            _debug("get_status: queue preview failed", exc_info=True)
            status.setdefault("queue_preview", [])
            status.setdefault("queue_length", None)

        # 추가: pubsub 등록 채널 수 조회(선택적)
        try:
            # pubsub_channels는 redis-py의 pubsub_channels() 또는 client.execute_command('PUBSUB CHANNELS')
            channels = []
            try:
                # redis-py 4.x has pubsub_channels
                if hasattr(client, "pubsub_channels"):
                    channels = client.pubsub_channels()
                else:
                    # fallback to raw command
                    channels = client.execute_command("PUBSUB", "CHANNELS") or []
            except Exception:
                channels = client.execute_command("PUBSUB", "CHANNELS") or []
            status["pubsub_channels_count"] = len(channels) if channels is not None else 0
        except Exception:
            _debug("get_status: pubsub channels fetch failed", exc_info=True)

        return status

    except Exception as e:
        _exception("get_status unexpected exception")
        try:
            status["error"] = str(e)
        except Exception:
            status["error"] = "unknown error"
        status["connected"] = False
        return status

# (계속되는 기존 구현...)
# -------------------------
# 명시적 공개 심볼
__all__ = [
    "get_client", "close_client", "lpush_json", "brpop_json", "rpop_json",
    "publish_status", "list_pubsub_channels", "get_sortedset_top",
    "get_l1_expiring_keys", "get_gap_queue_preview", "clear_queue",
    "clear_keys_by_prefix", "get_status", "DEFAULT_QUEUE", "DEFAULT_STATUS_CHANNEL"
]