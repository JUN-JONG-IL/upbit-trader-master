#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_redis_pubsub.py

간단 진단:
- SMEMBERS pubsub:channels (채널 레지스트리)
- PUBSUB NUMSUB <channels...> (구독자 수)
- KEYS patterns (ticker:, market.ticker:, l1:) 샘플
- LLEN / ZCARD gap_fill_queue
- 일부 L1 키 TTL 샘플

사용:
  python tools/diagnose_redis_pubsub.py
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

# Try to import local timescale_redis loader (project layout)
tsr = None
try:
    import timescale_redis as tsr  # type: ignore
except Exception:
    # try relative project path
    repo_root = Path(__file__).resolve().parents[1]  # repo/tools -> repo
    candidates = [
        repo_root / "src" / "data_01" / "timescale" / "timescale_redis.py",
        repo_root / "src" / "data_01" / "timescale_redis.py",
        repo_root / "src" / "data_01" / "redis" / "timescale_redis.py",
    ]
    for c in candidates:
        if c.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("timescale_redis_diag", str(c))
            mod = importlib.util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(mod)  # type: ignore
            tsr = mod
            break

# fallback to redis library directly if timescale_redis not available
redis_client = None
if tsr:
    try:
        redis_client = tsr.get_client()
    except Exception:
        redis_client = None

if redis_client is None:
    try:
        import redis
        # try env REDIS_URL or host/port
        url = os.getenv("REDIS_URL")
        if url:
            redis_client = redis.from_url(url, decode_responses=True)
        else:
            host = os.getenv("REDIS_HOST", "127.0.0.1")
            port = int(os.getenv("REDIS_PORT", "6379"))
            pwd = os.getenv("REDIS_PASSWORD", None)
            redis_client = redis.Redis(host=host, port=port, password=pwd, decode_responses=True)
    except Exception as exc:
        print("Cannot create redis client:", exc, file=sys.stderr)
        sys.exit(2)

def safe(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        return f"ERROR: {e}"

def main():
    cli = redis_client
    print("Redis diagnostic")
    try:
        print("PING:", safe(cli.ping))
    except Exception:
        pass

    # 1) pubsub registry (SMEMBERS)
    setname = os.getenv("PUBSUB_CHANNELS_SET", "pubsub:channels")
    print("\nSMEMBERS", setname)
    members = safe(cli.smembers, setname)
    if isinstance(members, (set, list)):
        members = list(members)
    print("->", json.dumps(members, ensure_ascii=False, indent=2))

    # 2) PUBSUB NUMSUB for members (if any)
    if members:
        try:
            raw = safe(cli.pubsub_numsub, *members)
        except TypeError:
            raw = safe(cli.pubsub_numsub, members)
        print("\nPUBSUB NUMSUB raw:", raw)
    else:
        print("\nPUBSUB NUMSUB: no members to query")

    # 3) show keys count for patterns
    patterns = ["market.ticker.*", "ticker:*", "l1:*"]
    for p in patterns:
        try:
            count = 0
            sample = []
            it = cli.scan_iter(match=p, count=200)
            for i, k in enumerate(it):
                if i < 20:
                    sample.append(k)
                count += 1
                if count >= 1000:
                    break
            print(f"\nPattern {p}: approx_count(scanned)={count}, sample(<=20)={sample}")
        except Exception as e:
            print(f"\nPattern {p} scan error: {e}")

    # 4) gap_fill_queue status
    q = os.getenv("TIMESCALE_REDIS_QUEUE", "gap_fill_queue")
    try:
        llen = safe(cli.llen, q)
        zcard = safe(cli.zcard, q)
        print(f"\nQueue '{q}': LLEN={llen}, ZCARD={zcard}")
        if isinstance(llen, int) and llen > 0:
            sample = safe(cli.lrange, q, 0, 9)
            print("LRANGE 0..9:", sample)
    except Exception as e:
        print("Queue check error:", e)

    # 5) show pubsub:channels content TTL? (sets do not have TTL)
    try:
        ttl = safe(cli.ttl, setname)
        print(f"\nTTL of {setname} (should be -1 for no expiry): {ttl}")
    except Exception:
        pass

    print("\nDone. If you want, paste this output here and I will analyze next steps.")

if __name__ == "__main__":
    main()

