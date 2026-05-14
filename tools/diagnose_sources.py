# -*- coding: utf-8 -*-
"""
진단 스크립트: MongoDB metadata, Redis gap queue 상태 점검 및 enqueue_all의 dry-run 확인
사용법:
  - 기본(비파괴): python tools/diagnose_sources.py
  - 실제 1개 심볼 enqueue 테스트: python tools/diagnose_sources.py --do-enqueue --limit 1
환경변수:
  - REDIS_URL, MONGO_URI 등은 환경변수로 지정 가능
"""
import argparse
import os
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--do-enqueue", action="store_true", help="실제 Redis에 등록(테스트용 제한 권장)")
    p.add_argument("--limit", type=int, default=10, help="샘플 심볼 수 (diagnose)")
    args = p.parse_args()

    print("환경값: REDIS_URL=%s" % os.getenv("REDIS_URL", "redis://:dummy@127.0.0.1:58530/0"))
    print("환경값: MONGO_URI=%s" % os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader"))

    # 1) Mongo 확인
    try:
        from pymongo import MongoClient
        client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader"), serverSelectionTimeoutMS=3000)
        db = client.get_default_database() or client.get_database("upbit_trader")
        print("Mongo DB:", db.name)
        colnames = db.list_collection_names()
        print("Collections:", colnames)
        if "metadata" in colnames:
            coll = db["metadata"]
            cnt = coll.count_documents({})
            print("metadata count:", cnt)
            sample = list(coll.find({}, {"symbol": 1}).limit(args.limit))
            print("sample symbols:", [d.get("symbol") for d in sample])
        else:
            print("metadata 컬렉션 없음")
    except Exception as e:
        print("Mongo 연결 실패:", e)

    # 2) Redis 확인
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://:dummy@127.0.0.1:58530/0"), decode_responses=True)
        zcard = r.zcard(os.getenv("GAP_QUEUE", "gap_fill_queue"))
        print("Redis gap_fill_queue size:", zcard)
        sample = r.zrange(os.getenv("GAP_QUEUE", "gap_fill_queue"), 0, 10, withscores=True)
        print("gap_fill_queue sample count:", len(sample))
    except Exception as e:
        print("Redis 연결 실패:", e)

    # 3) enqueue_all dry-run
    print("\n-> enqueue_all dry-run (상위 %d 심볼)" % args.limit)
    try:
        import importlib
        mod = importlib.import_module("src.14_orchestrator.enqueue_all")
        cnt = mod.enqueue_all_symbols(dry_run=True, max_symbols=args.limit)
        print("dry-run 시도 심볼 수:", cnt)
        if args.do_enqueue:
            print("실제 enqueue 수행 (limit=%d)..." % args.limit)
            cnt2 = mod.enqueue_all_symbols(dry_run=False, max_symbols=args.limit)
            print("실제 등록 완료:", cnt2)
    except Exception as e:
        print("enqueue_all 모듈 호출 실패:", e)

if __name__ == "__main__":
    main()