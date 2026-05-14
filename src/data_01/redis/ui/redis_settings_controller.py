#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis settings controller (UI-agnostic backend helpers)

- 제공 함수:
  - get_client(timeout=2)
  - get_status() -> dict (ping, info summary)
  - list_pubsub_channels() -> List[str]
  - get_gap_queue_preview(queue=DEFAULT_QUEUE, n=200) -> List[str]
  - get_sortedset_top(zset, n=100) -> List[(member, score)]
  - get_l1_expiring_keys(prefix='l1:', limit=500) -> List[(key, ttl)]
  - clear_queue(queue, backup=True) -> dict(result, backup_key or error)
  - clear_keys_by_prefix(prefix, limit=1000, dry_run=True) -> dict(summary, deleted_count)
- 안전성: 작업(삭제 등)은 UI에서 반드시 확인/권한 체크 후 호출하세요.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import time
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------
# Robust dynamic loader for timescale_redis
# ------------------------------
def _load_module_from_path(path: Path, mod_name: str) -> Optional[Any]:
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return mod
    except Exception:
        return None

def _find_timescale_mod() -> Optional[Any]:
    """
    여러 방식으로 timescale_redis 모듈을 찾아 로드합니다.
    1) 흔한 import 이름 시도
    2) 소스 트리 내 후보 경로 검색
    3) 환경변수 TIMESCALE_REDIS_PATH에 지정된 경로 사용
    4) sys.modules에 이미 로드된 모듈 검색
    """
    candidates_names = [
        "src.data_01.timescale.timescale_redis",
        "timescale_redis",
        "src._data_01.timescale.timescale_redis",
        "src.data_01.timescale",
    ]
    for name in candidates_names:
        try:
            mod = importlib.import_module(name)
            return mod
        except Exception:
            continue

    # search repo-relative paths up from this file
    here = Path(__file__).resolve()
    for base in here.parents:
        paths = [
            base / "src" / "data_01" / "timescale" / "timescale_redis.py",
            base / "src" / "data_01" / "timescale_redis.py",
            base / "data_01" / "timescale" / "timescale_redis.py",
            base / "src" / "_data_01" / "timescale" / "timescale_redis.py",
            here.parents[2] / "timescale" / "timescale_redis.py",
        ]
        for p in paths:
            if p.exists():
                mod = _load_module_from_path(p, "timescale_redis")
                if mod:
                    return mod

    env = os.getenv("TIMESCALE_REDIS_PATH")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            mod = _load_module_from_path(p, "timescale_redis")
            if mod:
                return mod

    # final fallback: any loaded module that endswith timescale_redis
    for name, mod in list(sys.modules.items()):
        if name.endswith("timescale_redis"):
            return mod

    return None

_timescale_mod = _find_timescale_mod()

# ------------------------------
# Shim: 모듈이 없을 때 안전한 동작을 보장하는 경량 래퍼
# ------------------------------
class _Shim:
    def get_client(self, timeout: int = 2):
        return None
    def get_status(self, timeout: int = 2):
        return {"client": False, "ping": False, "info": {}, "error": "shim"}
    def list_pubsub_channels(self, client=None):
        return []
    def get_gap_queue_preview(self, queue="gap_fill_queue", n=200):
        return []
    def get_sortedset_top(self, client, zset, n=100):
        return []
    def get_l1_expiring_keys(self, client, prefix="l1:"):
        return []
    def clear_queue(self, client, queue, backup=True):
        return {"ok": False, "error": "shim"}
    def clear_keys_by_prefix(self, client, prefix, limit=1000, dry_run=True):
        return {"ok": False, "error": "shim"}

if _timescale_mod is None:
    _timescale_mod = _Shim()

# DEFAULT_QUEUE: 모듈에서 가져오거나 폴백
DEFAULT_QUEUE = getattr(_timescale_mod, "DEFAULT_QUEUE", "gap_fill_queue")
_DEFAULT_PUBSUB_SET = os.getenv("PUBSUB_CHANNELS_SET", "pubsub:channels")

# ------------------------------
# Helper: bytes -> str 안전 변환
# ------------------------------
def _ensure_str(v: Any) -> str:
    try:
        if isinstance(v, (bytes, bytearray)):
            return v.decode("utf-8", errors="replace")
        return str(v)
    except Exception:
        return str(v)

# ------------------------------
# 공개 함수들
# ------------------------------
def get_client(timeout: int = 2) -> Optional[Any]:
    """Return redis client (or None)."""
    try:
        return _timescale_mod.get_client(timeout=timeout)
    except Exception:
        return None

def get_status(timeout: int = 2) -> Dict[str, Any]:
    """
    Return basic Redis/connect status:
      { "client": bool, "ping": bool, "info": {selected keys}, "error": str|None }
    """
    try:
        # if module provides get_status, prefer that
        if hasattr(_timescale_mod, "get_status"):
            return _timescale_mod.get_status(timeout=timeout)
    except Exception:
        pass

    client = get_client(timeout=timeout)
    out: Dict[str, Any] = {"client": bool(client), "ping": False, "info": {}, "error": None}
    if not client:
        out["error"] = "no redis client"
        return out
    try:
        out["ping"] = bool(client.ping())
    except Exception as e:
        out["error"] = f"ping failed: {e}"
    try:
        info = client.info()
        keys = ["redis_version", "role", "connected_clients", "used_memory_human", "uptime_in_seconds"]
        out["info"] = {k: info.get(k) for k in keys if k in info}
    except Exception:
        out["info"] = {}
    return out

def list_pubsub_channels() -> List[str]:
    """
    Return known channels from registry set; falls back to timescale_redis.list_pubsub_channels.
    """
    try:
        client = get_client()
        # module-level helper may expect client or not; try both
        try:
            return list(_timescale_mod.list_pubsub_channels(client))
        except TypeError:
            return list(_timescale_mod.list_pubsub_channels())
    except Exception:
        return []

def get_gap_queue_preview(queue: str = DEFAULT_QUEUE, n: int = 200) -> List[str]:
    """
    Preview top n items from a list-style queue (LRANGE 0 n-1).
    Returns decoded JSON strings or raw strings.
    """
    client = get_client()
    if not client:
        return _timescale_mod.get_gap_queue_preview(queue, n) if hasattr(_timescale_mod, "get_gap_queue_preview") else []
    try:
        raw = client.lrange(queue, 0, n - 1)
        out: List[str] = []
        for item in raw:
            try:
                s = _ensure_str(item)
                # try json pretty
                try:
                    parsed = json.loads(s)
                    out.append(json.dumps(parsed, ensure_ascii=False))
                except Exception:
                    out.append(s)
            except Exception:
                out.append(str(item))
        return out
    except Exception:
        # fallback to zrevrange (maybe it's a zset)
        try:
            items = client.zrevrange(queue, 0, n - 1, withscores=False)
            return [_ensure_str(x) for x in items]
        except Exception:
            return []

def get_sortedset_top(zset: str, n: int = 100) -> List[Tuple[str, float]]:
    client = get_client()
    if not client:
        return _timescale_mod.get_sortedset_top(zset, n) if hasattr(_timescale_mod, "get_sortedset_top") else []
    try:
        items = client.zrevrange(zset, 0, n - 1, withscores=True)
        out: List[Tuple[str, float]] = []
        for k, v in items:
            try:
                key = _ensure_str(k)
                score = float(v) if v is not None else 0.0
                out.append((key, score))
            except Exception:
                out.append((_ensure_str(k), 0.0))
        return out
    except Exception:
        return []

def get_l1_expiring_keys(prefix: str = "l1:", limit: int = 500) -> List[Tuple[str, int]]:
    client = get_client()
    if not client:
        # delegate to module if available
        try:
            return _timescale_mod.get_l1_expiring_keys(client, prefix=prefix)
        except Exception:
            return []
    try:
        results: List[Tuple[str, int]] = []
        pattern = f"{prefix}*"
        if hasattr(client, "scan_iter"):
            for key in client.scan_iter(match=pattern, count=200):
                try:
                    key_str = _ensure_str(key)
                except Exception:
                    key_str = str(key)
                try:
                    ttl = client.ttl(key)
                except Exception:
                    ttl = -1
                results.append((key_str, int(ttl if ttl is not None else -1)))
                if len(results) >= limit:
                    break
        else:
            keys = client.keys(pattern)
            for key in keys[:limit]:
                key_str = _ensure_str(key)
                try:
                    ttl = client.ttl(key)
                except Exception:
                    ttl = -1
                results.append((key_str, int(ttl if ttl is not None else -1)))
        results.sort(key=lambda x: (x[1] if x[1] >= 0 else 10**12))
        return results
    except Exception:
        return []

def clear_queue(queue: str = DEFAULT_QUEUE, backup: bool = True) -> Dict[str, Any]:
    """
    Clear a list or zset queue.
    If backup=True, rename to backup:key:ts and DO NOT delete the backup (so operator can inspect).
    Returns dict with 'ok' bool and 'backup' or 'deleted' info or 'error'.
    """
    client = get_client()
    if not client:
        return {"ok": False, "error": "no redis client"}
    ts = int(time.time())
    try:
        if backup:
            backup_key = f"backup:{queue}:{ts}"
            try:
                client.rename(queue, backup_key)
            except Exception:
                try:
                    client.delete(backup_key)
                    client.rename(queue, backup_key)
                except Exception as e:
                    return {"ok": False, "error": f"rename failed: {e}"}
            return {"ok": True, "backup": backup_key}
        else:
            client.delete(queue)
            return {"ok": True, "deleted": queue}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def clear_keys_by_prefix(prefix: str, limit: int = 1000, dry_run: bool = True) -> Dict[str, Any]:
    """
    Scan and delete keys matching prefix*.
    If dry_run=True, only count; else perform unlink/delete and return deleted count.
    WARNING: Use with care. UI must require confirmation.
    """
    client = get_client()
    if not client:
        return {"ok": False, "error": "no redis client"}
    try:
        count = 0
        deleted = 0
        for key in client.scan_iter(match=f"{prefix}*", count=200):
            count += 1
            if dry_run:
                if count >= limit:
                    break
                continue
            try:
                client.unlink(key)
                deleted += 1
            except Exception:
                try:
                    client.delete(key)
                    deleted += 1
                except Exception:
                    pass
            if deleted >= limit:
                break
        return {"ok": True, "scanned": count, "deleted": deleted, "dry_run": bool(dry_run)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Lightweight test helpers (callable from CLI)
def _self_test():
    print("get_status:", json.dumps(get_status(), ensure_ascii=False))
    print("list_pubsub_channels:", json.dumps(list_pubsub_channels()[:50], ensure_ascii=False))
    print("gap_preview:", json.dumps(get_gap_queue_preview(DEFAULT_QUEUE, n=10), ensure_ascii=False))
    print("l1_expiring:", json.dumps(get_l1_expiring_keys("l1:", limit=20), ensure_ascii=False))

if __name__ == "__main__":
    _self_test()