# -*- coding: utf-8 -*-
"""
enqueue_all (강화판)
- MongoDB metadata에서 심볼을 읽어 gap_fill_queue에 등록합니다.
- 상세 로깅, 예외 핸들링, dry_run 옵션 지원.
- 기본 동작은 실제 등록(dry_run=False). 테스트 시 dry_run=True 로 호출하세요.
"""
from __future__ import annotations

import os
import time
import json
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("enqueue_all")
logger.addHandler(logging.NullHandler())

# 환경변수/기본값
GAP_QUEUE = os.getenv("GAP_QUEUE", "gap_fill_queue")


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        from _01_core.database.redis_factory import get_redis_url  # type: ignore
        return get_redis_url()
    except Exception:
        pass
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[1] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_enq", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception as _e:
        logger.debug("[enqueue_all] redis_factory 로드 실패 (%s), 기본 URL 사용", _e)
        return "redis://:dummy@127.0.0.1:58530/0"


REDIS_URL = _get_default_redis_url()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
LOOKBACK_DAYS_DEFAULT = int(os.getenv("FORCE_ENQUEUE_LOOKBACK_DAYS", "3"))
PRIORITY_DEFAULT = int(os.getenv("FORCE_ENQUEUE_PRIORITY", "3"))

# Optional imports (fail gracefully)
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

try:
    import redis
except Exception:
    redis = None


def _get_symbols_from_mongo(mongo_uri: str = MONGO_URI) -> Optional[List[str]]:
    """
    MongoDB에서 metadata collection의 'symbol' 필드 목록을 반환.
    실패 시 None을 반환.
    """
    if MongoClient is None:
        logger.debug("pymongo 미설치: MongoDB에서 심볼을 가져올 수 없음")
        return None
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # try to parse db name from URI if provided; get_default_database relies on pymongo parsing
        db = client.get_default_database()
        if db is None:
            # fallback: try 'upbit_trader'
            db = client.get_database("upbit_trader")
        if "metadata" not in db.list_collection_names():
            logger.warning("MongoDB: metadata 컬렉션이 없습니다 (db=%s).", db.name)
            return []
        coll = db["metadata"]
        symbols = []
        for doc in coll.find({}, {"symbol": 1}):
            s = doc.get("symbol")
            if s:
                symbols.append(s)
        symbols = sorted(set(symbols))
        logger.info("MongoDB: metadata 심볼 수=%d (db=%s)", len(symbols), db.name)
        return symbols
    except Exception as e:
        logger.exception("MongoDB에서 심볼을 가져오는 중 예외: %s", e)
        return None


def _get_fallback_symbols() -> List[str]:
    """
    Fallback 심볼 소스: src/01_core/config/symbols.json 또는 최소 KRW-BTC
    """
    repo_root = Path(__file__).resolve().parents[2]
    cand = repo_root / "src" / "01_core" / "config" / "symbols.json"
    if cand.exists():
        try:
            return json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("fallback symbols.json 파싱 실패")
    return ["KRW-BTC"]


def enqueue_all_symbols(
    redis_url: str = REDIS_URL,
    mongo_uri: str = MONGO_URI,
    lookback_days: int = LOOKBACK_DAYS_DEFAULT,
    priority: int = PRIORITY_DEFAULT,
    dry_run: bool = False,
    max_symbols: Optional[int] = None,
) -> int:
    """
    모든 심볼을 gap_fill_queue에 등록.
    - dry_run=True 이면 실제 ZADD 하지 않고 몇 가지 샘플만 로그로 남김.
    - max_symbols: 테스트 시 일부만 처리.
    Returns number of attempted symbols (or actually added if dry_run=False).
    """
    if redis is None:
        logger.error("redis 패키지 미설치: pip install redis")
        return 0

    symbols = _get_symbols_from_mongo(mongo_uri) or _get_fallback_symbols()
    if not symbols:
        logger.warning("심볼 목록 비어있음 - 아무것도 등록하지 않음")
        return 0

    if max_symbols:
        symbols = symbols[:max_symbols]

    logger.info("enqueue_all_symbols: 준비 (symbols=%d, lookback_days=%d, dry_run=%s)", len(symbols), lookback_days, dry_run)

    now = datetime.utcnow()
    start_iso = (now - timedelta(days=int(lookback_days))).isoformat() + "Z"
    end_iso = now.isoformat() + "Z"

    r = None
    try:
        r = redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        logger.exception("Redis 연결 실패(%s): %s", redis_url, e)
        return 0

    added = 0
    errors = 0
    for i, sym in enumerate(symbols, start=1):
        job = {
            "symbol": sym,
            "timeframe": "1m",
            "start": start_iso,
            "end": end_iso,
            "gap_seconds": int((now - (now - timedelta(days=lookback_days))).total_seconds()),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        member = json.dumps(job, ensure_ascii=False)
        if dry_run:
            logger.debug("[dry-run] would ZADD %s -> %s", sym, member[:200])
            added += 1
            continue
        try:
            # Use zadd mapping API: {member: score}
            r.zadd(GAP_QUEUE, {member: int(priority)})
            added += 1
        except Exception as e:
            errors += 1
            logger.exception("Redis zadd 실패 for %s: %s", sym, e)
        # small throttle for large lists
        if i % 200 == 0:
            time.sleep(0.05)

    logger.info("enqueue_all_symbols 완료: 시도=%d, 성공=%d, 실패=%d", len(symbols), added, errors)
    return added


def maybe_enqueue_on_startup(dry_run: bool = False, max_symbols: Optional[int] = None) -> int:
    """
    앱 시작 시 호출 가능한 래퍼(환경변수로 제어 가능).
    - dry_run: 실제 큐에 넣지 않고 시뮬레이션만 함.
    """
    env_enabled = os.getenv("FORCE_ENQUEUE_ALL", "false").lower() in ("1", "true", "yes")
    if not env_enabled:
        logger.info("FORCE_ENQUEUE_ALL 비활성화 (환경변수 확인)")
        return 0
    try:
        lookback = int(os.getenv("FORCE_ENQUEUE_LOOKBACK_DAYS", str(LOOKBACK_DAYS_DEFAULT)))
    except Exception:
        lookback = LOOKBACK_DAYS_DEFAULT
    try:
        prio = int(os.getenv("FORCE_ENQUEUE_PRIORITY", str(PRIORITY_DEFAULT)))
    except Exception:
        prio = PRIORITY_DEFAULT
    # call enqueue_all_symbols
    return enqueue_all_symbols(redis_url=os.getenv("REDIS_URL", REDIS_URL), mongo_uri=os.getenv("MONGO_URI", MONGO_URI), lookback_days=lookback, priority=prio, dry_run=dry_run, max_symbols=max_symbols)
