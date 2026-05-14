#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 통합 self-test 스크립트
- 목적: 레포의 Redis 계층(redis_client, redis_db, cache_manager, cluster_manager, sentinel_manager)을
  한 번에 로드하여 통합 동작을 확인합니다.
- 실행: Python 3.8+ 권장. (PowerShell 예시는 하단에 있음)
- 비고: 로컬 환경에 Redis가 없거나 Sentinel/Cluster 구성되지 않은 경우에도
  가능한 범위에서 결과를 출력하고 실패는 로그로 남깁니다.
"""
from __future__ import annotations

import importlib.util
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]  # repo root (tools/... -> parents[3] -> repo root)
SRC = ROOT / "src" / "02_data" / "redis"
TS_SRC = ROOT / "src" / "02_data" / "timescale"

def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def safe_json(obj: Any):
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)
    except Exception:
        return str(obj)

async def run_tests():
    results: Dict[str, Any] = {}

    # 1) load redis_client
    try:
        rc_mod = load_module_from_path("redis_client_local", SRC / "redis_client.py")
        results["redis_client_loaded"] = True
    except Exception as exc:
        results["redis_client_loaded"] = False
        results["redis_client_error"] = str(exc)
        print("redis_client 로드 실패:", exc)
        # Without redis_client many tests will be skipped but continue to attempt direct modules.

    # 2) test get_redis_client / ping
    try:
        get_client = getattr(rc_mod, "get_redis_client")
        client_wrapper = get_client(use_cached=True)
        ping_ok = False
        try:
            ping_ok = bool(client_wrapper.ping())
        except Exception:
            # some wrappers expose underlying client
            try:
                raw = getattr(client_wrapper, "_client", None) or getattr(client_wrapper, "client", None) or client_wrapper
                ping_ok = bool(raw.ping())
            except Exception:
                ping_ok = False
        results["ping"] = ping_ok
    except Exception as exc:
        results["ping_error"] = str(exc)

    # 3) load redis_db and run self_test() if present
    try:
        rdb_mod = load_module_from_path("redis_db_local", SRC / "redis_db.py")
        if hasattr(rdb_mod, "self_test"):
            ok, summary = rdb_mod.self_test()
            results["redis_db_self_test_ok"] = ok
            results["redis_db_summary"] = summary
        else:
            results["redis_db_self_test_ok"] = None
    except Exception as exc:
        results["redis_db_error"] = str(exc)

    # 4) load cache_manager and run basic push/get/invalidate tests
    try:
        cm_mod = load_module_from_path("cache_manager_local", SRC / "cache_manager.py")
        # use client_wrapper if available
        client_for_cache = locals().get("client_wrapper", None)
        cm = cm_mod.CacheManager(client=client_for_cache)
        # run async tests
        async def cache_ops():
            out = {}
            try:
                # push trade
                ok = await cm.push_trade("TEST-SYMBOL", {"price": 1234, "qty": 1, "ts": 1234567890})
                out["push_trade_ok"] = ok
                trades = await cm.get_trades("TEST-SYMBOL", limit=5)
                out["trades_sample"] = trades
                # push candle
                c_ok = await cm.push_candle("TEST-SYMBOL", "1m", {"time": 1234567890, "open":1, "close":2})
                out["push_candle_ok"] = c_ok
                candles = await cm.get_candles("TEST-SYMBOL", "1m", limit=5)
                out["candles_sample"] = candles
                # set/get orderbook
                ob_ok = await cm.set_orderbook("TEST-SYMBOL", {"ask":"100","bid":"99"})
                out["set_orderbook_ok"] = ob_ok
                ob = await cm.get_orderbook("TEST-SYMBOL")
                out["orderbook"] = ob
                # invalidate
                await cm.invalidate("TEST-SYMBOL")
            except Exception as e:
                out["error"] = str(e)
            return out

        cache_res = await cache_ops()
        results["cache_manager"] = cache_res
    except Exception as exc:
        results["cache_manager_error"] = str(exc)

    # 5) cluster_manager.get_cluster_nodes
    try:
        cmgr_mod = load_module_from_path("cluster_manager_local", SRC / "cluster_manager.py")
        try:
            nodes = cmgr_mod.get_cluster_nodes(host="localhost", port=6379)
            results["cluster_nodes"] = nodes
        except Exception as exc:
            results["cluster_nodes_error"] = str(exc)
    except Exception as exc:
        results["cluster_manager_error"] = str(exc)

    # 6) sentinel_manager tests (async)
    try:
        sm_mod = load_module_from_path("sentinel_manager_local", SRC / "sentinel_manager.py")
        # create manager for localhost sentinel default port
        mgr = sm_mod.SentinelManager([("localhost", 6379)], master_name="mymaster")
        async def sentinel_ops():
            out = {}
            try:
                await mgr.connect()
                out["master_info"] = await mgr.master_info()
                out["slaves_info"] = await mgr.slaves_info()
                out["sentinels_info"] = await mgr.sentinels_info()
                out["failover_attempt"] = await mgr.failover()
                await mgr.close()
            except Exception as e:
                out["error"] = str(e)
            return out
        sen_res = await sentinel_ops()
        results["sentinel_manager"] = sen_res
    except Exception as exc:
        results["sentinel_manager_error"] = str(exc)

    # print summarized JSON
    print("=== REDIS INTEGRATION SELF TEST RESULT ===")
    print(safe_json(results))

if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except Exception as e:
        print("실행 중 예외:", e)
        sys.exit(1)
