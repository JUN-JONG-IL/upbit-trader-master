#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
redis_db — Redis 연결/유틸 통합 레이어

목적:
- 레포의 get_redis_client 팩토리와 일관된 방식으로 Redis를 사용하도록 통합
- 문자열, JSON, 리스트, 스트림, pub/sub, 키 스캔 등의 공통 헬퍼 제공
- 내부적으로 wrapper RedisClient 또는 low-level client 모두 지원

사용법:
- 다른 모듈에서는 `from src._data_01.redis.redis_db import set_json, get_json, lpush_recent, ...` 등 사용
"""

from __future__ import annotations
import logging
import json
from typing import Any, Optional, Dict, List, Iterator, Callable
from pathlib import Path
import importlib.util

logger = logging.getLogger("redis_db")
if logger.level == logging.NOTSET:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(asctime)s] [redis_db] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)
logger.propagate = False

# 안전하게 get_redis_client 팩토리 로드 (상대 import 실패 시 파일 동적 로드)
def _load_get_redis_client() -> Optional[Callable[..., Any]]:
    try:
        # 정상 패키지 구조라면 상대 임포트 시도
        from .redis_client import get_redis_client  # type: ignore
        return get_redis_client
    except Exception:
        # dynamic load from repo path (개발 환경에서 상대 import 문제 회피)
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

# 모듈 수준 캐시(편의) — get_redis_client 내부 캐시와 중복 가능
_MODULE_CLIENT: Optional[Any] = None

def _ensure_wrapper(timeout: int = 2) -> Optional[Any]:
    """
    Redis wrapper 인스턴스(또는 low-level client)를 반환.
    - 내부적으로 get_redis_client(use_cached=True, timeout=...) 호출을 사용.
    - 실패 시 None 반환.
    """
    global _MODULE_CLIENT
    if _MODULE_CLIENT:
        try:
            if hasattr(_MODULE_CLIENT, "ping") and _MODULE_CLIENT.ping():
                return _MODULE_CLIENT
        except Exception:
            try:
                if hasattr(_MODULE_CLIENT, "close"):
                    _MODULE_CLIENT.close()
            except Exception:
                pass
            _MODULE_CLIENT = None

    if _get_redis_client is None:
        logger.debug("get_redis_client factory unavailable")
        return None
    try:
        wrapper = _get_redis_client(use_cached=True, timeout=timeout)
        # wrapper가 RedisClient wrapper일 수도 있으므로 ping 확인
        try:
            if hasattr(wrapper, "ping") and wrapper.ping():
                _MODULE_CLIENT = wrapper
                return wrapper
        except Exception:
            pass
        # fallback: wrapper 자체가 low-level client라면 반환
        _MODULE_CLIENT = wrapper
        return _MODULE_CLIENT
    except Exception:
        logger.exception("_ensure_wrapper: 클라이언트 생성 실패")
        _MODULE_CLIENT = None
        return None

def close_client():
    """모듈 수준 클라이언트 종료(테스트/정리용)"""
    global _MODULE_CLIENT
    if _MODULE_CLIENT:
        try:
            if hasattr(_MODULE_CLIENT, "close"):
                _MODULE_CLIENT.close()
        except Exception:
            logger.debug("close_client: close 실패", exc_info=True)
    _MODULE_CLIENT = None

# 헬퍼: wrapper에서 raw low-level client 추출
def _raw_client_from(wrapper: Any) -> Any:
    """
    wrapper가 있을 때 내부의 low-level client를 반환.
    - wrapper._client 또는 wrapper.client 존재 시 반환
    - 없으면 wrapper 자체를 low-level client로 간주
    """
    if wrapper is None:
        return None
    for attr in ("_client", "client", "redis"):
        try:
            raw = getattr(wrapper, attr, None)
            if raw:
                return raw
        except Exception:
            continue
    return wrapper

# ---------------------------
# 기본 키/값
# ---------------------------
def set_value(key: str, value: str, ttl: Optional[int] = None) -> bool:
    """문자열 값을 저장합니다. ttl이 주어지면 setex 사용."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("set_value: redis 클라이언트 없음")
        return False
    # wrapper may have set/setex implemented; prefer wrapper
    try:
        if hasattr(wrapper, "set"):
            if ttl:
                return bool(wrapper.set(key, value) if not hasattr(wrapper, "setex") else wrapper.setex(key, ttl, value))
            return bool(wrapper.set(key, value))
        raw = _raw_client_from(wrapper)
        if raw is None:
            return False
        if ttl:
            return bool(raw.setex(key, ttl, value))
        return bool(raw.set(key, value))
    except Exception:
        logger.exception("set_value 실패")
        return False

def get_value(key: str) -> Optional[str]:
    """문자열 값을 조회합니다."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("get_value: redis 클라이언트 없음")
        return None
    try:
        if hasattr(wrapper, "get"):
            return wrapper.get(key)
        raw = _raw_client_from(wrapper)
        if raw is None:
            return None
        return raw.get(key)
    except Exception:
        logger.exception("get_value 실패")
        return None

# ---------------------------
# JSON 헬퍼
# ---------------------------
def set_json(key: str, obj: Any, ttl: Optional[int] = None) -> bool:
    """객체를 JSON으로 저장"""
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
        return set_value(key, s, ttl=ttl)
    except Exception:
        logger.exception("set_json 실패")
        return False

def get_json(key: str) -> Optional[Any]:
    """JSON 문자열을 역직렬화하여 반환"""
    s = get_value(key)
    if s is None:
        return None
    try:
        return json.loads(s)
    except Exception:
        logger.exception("get_json 실패")
        return None

# ---------------------------
# 리스트 기반 큐 (LPUSH/BRPOP 등)
# ---------------------------
def lpush_recent(key: str, value: str, maxlen: int = 2000) -> bool:
    """LPUSH 후 LTRIM으로 고정 길이 유지 (최근 N개 보관)."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("lpush_recent: redis 클라이언트 없음")
        return False
    try:
        raw = _raw_client_from(wrapper)
        pipe = raw.pipeline() if raw is not None else None
        if pipe is None:
            # try wrapper lpush if available
            if hasattr(wrapper, "lpush"):
                wrapper.lpush(key, value)
                if hasattr(wrapper, "ltrim"):
                    wrapper.ltrim(key, 0, maxlen - 1)
                return True
            return False
        pipe.lpush(key, value)
        pipe.ltrim(key, 0, maxlen - 1)
        pipe.execute()
        return True
    except Exception:
        logger.exception("lpush_recent 실패")
        return False

def llen(key: str) -> int:
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("llen: redis 클라이언트 없음")
        return 0
    try:
        if hasattr(wrapper, "llen"):
            return int(wrapper.llen(key) or 0)
        raw = _raw_client_from(wrapper)
        if raw is None:
            return 0
        return int(raw.llen(key) or 0)
    except Exception:
        logger.exception("llen 실패")
        return 0

def brpop_json(key: str, timeout: int = 5) -> Optional[Any]:
    """BRPOP을 사용해 JSON 항목을 꺼냅니다(블록킹). 실패/타임아웃 시 None."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("brpop_json: redis 클라이언트 없음")
        return None
    try:
        # prefer wrapper.brpop if exists
        if hasattr(wrapper, "brpop"):
            item = wrapper.brpop(key, timeout=timeout)
        else:
            raw = _raw_client_from(wrapper)
            if raw is None:
                return None
            item = raw.brpop(key, timeout=timeout)
        if not item:
            return None
        payload = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else item
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return json.loads(payload)
    except Exception:
        logger.exception("brpop_json 실패")
        return None

# ---------------------------
# Streams (XADD) 단순 헬퍼
# ---------------------------
def xadd_json(stream: str, obj: Dict[str, Any], maxlen: Optional[int] = None) -> Optional[str]:
    """Redis Streams에 JSON을 'data' 필드로 추가합니다."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("xadd_json: redis 클라이언트 없음")
        return None
    try:
        payload = json.dumps(obj, default=str, ensure_ascii=False)
        if hasattr(wrapper, "xadd"):
            if maxlen:
                return wrapper.xadd(stream, {"data": payload}, maxlen=maxlen, approximate=True)
            return wrapper.xadd(stream, {"data": payload})
        raw = _raw_client_from(wrapper)
        if raw is None:
            return None
        if maxlen:
            return raw.xadd(stream, {"data": payload}, maxlen=maxlen, approximate=True)
        return raw.xadd(stream, {"data": payload})
    except Exception:
        logger.exception("xadd_json 실패")
        return None

# ---------------------------
# Pub/Sub publish
# ---------------------------
def publish_json(channel: str, obj: Any) -> bool:
    """채널에 JSON 메시지를 퍼블리시합니다."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("publish_json: redis 클라이언트 없음")
        return False
    try:
        payload = json.dumps(obj, default=str, ensure_ascii=False)
        if hasattr(wrapper, "publish"):
            wrapper.publish(channel, payload)
            return True
        raw = _raw_client_from(wrapper)
        if raw is None:
            return False
        raw.publish(channel, payload)
        return True
    except Exception:
        logger.exception("publish_json 실패")
        return False

# ---------------------------
# 안전한 키 조회 (SCAN 사용 권장)
# ---------------------------
def keys_scan(pattern: str, count: int = 100) -> Iterator[str]:
    """
    SCAN으로 안전하게 키를 반복합니다. 운영에서는 KEYS 사용 금지.
    """
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("keys_scan: redis 클라이언트 없음")
        return iter([])
    try:
        raw = _raw_client_from(wrapper)
        if raw is None:
            return iter([])
        # redis-py provides scan_iter convenience
        try:
            for k in raw.scan_iter(match=pattern, count=count):
                yield k
            return
        except Exception:
            cursor = 0
            while True:
                cursor, data = raw.scan(cursor=cursor, match=pattern, count=count)
                for k in data:
                    yield k
                if int(cursor) == 0:
                    break
    except Exception:
        logger.exception("keys_scan 실패")
        return iter([])

def keys_list(pattern: str, limit: Optional[int] = 1000) -> List[str]:
    """keys_scan의 리스트 결과 (limit로 상한 지정)."""
    out: List[str] = []
    try:
        for k in keys_scan(pattern):
            out.append(k)
            if limit and len(out) >= limit:
                break
    except Exception:
        logger.exception("keys_list 실패")
    return out

# ---------------------------
# 유틸/진단
# ---------------------------
def info_summary() -> Dict[str, Any]:
    """INFO 명령 결과를 반환(부분 요약)."""
    wrapper = _ensure_wrapper()
    if wrapper is None:
        logger.error("info_summary: redis 클라이언트 없음")
        return {}
    try:
        raw = _raw_client_from(wrapper)
        if raw is None:
            return {}
        info = raw.info()
        summary = {
            "redis_version": info.get("redis_version"),
            "used_memory_human": info.get("used_memory_human"),
            "total_keys": None,
            "role": info.get("role"),
            "cluster_enabled": info.get("cluster_enabled"),
        }
        # keyspace 요약이 dict 형태로 올 경우 간단 합산
        ks = info.get("keyspace")
        if isinstance(ks, dict):
            try:
                total = 0
                for _, v in ks.items():
                    if isinstance(v, dict):
                        total += int(v.get("keys", 0))
                summary["total_keys"] = total
            except Exception:
                summary["total_keys"] = None
        return summary
    except Exception:
        logger.exception("info_summary 실패")
        return {}

def test_pubsub(channel: str = "test.channel", message: str = "hello") -> bool:
    """간단 퍼블리시 테스트(연결 없으면 자동 연결 시도)."""
    return publish_json(channel, message)

# ---------------------------
# 모듈 자체 테스트 헬퍼 (개발용)
# ---------------------------
def self_test() -> Dict[str, Any]:
    """
    간단한 연결/요약 테스트를 수행하고 결과를 반환합니다.
    반환: dict (연결상태, 요약)
    """
    out: Dict[str, Any] = {"ok": False}
    try:
        wrapper = _ensure_wrapper()
        if not wrapper:
            out["error"] = "no_client"
            return out
        ping_ok = False
        try:
            if hasattr(wrapper, "ping"):
                ping_ok = bool(wrapper.ping())
            else:
                raw = _raw_client_from(wrapper)
                ping_ok = bool(raw.ping())
        except Exception:
            ping_ok = False
        out["ok"] = ping_ok
        out["summary"] = info_summary() if ping_ok else {}
        return out
    except Exception:
        logger.exception("self_test 실패")
        return {"ok": False, "error": "exception"}
