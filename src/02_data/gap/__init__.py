# -*- coding: utf-8 -*-
"""
Timescale 테스트 스키마 & 샘플 데이터 생성기 (PoC)

목적:
- detector가 기대하는 market_ticks 테이블이 없을 때 테스트용으로 테이블을 생성합니다.
- exchange_ts를 파티셔닝 컬럼으로 사용하는 hypertable 생성 시,
  'partitioning column must be part of primary/composite key' 제약을 만족하도록
  PRIMARY KEY를 (trade_id, exchange_ts)로 정의합니다.
- 운영 환경에서는 collector가 데이터를 삽입하므로 이 스크립트는 테스트/개발 전용입니다.

사용 예:
1) 테이블만 생성:
    python -m src.02_data.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --create-only

2) 테이블 생성 + 샘플 심볼 1개 삽입(마지막 ts를 now - hours_ago):
    python -m src.02_data.gap.init_schema --timescale-dsn "postgresql://postgres:postgres@localhost:5432/upbit_trader" --seed-symbols "KRW-BTC" --hours-ago 48

주의:
- 이 스크립트는 ���발용이며, 운영 DB에 실행하기 전 DSN을 반드시 확인하세요.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

logger = logging.getLogger("gap.init_schema")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(ch)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


# 테이블 생성 DDL: PRIMARY KEY를 (trade_id, exchange_ts)로 하여 hypertable 제약 충족
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_ticks (
  trade_id TEXT NOT NULL,
  exchange_ts TIMESTAMPTZ NOT NULL,
  symbol TEXT NOT NULL,
  price NUMERIC,
  qty NUMERIC,
  side TEXT,
  ingest_ts TIMESTAMPTZ DEFAULT now(),
  trace_id TEXT,
  PRIMARY KEY (trade_id, exchange_ts)
);
"""

# hypertable 생성 SQL (Timescale가 설치되어 있으면 실행)
CREATE_HYPERTABLE_SQL = "SELECT create_hypertable('market_ticks', 'exchange_ts', if_not_exists => TRUE);"

INSERT_SAMPLE_SQL = """
INSERT INTO market_ticks (trade_id, symbol, exchange_ts, price, qty, side, trace_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (trade_id, exchange_ts) DO NOTHING;
"""


async def _create_pool(dsn: str):
    try:
        import asyncpg  # type: ignore
    except ModuleNotFoundError:
        logger.error("asyncpg 모듈이 필요합니다. 설치: pip install asyncpg")
        raise
    try:
        pool = await asyncpg.create_pool(dsn)
        logger.info("[init_schema] asyncpg pool 생성 성공")
        return pool
    except Exception:
        logger.exception("[init_schema] asyncpg pool 생성 실패")
        raise


async def create_schema(pool: Any) -> bool:
    """
    market_ticks 테이블 생성 및 hypertable 생성 시도.
    실패 시 예외를 던지지 않고 False 반환(호환성 목적).
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            # hypertable 생성 시도: Timescale이 설치되어 있어야 성공
            try:
                await conn.execute(CREATE_HYPERTABLE_SQL)
                logger.info("[init_schema] hypertable 생성/확인 완료")
            except Exception as e:
                # hypertable 생성 실패는 치명적이지 않음(예: extension 미설치)
                logger.warning("[init_schema] create_hypertable 실패(무시): %s", e)
        logger.info("[init_schema] market_ticks 스키마 생성/확인 완료")
        return True
    except Exception:
        logger.exception("[init_schema] 스키마 생성 실패")
        return False


async def seed_samples(pool: Any, symbols: List[str], hours_ago: int = 48, price: float = 1000.0, qty: float = 0.001):
    """
    각 심볼에 대해 단일 샘플 tick을 삽입.
    exchange_ts = now - hours_ago
    """
    now = datetime.now(timezone.utc)
    sample_ts = now - timedelta(hours=hours_ago)
    try:
        async with pool.acquire() as conn:
            for sym in symbols:
                trade_id = f"seed-{sym}-{int(sample_ts.timestamp())}"
                side = "bid"
                trace_id = f"seed-{sym}"
                await conn.execute(INSERT_SAMPLE_SQL, trade_id, sym, sample_ts, price, qty, side, trace_id)
                logger.info("[init_schema] 샘플 삽입: symbol=%s trade_id=%s exchange_ts=%s", sym, trade_id, sample_ts.isoformat())
    except Exception:
        logger.exception("[init_schema] 샘플 삽입 실패")
        raise


async def _main_async(args):
    if not args.timescale_dsn:
        logger.error("timescale-dsn이 필요합니다. --timescale-dsn 인자 또는 TIMESCALE_DSN 환경변수를 사용하세요.")
        return

    pool = await _create_pool(args.timescale_dsn)
    try:
        ok = await create_schema(pool)
        if not ok:
            logger.error("스키마 생성 실패, 종료")
            return

        if args.seed_symbols:
            symbols = [s.strip() for s in args.seed_symbols.split(",") if s.strip()]
            if symbols:
                await seed_samples(pool, symbols, hours_ago=args.hours_ago, price=args.price, qty=args.qty)
            else:
                logger.warning("seed_symbols 가 비어있음 - 샘플 삽입 생략")
        else:
            logger.info("샘플 삽입 옵션 미지정 (--seed-symbols) - 스키마 생성만 수행")
    finally:
        try:
            await pool.close()
        except Exception:
            logger.debug("pool 종료 중 예외", exc_info=True)


def main():
    p = argparse.ArgumentParser(description="Timescale market_ticks 스키마 생성 및 샘플 삽입 (개발용)")
    p.add_argument("--timescale-dsn", type=str, default=os.environ.get("TIMESCALE_DSN", ""), help="Timescale/Postgres DSN")
    p.add_argument("--create-only", action="store_true", help="스키마만 생성 (seed 무시)")
    p.add_argument("--seed-symbols", type=str, default="", help="콤마로 구분된 심볼 리스트 (예: KRW-BTC,KRW-ETH)")
    p.add_argument("--hours-ago", type=int, default=48, help="삽입할 샘플의 exchange_ts 를 현재에서 몇 시간 이전으로 할지")
    p.add_argument("--price", type=float, default=50000.0, help="샘플 price")
    p.add_argument("--qty", type=float, default=0.001, help="샘플 qty")
    args = p.parse_args()

    # create-only이면 seed 무시
    if args.create_only:
        args.seed_symbols = ""

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()