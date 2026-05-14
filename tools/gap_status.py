# -*- coding: utf-8 -*-
r"""
gap 상태 점검 도구 (PowerShell 친화적)

기능:
- Redis ZSET(gap_fill_queue)의 상위 N개 항목을 조회하여 job_id, symbol, gap_seconds, score 요약 출력
- 각 job에 대해 두 가지 방식으로 백필 진행 상태를 조회:
  1) trade_id 패턴(backfill-{job_id}-% ) 기반 행 수
  2) 심볼 + 시간 범위(start..end) 기반 행 수 (실제 백필된 레코드가 시간 윈도우에 들어왔는지 확인)
- async 기반으로 redis.asyncio와 asyncpg 사용 (환경에 asyncpg/redis.asyncio 필요)
- 사용 예 (PowerShell):
    cd C:\Users\jji24\anaconda3\envs\py311\trade\upbit-trader-master
    python -m tools.gap_status --redis-url "redis://:dummy@127.0.0.1:58530/0" --timescale-dsn "postgresql://postgres:postgres@127.0.0.1:58529/upbit_trader" --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from datetime import datetime
from typing import Any, List, Optional

import orjson  # type: ignore

DEFAULT_ZSET_KEY = "gap_fill_queue"


async def _create_redis(redis_url: str):
    try:
        import redis.asyncio as redis  # type: ignore
    except Exception as e:
        print("[error] redis.asyncio 모듈 ��요: pip install redis >= 4.2.0", file=sys.stderr)
        raise e
    client = redis.from_url(redis_url, decode_responses=False)
    await client.ping()
    return client


async def _create_pool(dsn: Optional[str]):
    if not dsn:
        return None
    try:
        import asyncpg  # type: ignore
    except Exception as e:
        print("[warning] asyncpg 미설치 - Timescale 조회 비활성", file=sys.stderr)
        raise e
    pool = await asyncpg.create_pool(dsn)
    return pool


async def _fetch_zset_top(redis_client: Any, zset_key: str, limit: int) -> List[tuple]:
    """
    ZSET에서 상위(limit) 항목을 가져옴 (score 높은순)
    반환: list of (member_str, score_float)
    """
    items = await redis_client.zrevrange(zset_key, 0, limit - 1, withscores=True)
    out = []
    for member, score in items:
        if isinstance(member, (bytes, bytearray)):
            member = member.decode("utf-8")
        out.append((member, float(score)))
    return out


async def _count_backfill_rows_by_tradeid(pool: Any, job_id: str) -> Optional[int]:
    """
    market_ticks에서 backfill-{job_id}-% 로 시작하는 trade_id 개수 조회
    None 반환 시 DB 미연결
    """
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
        return None


async def _count_backfill_rows_by_window(pool: Any, symbol: str, start_iso: str, end_iso: str) -> Optional[int]:
    """
    심볼 + 시간 범위(start_iso, end_iso)로 market_ticks에 들어온 행 수 집계
    - start_iso/end_iso: ISO 포맷 문자열 (타임존 포함 가능)
    - None 반환 시 DB 미연결
    """
    if pool is None:
        return None
    try:
        # datetime parsing: datetime.fromisoformat handles offset-aware strings in Python 3.11
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
    except Exception:
        # 파싱 실패시 None 반환
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
        return None


def _pretty_print_gap(idx: int, gap_obj: dict, score: float, count_by_tradeid: Optional[int], count_by_window: Optional[int]):
    print(f"[{idx}] symbol={gap_obj.get('symbol')} job_id={gap_obj.get('job_id')}")
    print(f"     gap_seconds={gap_obj.get('gap_size_seconds')} score={score:.4f} attempts={gap_obj.get('attempts')}")
    print(f"     window: {gap_obj.get('start')} -> {gap_obj.get('end')}")
    if count_by_tradeid is None:
        print("     backfill_rows (by trade_id): (DB 미연결)")
    else:
        print(f"     backfill_rows (by trade_id): {count_by_tradeid}")
    if count_by_window is None:
        print("     backfill_rows (by window): (DB 미연결 or parse error)")
    else:
        print(f"     backfill_rows (by window): {count_by_window}")
    print("     raw metadata:", json.dumps(gap_obj, ensure_ascii=False))
    print("-" * 80)


async def main_async(redis_url: str, timescale_dsn: Optional[str], zset_key: str, limit: int):
    redis_client = None
    pool = None
    try:
        redis_client = await _create_redis(redis_url)
    except Exception as e:
        print("[error] Redis 연결 실패:", e, file=sys.stderr)
        return 1

    try:
        if timescale_dsn:
            pool = await _create_pool(timescale_dsn)
    except Exception:
        pool = None

    try:
        items = await _fetch_zset_top(redis_client, zset_key, limit)
        if not items:
            print("[info] gap ZSET 비어있음 또는 항목 없음:", zset_key)
            return 0

        for idx, (member_str, score) in enumerate(items, start=1):
            try:
                gap_obj = orjson.loads(member_str)
            except Exception:
                try:
                    gap_obj = json.loads(member_str)
                except Exception:
                    gap_obj = {"raw": member_str}

            job_id = gap_obj.get("job_id") or gap_obj.get("jobId") or ""
            count_by_tradeid = None
            count_by_window = None
            if job_id and pool is not None:
                try:
                    count_by_tradeid = await _count_backfill_rows_by_tradeid(pool, job_id)
                except Exception:
                    count_by_tradeid = None
            # 시간 창 기준 집계 (symbol+start+end)
            symbol = gap_obj.get("symbol")
            start_iso = gap_obj.get("start")
            end_iso = gap_obj.get("end")
            if symbol and start_iso and end_iso and pool is not None:
                try:
                    count_by_window = await _count_backfill_rows_by_window(pool, symbol, start_iso, end_iso)
                except Exception:
                    count_by_window = None

            _pretty_print_gap(idx, gap_obj, score, count_by_tradeid, count_by_window)
    finally:
        if redis_client is not None:
            try:
                if hasattr(redis_client, "aclose"):
                    res = redis_client.aclose()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(redis_client, "close"):
                    res = redis_client.close()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
        if pool is not None:
            try:
                await pool.close()
            except Exception:
                pass
    return 0


def parse_args():
    p = argparse.ArgumentParser(description="Gap status inspector (improved)")
    p.add_argument("--redis-url", type=str, default="redis://:dummy@127.0.0.1:58530/0")
    p.add_argument("--timescale-dsn", type=str, default="postgresql://postgres:postgres@127.0.0.1:58529/upbit_trader")
    p.add_argument("--zset-key", type=str, default=DEFAULT_ZSET_KEY)
    p.add_argument("--limit", type=int, default=10, help="상위 몇 개 항목 출력")
    return p.parse_args()


def main():
    args = parse_args()
    exit_code = asyncio.run(main_async(args.redis_url, args.timescale_dsn or None, args.zset_key, args.limit))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()