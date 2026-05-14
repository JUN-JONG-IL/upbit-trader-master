# -*- coding: utf-8 -*-
r"""
Gap 상태 HTTP API (PoC) — /health 엔드포인트 추가판

목적:
- gap_fill_queue의 상태 조회 API를 제공.
- 추가: /health 엔드포인트로 Redis/Timescale 접속 상태를 신속히 확인 가능.
- 운영: 인증/로깅/타임아웃/모니터링 보강 필요.

사용법(개발/검증용):
    cd C:\Users\jji24\anaconda3\envs\py311\trade\upbit-trader-master
    python -m src.data_01.gap.status_api --host 127.0.0.1 --port 8080 --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "postgresql://postgres:postgres@localhost:58529/upbit_trader"

엔드포인트:
- GET /health  -> {"status":"ok","redis":true,"timescale":true, "detail":{...}}
- GET /status?limit=10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, List, Optional

from aiohttp import web  # type: ignore
import orjson  # type: ignore

logger = logging.getLogger("gap.status_api")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_ZSET_KEY = os.environ.get("GAP_ZSET_KEY", "gap_fill_queue")


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[3] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_sa", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


# ---------------------------
# 데이터 소스 헬퍼 (생성은 on_startup에서 수행)
# ---------------------------
async def create_redis_client(redis_url: str):
    """redis.asyncio 클라이언트 생성 (실제 생성은 aiohttp 루프 내 on_startup에서 호출)"""
    try:
        import redis.asyncio as redis  # type: ignore
    except Exception:
        logger.error("redis.asyncio 필요: pip install redis")
        raise
    client = redis.from_url(redis_url, decode_responses=False)
    await client.ping()
    return client


async def create_timescale_pool(dsn: Optional[str]):
    """asyncpg pool 생성 (dsn 없으면 None 반환)"""
    if not dsn:
        return None
    try:
        import asyncpg  # type: ignore
    except Exception:
        logger.error("asyncpg 필요: pip install asyncpg")
        raise
    pool = await asyncpg.create_pool(dsn)
    return pool


async def fetch_zset_top(redis_client: Any, zset_key: str, limit: int) -> List[tuple]:
    """ZSET 상위(limit) 항목 조회 (score 내림차순)"""
    items = await redis_client.zrevrange(zset_key, 0, limit - 1, withscores=True)
    out = []
    for member, score in items:
        if isinstance(member, (bytes, bytearray)):
            member = member.decode("utf-8")
        out.append((member, float(score)))
    return out


async def count_by_tradeid(pool: Any, job_id: str) -> Optional[int]:
    """trade_id 패턴으로 백필 행 수 집계"""
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) AS cnt FROM market_ticks WHERE trade_id LIKE $1",
                f"backfill-{job_id}-%",
            )
            return int(row["cnt"]) if row and "cnt" in row else 0
    except Exception:
        logger.exception("count_by_tradeid 예외")
        return None


async def count_by_window(pool: Any, symbol: str, start_iso: str, end_iso: str) -> Optional[int]:
    """심볼 + 시간 창으로 백필된 행 수 집계"""
    if pool is None:
        return None
    try:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
    except Exception:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT count(*) AS cnt
                FROM market_ticks
                WHERE symbol = $1
                  AND exchange_ts >= $2
                  AND exchange_ts <= $3
                """,
                symbol,
                start_dt,
                end_dt,
            )
            return int(row["cnt"]) if row and "cnt" in row else 0
    except Exception:
        logger.exception("count_by_window 예외")
        return None


# ---------------------------
# HTTP 핸들러
# ---------------------------
class AppState:
    def __init__(self):
        self.redis = None
        self.pool = None
        self.zset_key = DEFAULT_ZSET_KEY


async def status_handler(request: web.Request):
    """
    GET /status?limit=10
    """
    app_state: AppState = request.app["state"]
    params = request.rel_url.query
    try:
        limit = int(params.get("limit", "10"))
    except Exception:
        limit = 10

    if app_state.redis is None:
        return web.json_response({"error": "redis not connected"}, status=500)

    try:
        items = await fetch_zset_top(app_state.redis, app_state.zset_key, limit)
    except Exception as e:
        logger.exception("Redis 조회 중 예외")
        return web.json_response({"error": "redis query failed", "detail": str(e)}, status=500)

    out_items = []
    for member_str, score in items:
        try:
            gap_obj = orjson.loads(member_str)
        except Exception:
            try:
                gap_obj = json.loads(member_str)
            except Exception:
                gap_obj = {"raw": member_str}

        job_id = gap_obj.get("job_id") or ""
        symbol = gap_obj.get("symbol")
        start_iso = gap_obj.get("start")
        end_iso = gap_obj.get("end")

        tradeid_cnt = None
        window_cnt = None
        if job_id and app_state.pool is not None:
            tradeid_cnt = await count_by_tradeid(app_state.pool, job_id)
        if symbol and start_iso and end_iso and app_state.pool is not None:
            window_cnt = await count_by_window(app_state.pool, symbol, start_iso, end_iso)

        out_items.append(
            {
                "symbol": symbol,
                "job_id": job_id,
                "gap_seconds": gap_obj.get("gap_size_seconds"),
                "score": score,
                "attempts": gap_obj.get("attempts"),
                "count_by_tradeid": tradeid_cnt,
                "count_by_window": window_cnt,
                "start": start_iso,
                "end": end_iso,
                "raw": gap_obj,
            }
        )

    return web.json_response({"items": out_items}, status=200, dumps=lambda x: orjson.dumps(x).decode("utf-8"))


async def health_handler(request: web.Request):
    """
    GET /health
    가벼운 헬스체크: Redis ping, Timescale 연결 가능 여부를 빠르게 반환.
    DB 집계/쿼리는 하지 않음(빠른 응답 목적).
    """
    app_state: AppState = request.app["state"]
    result = {"status": "ok", "redis": False, "timescale": None, "detail": {}}

    # Redis 연결 체크 (빠르게 ping)
    try:
        if app_state.redis is not None:
            # ping may return True or b'PONG' depending on client
            pong = await asyncio.wait_for(app_state.redis.ping(), timeout=1.0)
            result["redis"] = bool(pong)
        else:
            result["redis"] = False
    except Exception as e:
        result["redis"] = False
        result["detail"]["redis_error"] = str(e)

    # Timescale / Postgres 연결 체크: 가벼운 select 1
    try:
        if app_state.pool is not None:
            async with app_state.pool.acquire() as conn:
                row = await asyncio.wait_for(conn.fetchrow("SELECT 1 AS ok"), timeout=2.0)
                result["timescale"] = bool(row and row.get("ok") == 1)
        else:
            result["timescale"] = None
    except Exception as e:
        result["timescale"] = False
        result["detail"]["timescale_error"] = str(e)

    # overall status
    if not result["redis"] or (result["timescale"] is False):
        result["status"] = "degraded"
        return web.json_response(result, status=503)
    return web.json_response(result, status=200)


# ---------------------------
# 서버 런처: on_startup / on_cleanup 훅 사용
# ---------------------------
async def on_startup(app: web.Application, redis_url: str, timescale_dsn: Optional[str], zset_key: str):
    """
    aiohttp 서버 루프에서 호출되는 startup 훅.
    """
    state: AppState = app["state"]
    state.zset_key = zset_key
    try:
        state.redis = await create_redis_client(redis_url)
        logger.info("[status_api] Redis 연결 성공")
    except Exception:
        logger.exception("[status_api] Redis 연결 실패")
        state.redis = None

    try:
        state.pool = await create_timescale_pool(timescale_dsn) if timescale_dsn else None
        if state.pool is not None:
            logger.info("[status_api] Timescale pool 생성 성공")
    except Exception:
        logger.exception("[status_api] Timescale pool 생성 실패")
        state.pool = None


async def on_cleanup(app: web.Application):
    """서버 종료 시 리소스 정리"""
    state: AppState = app["state"]
    try:
        if state.redis is not None:
            if hasattr(state.redis, "aclose"):
                res = state.redis.aclose()
                if asyncio.iscoroutine(res):
                    await res
            elif hasattr(state.redis, "close"):
                res = state.redis.close()
                if asyncio.iscoroutine(res):
                    await res
            logger.info("[status_api] Redis 연결 종료")
    except Exception:
        logger.exception("[status_api] Redis 종료 중 예외")

    try:
        if state.pool is not None:
            await state.pool.close()
            logger.info("[status_api] Timescale pool 종료")
    except Exception:
        logger.exception("[status_api] pool 종료 중 예외")


def create_app():
    app = web.Application()
    app["state"] = AppState()
    app.add_routes([web.get("/status", status_handler), web.get("/health", health_handler)])
    return app


def parse_args():
    p = argparse.ArgumentParser(description="Gap Status HTTP API (PoC)")
    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--redis-url", type=str, default=os.environ.get("REDIS_URL") or _get_default_redis_url())
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""))
    p.add_argument("--zset-key", type=str, default=os.environ.get("GAP_ZSET_KEY", DEFAULT_ZSET_KEY))
    return p.parse_args()


def main():
    args = parse_args()
    app = create_app()
    app.on_startup.append(lambda app: on_startup(app, args.redis_url, args.timescale_dsn or None, args.zset_key))
    app.on_cleanup.append(on_cleanup)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()